import base64
import hashlib
import hmac
import time
import urllib.parse

import requests

BASE = "https://api.bithumb.com"


class BithumbPrivate:
    """빗썸 인증 API (API 1.0). 실잔고 조회 + 시장가 매수/매도."""

    def __init__(self, api_key: str, secret_key: str, session=None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.session = session or requests.Session()

    def _sign(self, endpoint: str, params: dict, nonce: str) -> str:
        query = urllib.parse.urlencode(params)
        data = endpoint + chr(0) + query + chr(0) + nonce
        h = hmac.new(self.secret_key.encode("utf-8"),
                     data.encode("utf-8"), hashlib.sha512)
        return base64.b64encode(h.hexdigest().encode("utf-8")).decode("utf-8")

    def _post(self, endpoint: str, params: dict) -> dict:
        params = {"endpoint": endpoint, **params}
        nonce = str(int(time.time() * 1000))
        headers = {
            "Api-Key": self.api_key,
            "Api-Sign": self._sign(endpoint, params, nonce),
            "Api-Nonce": nonce,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        resp = self.session.post(BASE + endpoint, data=params,
                                 headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_balance(self, currency: str = "ALL") -> dict:
        return self._post("/info/balance", {"currency": currency})

    def market_buy(self, symbol: str, units: float) -> dict:
        return self._post("/trade/market_buy", {
            "order_currency": symbol, "payment_currency": "KRW",
            "units": f"{units:.8f}"})

    def market_sell(self, symbol: str, units: float) -> dict:
        return self._post("/trade/market_sell", {
            "order_currency": symbol, "payment_currency": "KRW",
            "units": f"{units:.8f}"})


def parse_krw_available(balance: dict) -> float:
    return float(balance.get("data", {}).get("available_krw", 0) or 0)


def parse_units(balance: dict, symbol: str) -> float:
    key = f"available_{symbol.lower()}"
    return float(balance.get("data", {}).get(key, 0) or 0)
