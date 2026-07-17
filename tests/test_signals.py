import pandas as pd
from config import Settings
from strategy.signals import evaluate, Signal


def _candles(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def test_insufficient_data_holds():
    s = Settings()
    candles = _candles([100.0] * 10)  # long_period(60) 미만
    sig = evaluate(candles, s, in_position=False)
    assert sig.action == "hold"


def test_golden_cross_with_rsi_recovery_buys():
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40)
    # 하락으로 RSI 과매도 → 반등하여 골든크로스 형성
    closes = [100, 95, 90, 88, 85, 82, 80, 82, 88, 95]
    sig = evaluate(_candles(closes), s, in_position=False)
    assert sig.action == "buy"
    assert "rsi" in sig.reason


def test_dead_cross_sells_when_in_position():
    s = Settings(short_period=3, long_period=5, rsi_period=5)
    closes = [80, 85, 90, 95, 100, 105, 110, 115, 120, 80]  # 상승 후 하락 → 데드크로스
    sig = evaluate(_candles(closes), s, in_position=True)
    assert sig.action == "sell"
