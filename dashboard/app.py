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

TRADE_COLUMNS = ["시각", "종목", "구분", "체결가(원)", "수량", "거래금액(원)", "수수료(원)"]
HOLDING_COLUMNS = ["종목", "매수가(원)", "수량", "매수금액(원)", "고점(원)"]


def load_data(store: Store, mode: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    balance, trades = store.balance_df(), store.trades_df()
    if mode is not None:
        balance = balance[balance["mode"] == mode].reset_index(drop=True)
        trades = trades[trades["mode"] == mode].reset_index(drop=True)
    return balance, trades


def load_settings(store: Store) -> Settings:
    return store.get_settings()


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
    out = df.rename(columns={"ts": "시각", "symbol": "종목", "price": "체결가(원)",
                             "qty": "수량", "fee": "수수료(원)"})[TRADE_COLUMNS]
    return out.sort_values("시각", ascending=False).reset_index(drop=True)


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


PRICE_COLUMNS = {"체결가(원)", "매수가(원)", "고점(원)"}


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


def render() -> None:
    st.title("코인 자동매매 봇 대시보드")
    store = Store(url=database.url())
    mode = st.radio("모드", ["backtest", "paper"], horizontal=True,
                    format_func=lambda m: {"backtest": "백테스트",
                                           "paper": "페이퍼(실시간 가상)"}[m])

    # 페이퍼 수동 실행 버튼 (버튼 클릭 시 아래 load_data가 갱신된 DB를 읽음)
    if mode == "paper":
        if st.button("▶️ 페이퍼 지금 실행 (실시간 시세로 1회 매매)", type="primary"):
            try:
                with st.spinner("빗썸 시세 조회 후 매매 판단 중... (수십 초 걸릴 수 있다)"):
                    summary = run_paper_now(store, load_settings(store))
                st.session_state["paper_run_result"] = summary
            except Exception as e:
                st.session_state["paper_run_result"] = {"error": str(e)}
        res = st.session_state.get("paper_run_result")
        if res:
            if "error" in res:
                st.error(f"실행 실패: {res['error']}")
            else:
                st.success(
                    f"실행 완료 — 현금 {res['cash']:,.0f}원 / 보유 {res['positions']}종목 "
                    f"/ 이번 체결 {res['filled']}건 / 총자산 {res['total']:,.0f}원")

    balance, trades = load_data(store, mode=mode)

    # 요약 지표
    if balance.empty:
        st.info("아직 데이터가 없다. 아래 설정을 확인하고 봇을 실행해라.")
    else:
        start = balance.iloc[0]["total_krw"]
        end = balance.iloc[-1]["total_krw"]
        ret = (end - start) / start * 100
        positions = store.get_positions(mode)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("현재 총자산", f"{end:,.0f} 원")
        c2.metric("수익률", f"{ret:+.2f}%")
        c3.metric("보유 종목", f"{len(positions)} 개")
        c4.metric("총 거래", f"{len(trades)} 건")

        st.subheader("📈 자금 흐름 (총자산 · 현금 · 보유평가)")
        st.line_chart(balance_chart(balance))
        st.caption("매수하면 현금↓ 보유평가↑, 매도하면 현금↑ 보유평가↓ 로 움직인다.")

        st.subheader("💼 보유 현황")
        hold = holdings_table(positions)
        if hold.empty:
            st.caption("현재 보유 중인 종목이 없다.")
        else:
            st.dataframe(_won(hold, ["매수가(원)", "매수금액(원)", "고점(원)"]),
                         use_container_width=True, hide_index=True)

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
