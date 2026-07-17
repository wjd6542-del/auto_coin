import pandas as pd
from strategy.indicators import sma, rsi


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(s, 3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 2.0   # (1+2+3)/3
    assert result.iloc[4] == 4.0   # (3+4+5)/3


def test_rsi_all_gains_is_100():
    s = pd.Series(range(1, 20), dtype=float)  # 계속 상승
    result = rsi(s, 14)
    assert result.iloc[-1] == 100.0


def test_rsi_bounds():
    s = pd.Series([10, 11, 9, 12, 8, 13, 7, 14, 6, 15, 5, 16, 4, 17, 3], dtype=float)
    result = rsi(s, 14).dropna()
    assert (result >= 0).all() and (result <= 100).all()
