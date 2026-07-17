from dataclasses import dataclass, field

import pandas as pd

from config import Settings
from strategy.indicators import sma, rsi


@dataclass
class Signal:
    action: str  # "buy" | "sell" | "hold"
    reason: dict = field(default_factory=dict)


def evaluate(candles: pd.DataFrame, settings: Settings, in_position: bool) -> Signal:
    close = candles["close"]
    if len(close) < settings.long_period + 1:
        return Signal("hold", {"why": "insufficient_data"})

    short = sma(close, settings.short_period)
    long = sma(close, settings.long_period)
    r = rsi(close, settings.rsi_period)

    short_now, short_prev = short.iloc[-1], short.iloc[-2]
    long_now, long_prev = long.iloc[-1], long.iloc[-2]
    rsi_now = r.iloc[-1]
    rsi_window = r.iloc[-settings.rsi_period:]

    golden = short_prev <= long_prev and short_now > long_now
    dead = short_prev >= long_prev and short_now < long_now
    rsi_recovered = (rsi_window.min() < settings.rsi_oversold) and (rsi_now > settings.rsi_recover)

    reason = {"short": float(short_now), "long": float(long_now), "rsi": float(rsi_now)}

    if not in_position and golden and rsi_recovered:
        return Signal("buy", reason)
    if in_position and dead:
        return Signal("sell", reason)
    return Signal("hold", reason)
