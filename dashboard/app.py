import sys
from pathlib import Path

# `streamlit run dashboard/app.py`로 직접 실행할 때 프로젝트 루트를
# 파이썬 경로에 넣어 config/db 모듈을 찾게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from config import database
from db.store import Store


def load_data(store: Store, mode: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    balance, trades = store.balance_df(), store.trades_df()
    if mode is not None:
        balance = balance[balance["mode"] == mode].reset_index(drop=True)
        trades = trades[trades["mode"] == mode].reset_index(drop=True)
    return balance, trades


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


if __name__ == "__main__":
    render()
