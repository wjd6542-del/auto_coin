import sys
from pathlib import Path

# `streamlit run dashboard/app.py`로 직접 실행할 때 프로젝트 루트를
# 파이썬 경로에 넣어 config/db 모듈을 찾게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import replace

import pandas as pd
import streamlit as st

from config import database, Settings
from db.store import Store
from engine.paper import PaperTrader

TRADE_COLUMNS = ["시각", "종목", "구분", "체결가(원)", "수량", "거래금액(원)", "수수료(원)", "사유"]
HOLDING_COLUMNS = ["종목", "매수가(원)", "수량", "매수금액(원)", "고점(원)"]
SITUATION_COLUMNS = ["종목", "평단(원)", "현재가(원)", "수익률", "추세", "손절가(원)", "손절까지"]


def load_data(store: Store, mode: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    balance, trades = store.balance_df(), store.trades_df()
    if mode is not None:
        balance = balance[balance["mode"] == mode].reset_index(drop=True)
        trades = trades[trades["mode"] == mode].reset_index(drop=True)
    return balance, trades


def load_settings(store: Store) -> Settings:
    return store.get_settings()


def live_safety_badge(settings: Settings) -> str:
    """실거래 상태를 요약한 배지 문자열을 반환한다."""
    if settings.kill_switch:
        return "🛑 비상정지 켜짐 — 거래 중단"
    if settings.live_enabled:
        return "🟢 실거래 ON — 진짜 돈으로 매매 중"
    return "⚪ 실거래 OFF — 판단만(주문 안 함)"


def run_paper_now(store: Store, settings: Settings, client=None) -> dict:
    """페이퍼 1 사이클을 지금 실행한다 (대시보드 수동 실행 버튼용).

    client 미지정 시 실제 빗썸 클라이언트를 쓴다. 테스트는 stub 주입.
    """
    if client is None:
        from bithumb.client import BithumbClient
        client = BithumbClient()
    return PaperTrader(settings, store, client, fee_rate=settings.fee_rate).run_once()


def format_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """거래 내역을 한글 컬럼 + 거래금액 포함으로 변환한다 (최신순)."""
    if trades.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    df = trades.copy()
    df["구분"] = df["side"].map({"buy": "매수", "sell": "매도"}).fillna(df["side"])
    df["거래금액(원)"] = df["price"] * df["qty"]
    if "note" not in df.columns:
        df["note"] = ""
    df["note"] = df["note"].fillna("")
    out = df.rename(columns={"ts": "시각", "symbol": "종목", "price": "체결가(원)",
                             "qty": "수량", "fee": "수수료(원)", "note": "사유"})[TRADE_COLUMNS]
    return out.sort_values("시각", ascending=False).reset_index(drop=True)


def position_situation(positions: dict, settings: Settings,
                       price_map: dict, trend_map: dict) -> pd.DataFrame:
    """보유 포지션의 현재 상황: 현재가·수익률·추세·손절가·손절까지 거리."""
    if not positions:
        return pd.DataFrame(columns=SITUATION_COLUMNS)
    rows = []
    for sym, p in positions.items():
        cur = price_map.get(sym)
        if cur is None:
            continue
        ret = (cur / p.entry_price - 1) * 100
        stop = p.high_price * (1 - settings.trailing_stop_pct)
        to_stop = (cur - stop) / cur * 100 if cur else 0.0
        rows.append({"종목": sym, "평단(원)": p.entry_price, "현재가(원)": cur,
                     "수익률": f"{ret:+.1f}%", "추세": trend_map.get(sym, "-"),
                     "손절가(원)": stop, "손절까지": f"{to_stop:+.1f}%"})
    return pd.DataFrame(rows, columns=SITUATION_COLUMNS)


def balance_chart(balance: pd.DataFrame) -> pd.DataFrame:
    """자금 흐름 시계열: 총자산 / 현금 / 보유평가.

    매수하면 현금↓·보유평가↑, 매도하면 반대로 움직이는 게 보인다.
    기록이 없는(과거) 컬럼은 자동으로 뺀다.
    """
    df = balance.set_index("ts")
    out = pd.DataFrame({"총자산": df["total_krw"]})
    if "cash_krw" in df.columns and df["cash_krw"].notna().any():
        out["현금"] = df["cash_krw"]
    if "holdings_krw" in df.columns and df["holdings_krw"].notna().any():
        out["보유평가"] = df["holdings_krw"]
    return out


def realized_pnl(trades: pd.DataFrame) -> float:
    """실현 손익(원). 매수-매도를 FIFO로 짝지어 청산된 부분의 손익 합계.

    미청산(보유 중) 매수는 제외. 수수료도 차감한다.
    """
    if trades.empty:
        return 0.0
    from collections import defaultdict, deque
    lots: dict = defaultdict(deque)   # symbol -> [ [qty, price], ... ]
    pnl = 0.0
    for _, t in trades.sort_values("ts").iterrows():
        sym, qty, price = t["symbol"], float(t["qty"]), float(t["price"])
        fee = float(t.get("fee", 0) or 0)
        pnl -= fee
        if t["side"] == "buy":
            lots[sym].append([qty, price])
        else:  # sell — 보유분과 짝지어 실현손익 누적
            remaining = qty
            while remaining > 1e-12 and lots[sym]:
                lot = lots[sym][0]
                take = min(remaining, lot[0])
                pnl += take * (price - lot[1])
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-12:
                    lots[sym].popleft()
    return pnl


def two_week_trend(closes_by_symbol: dict) -> pd.DataFrame:
    """종목별 최근 종가를 기준일=100으로 정규화(추세 비교용).

    가격대가 다른 종목(ETH 270만 vs PUMP 3원)을 한 차트에서 비교하려면
    시작점을 100으로 맞춰 % 변화로 봐야 한다.
    """
    cols = {}
    for sym, ser in closes_by_symbol.items():
        s = ser.dropna()
        if len(s) == 0 or float(s.iloc[0]) == 0:
            continue
        cols[sym] = s / float(s.iloc[0]) * 100
    return pd.DataFrame(cols)


@st.cache_data(ttl=300)
def _fetch_recent_closes(symbols: tuple, days: int = 14) -> dict:
    """종목별 최근 days일 종가를 빗썸에서 조회. 5분 캐시."""
    from bithumb.client import BithumbClient
    client = BithumbClient()
    out = {}
    for s in symbols:
        try:
            out[s] = client.get_daily_candles(s)["close"].tail(days)
        except Exception:
            pass
    return out


def holdings_table(positions: dict) -> pd.DataFrame:
    """보유 포지션을 한글 컬럼 표로 변환한다."""
    if not positions:
        return pd.DataFrame(columns=HOLDING_COLUMNS)
    rows = [{"종목": s, "매수가(원)": p.entry_price, "수량": p.qty,
             "매수금액(원)": p.entry_price * p.qty, "고점(원)": p.high_price}
            for s, p in positions.items()]
    return pd.DataFrame(rows, columns=HOLDING_COLUMNS)


def gubun_color(gubun: str) -> str:
    """매수/매도 글자색 CSS (배경 건드리지 않음. 다크·라이트 모두 잘 보이는 색)."""
    if gubun == "매수":
        return "color: #ff4d4f; font-weight: bold"
    if gubun == "매도":
        return "color: #4d9bff; font-weight: bold"
    return ""


def fmt_price(x: float) -> str:
    """가격 표시. 저가 코인(1000원 미만)은 소수점까지 보여준다.

    PUMP처럼 2.876원짜리 코인을 '3'으로 반올림하면 안 되기 때문이다.
    """
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    return f"{x:,.4f}".rstrip("0").rstrip(".")


PRICE_COLUMNS = {"체결가(원)", "매수가(원)", "고점(원)", "평단(원)", "현재가(원)", "손절가(원)"}


def _won(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """지정 컬럼을 표시용 문자열로 포맷한 복사본 (가격은 저가코인 소수점 유지)."""
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            continue
        if c in PRICE_COLUMNS:
            out[c] = out[c].map(fmt_price)
        else:
            out[c] = out[c].map(lambda x: f"{x:,.0f}")
    if "수량" in out.columns:
        out["수량"] = out["수량"].map(lambda x: f"{x:,.6f}")
    return out


@st.cache_data(ttl=60)
def _fetch_price_trend(symbols: tuple, short: int, long: int) -> tuple[dict, dict]:
    """보유 종목의 현재가와 추세(단기>장기=상승)를 빗썸에서 조회. 60초 캐시."""
    from bithumb.client import BithumbClient
    from strategy.indicators import sma
    client = BithumbClient()
    price_map, trend_map = {}, {}
    for sym in symbols:
        try:
            df = client.get_daily_candles(sym)
            price_map[sym] = float(df["close"].iloc[-1])
            s = sma(df["close"], short).iloc[-1]
            l = sma(df["close"], long).iloc[-1]
            trend_map[sym] = "상승 ▲" if s > l else "하락 ▼"
        except Exception:
            pass
    return price_map, trend_map


def render() -> None:
    st.title("코인 자동매매 봇 대시보드")
    store = Store(url=database.url())
    mode = st.radio("모드", ["backtest", "live"], horizontal=True,
                    format_func=lambda m: {"backtest": "백테스트",
                                           "live": "💰 실거래"}[m])

    if mode == "live":
        st.error("⚠️ 실거래 페이지 — 진짜 돈으로 거래됩니다.")
        cs = load_settings(store)
        st.info(live_safety_badge(cs))
        col1, col2 = st.columns(2)
        with col1:
            new_enabled = st.toggle("실거래 활성화 (live_enabled)", cs.live_enabled)
        with col2:
            new_kill = st.toggle("🛑 비상정지 (kill_switch)", cs.kill_switch)
        # 실거래를 새로 켜는 건 진짜 돈이 나가므로 확인 게이트를 둔다.
        # 끄기·비상정지는 안전 방향이라 즉시 반영.
        turning_on = new_enabled and not cs.live_enabled
        confirmed = True
        if turning_on:
            confirmed = st.checkbox(
                "확인: 진짜 돈으로 자동매매를 시작합니다 (투자상한 내에서 실주문)")
        if (new_enabled != cs.live_enabled or new_kill != cs.kill_switch):
            if turning_on and not confirmed:
                st.warning("실거래를 켜려면 위 확인란을 체크하세요.")
            else:
                store.save_settings(replace(cs, live_enabled=new_enabled, kill_switch=new_kill))
                st.rerun()
        st.caption(f"투자 상한 {cs.max_invest_krw:,.0f}원 · 일일 손실한도 "
                   f"{cs.daily_loss_limit_pct*100:.0f}%")
        if st.button("▶️ 실거래 지금 실행", type="primary"):
            try:
                from bithumb.private import BithumbPrivate
                from bithumb.client import BithumbClient
                from config import secrets as _sec
                from engine.live import LiveTrader
                with st.spinner("실잔고 조회 후 매매 판단 중..."):
                    priv = BithumbPrivate(_sec.bithumb_api_key, _sec.bithumb_secret_key)
                    res = LiveTrader(cs, store, BithumbClient(), priv,
                                     fee_rate=cs.fee_rate).run_once()
                if res["blocked"]:
                    st.warning(f"차단됨: {res['blocked']}")
                else:
                    st.success(f"실행 완료 — 현금 {res['cash']:,.0f}원 / "
                               f"보유 {res['positions']}종목 / 체결 {res['filled']}건")
            except Exception as e:
                st.error(f"실행 실패: {e}")

    balance, trades = load_data(store, mode=mode)

    # 요약 지표
    if balance.empty:
        st.info("아직 데이터가 없다. 아래 설정을 확인하고 봇을 실행해라.")
    else:
        start = balance.iloc[0]["total_krw"]
        end = balance.iloc[-1]["total_krw"]
        ret = (end - start) / start * 100
        positions = store.get_positions(mode)
        realized = realized_pnl(trades)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("현재 총자산", f"{end:,.0f} 원")
        c2.metric("수익률", f"{ret:+.2f}%")
        c3.metric("실현 수익", f"{realized:+,.0f} 원")
        c4.metric("보유 종목", f"{len(positions)} 개")
        c5.metric("총 거래", f"{len(trades)} 건")
        st.caption("실현 수익 = 이미 팔아서 확정된 손익(수수료 차감). 보유 중 평가손익은 제외.")

        st.subheader("📈 자금 흐름 (총자산 · 현금 · 보유평가)")
        st.line_chart(balance_chart(balance))
        st.caption("매수하면 현금↓ 보유평가↑, 매도하면 현금↑ 보유평가↓ 로 움직인다.")

        # 매매 종목 2주 추세 (보유 + 거래 종목)
        traded = set(positions) | (set(trades["symbol"]) if not trades.empty else set())
        if traded:
            st.subheader("📉 매매 종목 2주 추세 (시작=100 정규화)")
            with st.spinner("최근 시세 조회 중..."):
                closes = _fetch_recent_closes(tuple(sorted(traded)), 14)
            trend = two_week_trend(closes)
            if trend.empty:
                st.caption("시세를 불러오지 못했다.")
            else:
                st.line_chart(trend)
                st.caption("각 종목의 14일 전 종가를 100으로 맞춘 상대 추세. 100 위=상승, 아래=하락.")

        st.subheader("💼 보유 현황")
        hold = holdings_table(positions)
        if hold.empty:
            st.caption("현재 보유 중인 종목이 없다.")
        else:
            st.dataframe(_won(hold, ["매수가(원)", "매수금액(원)", "고점(원)"]),
                         use_container_width=True, hide_index=True)

        # 현재 상황 요약 (실시간 시세 조회, 페이퍼 모드)
        if mode == "live" and positions:
            st.subheader("📊 현재 상황 요약")
            cs = load_settings(store)
            with st.spinner("현재 시세 조회 중..."):
                pmap, tmap = _fetch_price_trend(
                    tuple(sorted(positions)), cs.short_period, cs.long_period)
            sit = position_situation(positions, cs, pmap, tmap)
            if sit.empty:
                st.caption("시세를 불러오지 못했다.")
            else:
                st.dataframe(_won(sit, ["평단(원)", "현재가(원)", "손절가(원)"]),
                             use_container_width=True, hide_index=True)
                for _, r in sit.iterrows():
                    st.markdown(
                        f"- **{r['종목']}**: 현재 수익률 **{r['수익률']}** · 추세 {r['추세']} · "
                        f"손절가까지 {r['손절까지']} 여유 "
                        f"→ {'추세 유지 중, 계속 보유' if r['추세'].startswith('상승') else '추세 약화, 청산 주의'}")

        st.subheader("📒 거래 내역 (🔴매수 · 🔵매도)")
        disp = _won(format_trades(trades), ["체결가(원)", "거래금액(원)", "수수료(원)"])
        styled = disp.style.map(gubun_color, subset=["구분"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()
    with st.expander("⚙️ 전략 설정 (수정 후 저장하면 다음 실행부터 반영)"):
        cur = load_settings(store)
        with st.form("settings_form"):
            s1, s2, s3 = st.columns(3)
            short = s1.number_input("단기 이평선(일)", 1, 200, cur.short_period)
            long = s2.number_input("장기 이평선(일)", 1, 400, cur.long_period)
            rsi_p = s3.number_input("RSI 기간(일)", 1, 100, cur.rsi_period)
            rsi_os = s1.number_input("RSI 과매도선", 0.0, 100.0, cur.rsi_oversold)
            rsi_rc = s2.number_input("RSI 회복선", 0.0, 100.0, cur.rsi_recover)
            use_rsi = s3.checkbox("RSI 필터 사용(보수적)", cur.use_rsi_filter)
            trail = s1.number_input("트레일링스톱(%)", 0.0, 100.0, cur.trailing_stop_pct * 100) / 100
            maxpos = s2.number_input("동시 보유 종목수", 1, 50, cur.max_positions)
            pos_pct = s3.number_input("종목당 비중(%)", 0.0, 100.0, cur.position_pct * 100) / 100
            vol_pct = s1.number_input("거래량 대비 상한(%)", 0.0, 100.0, cur.max_volume_pct * 100) / 100
            top_n = s2.number_input("매매대상 상위 N종목", 1, 500, cur.top_n)
            min_val = s3.number_input("최소 거래대금(원)", 0.0, 1e12, cur.min_trade_value_krw)
            init_cap = s1.number_input("초기 자본(원)", 0.0, 1e12, cur.initial_capital)
            fee = s2.number_input("수수료율", 0.0, 1.0, cur.fee_rate, format="%.4f")
            if st.form_submit_button("저장"):
                store.save_settings(replace(cur,
                    short_period=int(short), long_period=int(long), rsi_period=int(rsi_p),
                    rsi_oversold=rsi_os, rsi_recover=rsi_rc, use_rsi_filter=use_rsi,
                    trailing_stop_pct=trail, max_positions=int(maxpos), position_pct=pos_pct,
                    max_volume_pct=vol_pct, top_n=int(top_n), min_trade_value_krw=min_val,
                    initial_capital=init_cap, fee_rate=fee))
                st.success("저장됐다. 다음 봇 실행부터 반영된다.")


if __name__ == "__main__":
    render()
