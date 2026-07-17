import pandas as pd
import requests

BASE = "https://api.bithumb.com/public"


class BithumbClient:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def get_top_symbols(self, top_n: int, min_trade_value: float) -> list[str]:
        url = f"{BASE}/ticker/ALL_KRW"
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"]
        rows = []
        for symbol, info in data.items():
            if symbol == "date" or not isinstance(info, dict):
                continue
            value = float(info["acc_trade_value_24H"])
            if value >= min_trade_value:
                rows.append((symbol, value))
        rows.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in rows[:top_n]]

    def get_daily_candles(self, symbol: str) -> pd.DataFrame:
        url = f"{BASE}/candlestick/{symbol}_KRW/24h"
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        raw = resp.json()["data"]
        df = pd.DataFrame(
            raw, columns=["ts", "open", "close", "high", "low", "volume"]
        )
        df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df = df.set_index("ts").sort_index()
        return df[["open", "high", "low", "close", "volume"]]
