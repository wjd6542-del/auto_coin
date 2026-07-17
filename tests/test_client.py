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
