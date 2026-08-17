from bithumb.private import BithumbPrivate, parse_krw_available, parse_units


class FakeResp:
    def __init__(self, payload): self._p = payload
    def json(self): return self._p
    def raise_for_status(self): pass


class FakeSession:
    def __init__(self, payload):
        self._p = payload
        self.last = {}
    def post(self, url, data=None, headers=None, timeout=None):
        self.last = {"url": url, "data": data, "headers": headers}
        return FakeResp(self._p)


def test_get_balance_sends_auth_headers():
    payload = {"status": "0000",
               "data": {"available_krw": "300000", "total_krw": "300000",
                        "available_eth": "0.5", "total_eth": "0.5"}}
    sess = FakeSession(payload)
    api = BithumbPrivate("KEY", "SECRET", session=sess)
    out = api.get_balance()
    assert out["status"] == "0000"
    # 인증 헤더 3종 존재
    h = sess.last["headers"]
    assert h["Api-Key"] == "KEY"
    assert h["Api-Nonce"].isdigit()
    assert h["Api-Sign"]                      # 비어있지 않음
    assert sess.last["url"].endswith("/info/balance")
    assert sess.last["data"]["endpoint"] == "/info/balance"


def test_parse_balance_helpers():
    payload = {"status": "0000",
               "data": {"available_krw": "300000", "available_eth": "0.5"}}
    assert parse_krw_available(payload) == 300000.0
    assert parse_units(payload, "ETH") == 0.5
    assert parse_units(payload, "BTC") == 0.0    # 없으면 0


def test_market_buy_posts_units():
    payload = {"status": "0000", "order_id": "123"}
    sess = FakeSession(payload)
    api = BithumbPrivate("KEY", "SECRET", session=sess)
    api.market_buy("ETH", 0.073828)
    d = sess.last["data"]
    assert d["endpoint"] == "/trade/market_buy"
    assert d["order_currency"] == "ETH"
    assert d["payment_currency"] == "KRW"
    assert float(d["units"]) == 0.073828


def test_sign_is_deterministic():
    api = BithumbPrivate("KEY", "SECRET")
    s1 = api._sign("/info/balance", {"endpoint": "/info/balance"}, "1000")
    s2 = api._sign("/info/balance", {"endpoint": "/info/balance"}, "1000")
    assert s1 == s2 and len(s1) > 0
