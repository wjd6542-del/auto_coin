import pandas as pd
from config import Settings
from db.store import Store
from engine.paper import PaperTrader


def _series(closes):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1.0] * len(closes)}, index=idx)


class StubClient:
    def __init__(self, candles):
        self._candles = candles
    def get_top_symbols(self, top_n, min_trade_value):
        return list(self._candles.keys())
    def get_daily_candles(self, symbol):
        return self._candles[symbol]


def _store(tmp_path):
    s = Store(str(tmp_path / "paper.db"))
    s.create_all()
    return s


def test_first_run_initializes_and_buys(tmp_path):
    store = _store(tmp_path)
    # 골든크로스가 "마지막 캔들"에서 발생하도록 만든 하락 후 반등 시계열
    # (short=3, long=5 SMA가 마지막 지점에서 막 교차하도록 검증된 값)
    up = [100, 95, 90, 85, 80, 78, 85, 95]
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 initial_capital=1_000_000, max_positions=4)
    trader = PaperTrader(s, store, StubClient({"AAA": _series(up)}))
    summary = trader.run_once()
    # 매수 발생 → 포지션 1개, 현금 감소, trade 기록
    assert summary["positions"] == 1
    assert summary["cash"] < 1_000_000
    assert len(store.trades_df()) == 1
    # 계좌·포지션이 DB에 지속됨
    assert store.get_account("paper") is not None
    assert "AAA" in store.get_positions("paper")


def test_state_persists_across_runs(tmp_path):
    store = _store(tmp_path)
    up = [100, 95, 90, 85, 80, 78, 85, 95]
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 initial_capital=1_000_000, max_positions=4)
    trader = PaperTrader(s, store, StubClient({"AAA": _series(up)}))
    trader.run_once()
    cash_after_first = store.get_account("paper")
    # 두 번째 실행: 이미 보유 중이라 재매수 안 함(중복 진입 금지), 현금 유지
    trader2 = PaperTrader(s, store, StubClient({"AAA": _series(up)}))
    trader2.run_once()
    assert store.get_account("paper") == cash_after_first
    assert len(store.get_positions("paper")) == 1
