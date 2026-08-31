import pandas as pd
from bithumb.client import BithumbClient


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.last_url = None

    def get(self, url, timeout=None):
        self.last_url = url
        return FakeResp(self._payload)


def test_get_top_symbols_ranks_and_filters():
    payload = {
        "status": "0000",
        "data": {
            "BTC": {"acc_trade_value_24H": "5000000000"},
            "ETH": {"acc_trade_value_24H": "3000000000"},
            "DOGE": {"acc_trade_value_24H": "500000000"},  # 필터 미달
            "date": "1700000000000",
        },
    }
    client = BithumbClient(session=FakeSession(payload))
    result = client.get_top_symbols(top_n=10, min_trade_value=1_000_000_000)
    assert result == ["BTC", "ETH"]


def test_get_daily_candles_parses_ohlcv():
    payload = {
        "status": "0000",
        "data": [
            ["1700000000000", "100", "110", "115", "95", "10"],
            ["1700086400000", "110", "120", "125", "108", "12"],
        ],
    }
    client = BithumbClient(session=FakeSession(payload))
    df = client.get_daily_candles("BTC")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.iloc[0]["close"] == 110.0   # 배열의 2번째가 close
    assert df.iloc[0]["high"] == 115.0
    assert df.index.is_monotonic_increasing


def test_get_marketcap_symbols_filters_junk_and_stables():
    from bithumb.client import BithumbClient
    class Resp:
        def __init__(self, p): self._p = p
        def json(self): return self._p
        def raise_for_status(self): pass
    class Sess:
        def get(self, url, params=None, timeout=None):
            if "ticker" in url:
                return Resp({"status": "0000", "data": {
                    "BTC": {"acc_trade_value_24H": "5000000000"},
                    "ETH": {"acc_trade_value_24H": "3000000000"},
                    "JUNK": {"acc_trade_value_24H": "2000000000"},  # 유동성O 시총X
                    "date": "1700000000000"}})
            return Resp([{"symbol": "btc", "market_cap": 3},
                         {"symbol": "eth", "market_cap": 2},
                         {"symbol": "usdt", "market_cap": 4},   # 스테이블 제외
                         {"symbol": "xyz", "market_cap": 1}])   # 빗썸에 없음
    syms = BithumbClient(session=Sess()).get_marketcap_symbols(10, 1_000_000_000)
    assert syms == ["BTC", "ETH"]   # JUNK(시총밖)·USDT(스테이블)·XYZ(빗썸없음) 제외


def test_select_universe_fallback_without_marketcap():
    from bithumb.client import select_universe
    class Stub:
        def get_top_symbols(self, n, v): return ["A", "B"]
    class S:
        use_market_cap = True; top_n = 10; min_trade_value_krw = 0
    assert select_universe(Stub(), S()) == ["A", "B"]   # 스텁엔 시총메서드 없음 → 폴백


def test_select_universe_uses_trade_value_when_disabled():
    from bithumb.client import select_universe
    class Client:
        def get_top_symbols(self, n, v): return ["TV"]
        def get_marketcap_symbols(self, n, v): return ["MC"]
    class S:
        use_market_cap = False; top_n = 10; min_trade_value_krw = 0
    assert select_universe(Client(), S()) == ["TV"]
