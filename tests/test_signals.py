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


def test_conservative_mode_buys_with_golden_cross_and_rsi_recovery():
    # 보수적 모드: 골든크로스 + RSI 회복 둘 다 만족해야 매수
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40, use_rsi_filter=True)
    closes = [100, 95, 90, 88, 85, 82, 80, 82, 88, 95]
    sig = evaluate(_candles(closes), s, in_position=False)
    assert sig.action == "buy"
    assert "rsi" in sig.reason


def test_conservative_mode_holds_without_rsi_recovery():
    # 보수적 모드: 골든크로스는 있지만 RSI 회복 조건 미충족(recover=101, 도달불가) → 보류
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=101, use_rsi_filter=True)
    closes = [100, 95, 90, 88, 85, 82, 80, 82, 88, 95]
    sig = evaluate(_candles(closes), s, in_position=False)
    assert sig.action == "hold"


def test_trend_mode_buys_on_golden_cross_without_rsi():
    # 추세추종 모드: RSI 회복 조건 미충족(recover=101)이어도 골든크로스만으로 매수
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=101, use_rsi_filter=False)
    closes = [100, 95, 90, 88, 85, 82, 80, 82, 88, 95]
    sig = evaluate(_candles(closes), s, in_position=False)
    assert sig.action == "buy"


def test_dead_cross_sells_when_in_position():
    s = Settings(short_period=3, long_period=5, rsi_period=5)
    closes = [80, 85, 90, 95, 100, 105, 110, 115, 120, 80]  # 상승 후 하락 → 데드크로스
    sig = evaluate(_candles(closes), s, in_position=True)
    assert sig.action == "sell"
