import pandas as pd
from config import Settings
from db.store import Store
from engine.backtest import Backtest


def _series(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1_000_000.0] * len(closes)},
        index=idx,
    )


def test_backtest_runs_and_records(tmp_path):
    store = Store(str(tmp_path / "bt.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40, max_positions=2,
                 initial_capital=1_000_000)
    # 매수 유발 후 상승 → 이익 실현되는 패턴
    up = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140, 150, 160, 170]
    result = Backtest(s, store).run({"AAA": _series(up)})
    assert result.num_trades >= 1
    assert result.final_capital > 0
    assert len(store.balance_df()) == len(up)


def test_no_signal_keeps_capital_flat(tmp_path):
    store = Store(str(tmp_path / "flat.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, initial_capital=1_000_000)
    flat = [100.0] * 15  # 크로스 없음
    result = Backtest(s, store).run({"AAA": _series(flat)})
    assert result.num_trades == 0
    assert result.final_capital == 1_000_000
