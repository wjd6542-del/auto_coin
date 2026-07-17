"""파라미터 튜닝 — 여러 설정 조합을 백테스트해 수익률·낙폭으로 비교한다.

캔들 데이터는 호출자가 한 번만 수집해 넘기고, 모든 조합이 이를 재사용한다.
각 조합은 인메모리 SQLite에 기록해 실행하므로 운영 DB를 건드리지 않는다.
"""

from dataclasses import replace
from itertools import product

import pandas as pd

from config import Settings
from db.store import Store
from engine.backtest import Backtest


def compute_mdd(balance: pd.Series) -> float:
    """최대 낙폭(MDD)을 % 로 반환한다 (음수, 예: -26.7)."""
    if balance.empty:
        return 0.0
    cummax = balance.cummax()
    drawdown = (balance - cummax) / cummax * 100
    return float(drawdown.min())


def backtest_once(
    candles_by_symbol: dict[str, pd.DataFrame],
    settings: Settings,
    fee_rate: float = 0.0004,
) -> dict:
    """한 설정으로 백테스트를 돌려 지표 dict를 반환한다."""
    store = Store(url="sqlite:///:memory:")
    store.create_all()
    result = Backtest(settings, store, fee_rate=fee_rate).run(candles_by_symbol)
    balance = store.balance_df()
    mdd = compute_mdd(balance["total_krw"]) if not balance.empty else 0.0
    return {
        "return_pct": round(result.return_pct, 1),
        "mdd_pct": round(mdd, 1),
        "num_trades": result.num_trades,
        "final_capital": round(result.final_capital),
    }


def run_grid(
    candles_by_symbol: dict[str, pd.DataFrame],
    base_settings: Settings,
    grid: dict[str, list],
    fee_rate: float = 0.0004,
) -> list[dict]:
    """grid의 모든 파라미터 조합을 백테스트해 수익률 내림차순 리스트로 반환한다.

    grid 예: {"short_period": [10, 20], "trailing_stop_pct": [0.05, 0.10]}
    반환 각 항목: {파라미터들..., return_pct, mdd_pct, num_trades, final_capital}
    """
    keys = list(grid.keys())
    rows = []
    for combo in product(*[grid[k] for k in keys]):
        overrides = dict(zip(keys, combo))
        settings = replace(base_settings, **overrides)
        metrics = backtest_once(candles_by_symbol, settings, fee_rate)
        rows.append({**overrides, **metrics})
    rows.sort(key=lambda r: r["return_pct"], reverse=True)
    return rows
