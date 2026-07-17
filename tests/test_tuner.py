import pandas as pd

from config import Settings
from engine.tuner import compute_mdd, backtest_once, run_grid


def _series(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1.0] * len(closes)},
        index=idx,
    )


def test_compute_mdd():
    # 100 → 120 → 90 → 110 : 고점 120 대비 90은 -25%
    s = pd.Series([100, 120, 90, 110], dtype=float)
    assert compute_mdd(s) == -25.0


def test_compute_mdd_empty():
    assert compute_mdd(pd.Series([], dtype=float)) == 0.0


def test_backtest_once_returns_metrics():
    up = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140, 150, 160, 170]
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False)
    m = backtest_once({"AAA": _series(up)}, s)
    assert set(m) == {"return_pct", "mdd_pct", "num_trades", "final_capital"}
    assert m["num_trades"] >= 1


def test_run_grid_sorted_by_return():
    up = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140, 150, 160, 170]
    base = Settings(long_period=5, use_rsi_filter=False)
    grid = {"short_period": [2, 3], "trailing_stop_pct": [0.05, 0.10]}
    rows = run_grid({"AAA": _series(up)}, base, grid)
    assert len(rows) == 4  # 2 x 2 조합
    # 수익률 내림차순 정렬 확인
    returns = [r["return_pct"] for r in rows]
    assert returns == sorted(returns, reverse=True)
    # 각 행에 파라미터와 지표가 모두 있어야 함
    assert "short_period" in rows[0] and "return_pct" in rows[0]
