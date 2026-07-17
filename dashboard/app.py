import sys
from pathlib import Path

# `streamlit run dashboard/app.py`로 직접 실행할 때 프로젝트 루트를
# 파이썬 경로에 넣어 config/db 모듈을 찾게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from config import database, Settings
from db.store import Store


def load_data(store: Store, mode: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    balance, trades = store.balance_df(), store.trades_df()
    if mode is not None:
        balance = balance[balance["mode"] == mode].reset_index(drop=True)
        trades = trades[trades["mode"] == mode].reset_index(drop=True)
    return balance, trades


def load_settings(store: Store) -> Settings:
    return store.get_settings()


def render() -> None:
    st.title("코인 자동매매 봇 대시보드")
    store = Store(url=database.url())
    mode = st.radio("모드", ["backtest", "paper"], horizontal=True)
    balance, trades = load_data(store, mode=mode)

    if balance.empty:
        st.info("아직 데이터가 없다. `python3 main.py --mode backtest` 먼저 실행.")
        return

    start = balance.iloc[0]["total_krw"]
    end = balance.iloc[-1]["total_krw"]
    ret = (end - start) / start * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("현재 자산", f"{end:,.0f} KRW")
    c2.metric("수익률", f"{ret:.2f}%")
    c3.metric("거래 수", f"{len(trades)}")

    st.subheader("총자산 추이")
    st.line_chart(balance.set_index("ts")["total_krw"])

    st.subheader("거래 내역")
    st.dataframe(trades.sort_values("ts", ascending=False))

    st.divider()
    with st.expander("⚙️ 전략 설정 (수정 후 저장하면 다음 실행부터 반영)"):
        cur = load_settings(store)
        with st.form("settings_form"):
            c1, c2, c3 = st.columns(3)
            short = c1.number_input("단기 이평", 1, 200, cur.short_period)
            long = c2.number_input("장기 이평", 1, 400, cur.long_period)
            rsi_p = c3.number_input("RSI 기간", 1, 100, cur.rsi_period)
            rsi_os = c1.number_input("RSI 과매도", 0.0, 100.0, cur.rsi_oversold)
            rsi_rc = c2.number_input("RSI 회복", 0.0, 100.0, cur.rsi_recover)
            use_rsi = c3.checkbox("RSI 필터 사용(보수적)", cur.use_rsi_filter)
            trail = c1.number_input("트레일링스톱 %", 0.0, 100.0, cur.trailing_stop_pct * 100) / 100
            maxpos = c2.number_input("동시 보유 종목", 1, 50, cur.max_positions)
            pos_pct = c3.number_input("종목당 비중 %", 0.0, 100.0, cur.position_pct * 100) / 100
            vol_pct = c1.number_input("거래량대비 상한 %", 0.0, 100.0, cur.max_volume_pct * 100) / 100
            top_n = c2.number_input("상위 N종목", 1, 500, cur.top_n)
            min_val = c3.number_input("최소 거래대금(KRW)", 0.0, 1e12, cur.min_trade_value_krw)
            init_cap = c1.number_input("초기 자본(KRW)", 0.0, 1e12, cur.initial_capital)
            fee = c2.number_input("수수료율", 0.0, 1.0, cur.fee_rate, format="%.4f")
            if st.form_submit_button("저장"):
                from dataclasses import replace
                store.save_settings(replace(cur,
                    short_period=int(short), long_period=int(long), rsi_period=int(rsi_p),
                    rsi_oversold=rsi_os, rsi_recover=rsi_rc, use_rsi_filter=use_rsi,
                    trailing_stop_pct=trail, max_positions=int(maxpos), position_pct=pos_pct,
                    max_volume_pct=vol_pct, top_n=int(top_n), min_trade_value_krw=min_val,
                    initial_capital=init_cap, fee_rate=fee))
                st.success("저장됐다. 다음 봇 실행부터 반영된다.")


if __name__ == "__main__":
    render()
