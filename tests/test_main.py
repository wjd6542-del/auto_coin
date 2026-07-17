import pandas as pd
from config import Settings
from db.store import Store
from main import run_backtest, run_paper


class StubClient:
    def get_top_symbols(self, top_n, min_trade_value):
        return ["AAA"]

    def get_daily_candles(self, symbol):
        closes = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140, 150, 160, 170]
        idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
        return pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1.0] * len(closes)}, index=idx)


def test_run_backtest_end_to_end(tmp_path):
    store = Store(str(tmp_path / "m.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40)
    result = run_backtest(StubClient(), store, s)
    assert result.num_trades >= 1
    assert len(store.trades_df()) >= 1


def test_run_paper_end_to_end(tmp_path):
    class PaperStub:
        def get_top_symbols(self, top_n, min_trade_value):
            return ["AAA"]
        def get_daily_candles(self, symbol):
            closes = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140]
            idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
            return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                                 "close": closes, "volume": [1.0]*len(closes)}, index=idx)

    store = Store(str(tmp_path / "mp.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False)
    summary = run_paper(PaperStub(), store, s)
    assert "total" in summary
    assert store.get_account("paper") is not None
