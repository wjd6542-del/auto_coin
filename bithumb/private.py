"""빗썸 인증 API (2.0, JWT 방식).

- 잔고 조회: GET /v1/accounts
- 시장가 주문: POST /v2/orders
인증: JWT Bearer 토큰(HS256), 파라미터 있는 요청은 query_hash(SHA512) 포함.
성공 응답은 주문 객체(uuid 포함), 실패는 {"error": {...}} 형태.
키는 로그·리턴에 노출하지 않는다.
"""

import hashlib
import time
import urllib.parse
import uuid

import jwt
import requests

BASE = "https://api.bithumb.com"


class BithumbPrivate:
    def __init__(self, api_key: str, secret_key: str, session=None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.session = session or requests.Session()

    def _token(self, params: dict | None = None) -> str:
        payload = {
            "access_key": self.api_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": round(time.time() * 1000),
        }
        if params:
            query = urllib.parse.urlencode(params)
            payload["query_hash"] = hashlib.sha512(query.encode("utf-8")).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        return jwt.encode(payload, self.secret_key)

    def _auth_headers(self, params: dict | None = None) -> dict:
        return {"Authorization": f"Bearer {self._token(params)}"}

    def get_balance(self) -> list:
        """전체 자산 조회. 반환: [{currency, balance, locked, ...}, ...]"""
        r = self.session.get(BASE + "/v1/accounts",
                             headers=self._auth_headers(), timeout=10)
        r.raise_for_status()
        return r.json()

    def market_buy(self, symbol: str, krw_amount: float) -> dict:
        """시장가 매수: 원화 금액(krw_amount)만큼 산다."""
        params = {"market": f"KRW-{symbol}", "side": "bid",
                  "order_type": "price", "price": str(int(krw_amount))}
        return self._order(params)

    def market_sell(self, symbol: str, units: float) -> dict:
        """시장가 매도: 수량(units)만큼 판다."""
        params = {"market": f"KRW-{symbol}", "side": "ask",
                  "order_type": "market", "volume": f"{units:.8f}"}
        return self._order(params)

    def _order(self, params: dict) -> dict:
        # 에러도 본문(JSON)으로 확인해야 하므로 raise_for_status 하지 않고 그대로 반환.
        r = self.session.post(BASE + "/v2/orders", json=params,
                              headers=self._auth_headers(params), timeout=10)
        return r.json()


def order_ok(resp: dict) -> bool:
    """주문 성공 여부. 성공=uuid 존재, 실패=error 키."""
    return isinstance(resp, dict) and "error" not in resp and "uuid" in resp


def parse_krw_available(balance: list) -> float:
    for a in balance:
        if a.get("currency") == "KRW":
            return float(a.get("balance", 0) or 0)
    return 0.0


def parse_units(balance: list, symbol: str) -> float:
    for a in balance:
        if a.get("currency") == symbol.upper():
            return float(a.get("balance", 0) or 0)
    return 0.0
