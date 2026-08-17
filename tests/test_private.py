from bithumb.private import (
    BithumbPrivate, order_ok, parse_krw_available, parse_units,
)


class FakeResp:
    def __init__(self, payload):
        self._p = payload
    def json(self):
        return self._p
    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, payload):
        self._p = payload
        self.last = {}
    def get(self, url, headers=None, timeout=None):
        self.last = {"method": "GET", "url": url, "headers": headers}
        return FakeResp(self._p)
    def post(self, url, json=None, headers=None, timeout=None):
        self.last = {"method": "POST", "url": url, "json": json, "headers": headers}
        return FakeResp(self._p)


def test_get_balance_uses_jwt_bearer():
    payload = [{"currency": "KRW", "balance": "300000", "locked": "0"},
               {"currency": "ETH", "balance": "0.5", "locked": "0"}]
    sess = FakeSession(payload)
    api = BithumbPrivate("KEY", "SECRET", session=sess)
    out = api.get_balance()
    assert out[0]["currency"] == "KRW"
    assert sess.last["url"].endswith("/v1/accounts")
    auth = sess.last["headers"]["Authorization"]
    assert auth.startswith("Bearer ")            # JWT Bearer 토큰
    assert len(auth) > len("Bearer ")


def test_parse_balance_from_list():
    bal = [{"currency": "KRW", "balance": "300000"},
           {"currency": "ETH", "balance": "0.5"}]
    assert parse_krw_available(bal) == 300000.0
    assert parse_units(bal, "ETH") == 0.5
    assert parse_units(bal, "BTC") == 0.0        # 없으면 0


def test_market_buy_posts_price_amount():
    sess = FakeSession({"uuid": "abc"})
    api = BithumbPrivate("KEY", "SECRET", session=sess)
    api.market_buy("ETH", 30000)
    j = sess.last["json"]
    assert sess.last["url"].endswith("/v2/orders")
    assert j["market"] == "KRW-ETH"
    assert j["side"] == "bid"
    assert j["order_type"] == "price"
    assert j["price"] == "30000"                 # 시장가 매수는 금액
    assert "volume" not in j


def test_market_sell_posts_volume():
    sess = FakeSession({"uuid": "abc"})
    api = BithumbPrivate("KEY", "SECRET", session=sess)
    api.market_sell("ETH", 0.073828)
    j = sess.last["json"]
    assert j["market"] == "KRW-ETH"
    assert j["side"] == "ask"
    assert j["order_type"] == "market"
    assert float(j["volume"]) == 0.073828         # 시장가 매도는 수량
    assert "price" not in j


def test_order_ok():
    assert order_ok({"uuid": "abc", "market": "KRW-ETH"}) is True
    assert order_ok({"error": {"name": "x", "message": "y"}}) is False
    assert order_ok({}) is False


def test_query_hash_included_for_orders():
    # 파라미터 있는 요청은 JWT에 query_hash가 들어가야 함 (디코드해서 확인)
    import jwt as _jwt
    sess = FakeSession({"uuid": "abc"})
    api = BithumbPrivate("KEY", "SECRET", session=sess)
    api.market_sell("ETH", 1.0)
    token = sess.last["headers"]["Authorization"].removeprefix("Bearer ")
    decoded = _jwt.decode(token, "SECRET", algorithms=["HS256"])
    assert "query_hash" in decoded and decoded["query_hash_alg"] == "SHA512"
    assert decoded["access_key"] == "KEY"
