import pandas as pd
import requests

BASE = "https://api.bithumb.com/public"
COINGECKO = "https://api.coingecko.com/api/v3/coins/markets"

# 스테이블코인·래핑코인 (시총 상위지만 매매 대상 아님)
STABLES = {"USDT", "USDC", "USDS", "DAI", "TUSD", "BUSD", "FDUSD", "PYUSD",
           "USDE", "USDD", "GUSD", "FRAX", "USD1", "WBTC", "WETH", "WBT", "LEO"}


class BithumbClient:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def _liquid_symbols(self, min_trade_value: float) -> dict:
        """빗썸 상장 코인 중 거래대금 필터 통과분 {심볼: 거래대금}."""
        resp = self.session.get(f"{BASE}/ticker/ALL_KRW", timeout=10)
        resp.raise_for_status()
        out = {}
        for symbol, info in resp.json()["data"].items():
            if symbol == "date" or not isinstance(info, dict):
                continue
            value = float(info["acc_trade_value_24H"])
            if value >= min_trade_value:
                out[symbol] = value
        return out

    def get_top_symbols(self, top_n: int, min_trade_value: float) -> list[str]:
        """거래대금 24h 순 상위 N종목."""
        liquid = self._liquid_symbols(min_trade_value)
        rows = sorted(liquid.items(), key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in rows[:top_n]]

    def get_marketcap_symbols(self, top_n: int, min_trade_value: float) -> list[str]:
        """시가총액 상위 순 매매 대상. 빗썸 유동종목 ∩ 시총상위, 스테이블 제외.

        CoinGecko 시총 순위를 받아, 빗썸에서 유동성 통과한 코인만 시총 순으로 N개.
        실패하면 거래대금 순(get_top_symbols)으로 폴백한다.
        """
        liquid = set(self._liquid_symbols(min_trade_value))
        try:
            d = self.session.get(COINGECKO, params={
                "vs_currency": "krw", "order": "market_cap_desc",
                "per_page": 250, "page": 1}, timeout=15).json()
        except Exception:
            return self.get_top_symbols(top_n, min_trade_value)
        if not isinstance(d, list):
            return self.get_top_symbols(top_n, min_trade_value)
        result = []
        for c in d:
            sym = str(c.get("symbol", "")).upper()
            if sym in STABLES or sym not in liquid:
                continue
            result.append(sym)
            if len(result) >= top_n:
                break
        return result or self.get_top_symbols(top_n, min_trade_value)

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


def select_universe(client, settings) -> list[str]:
    """설정에 따라 매매 대상 종목을 고른다.

    use_market_cap=True + 클라이언트가 시총 조회를 지원하면 시총 상위,
    아니면 거래대금 상위. (테스트 스텁은 get_marketcap_symbols가 없어 폴백)
    """
    if getattr(settings, "use_market_cap", False) and hasattr(client, "get_marketcap_symbols"):
        return client.get_marketcap_symbols(settings.top_n, settings.min_trade_value_krw)
    return client.get_top_symbols(settings.top_n, settings.min_trade_value_krw)
