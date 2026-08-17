import pandas as pd
from config import Settings
from db.store import Store
from engine.live import LiveTrader, safety_block_reason


def _series(closes, vol=1_000_000.0):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [vol]*len(closes)}, index=idx)


class MarketStub:
    def __init__(self, candles): self._c = candles
    def get_top_symbols(self, top_n, min_trade_value): return list(self._c)
    def get_daily_candles(self, symbol): return self._c[symbol]


class PrivateStub:
    def __init__(self, krw, units=None):
        self._krw = krw
        self._units = units or {}
        self.orders = []
    def get_balance(self):
        bal = [{"currency": "KRW", "balance": str(self._krw)}]
        for sym, u in self._units.items():
            bal.append({"currency": sym.upper(), "balance": str(u)})
        return bal
    def market_buy(self, symbol, krw_amount):
        self.orders.append(("buy", symbol, krw_amount)); return {"uuid": "x"}
    def market_sell(self, symbol, units):
        self.orders.append(("sell", symbol, units)); return {"uuid": "x"}


def _store(tmp_path):
    s = Store(str(tmp_path / "live.db")); s.create_all(); return s


UP = [100, 95, 90, 85, 80, 78, 85, 95]   # 마지막 봉 골든크로스


def test_safety_block_kill_switch():
    s = Settings(kill_switch=True, live_enabled=True)
    assert safety_block_reason(s, 100000, 100000) == "비상정지(kill_switch) 켜짐"


def test_safety_block_not_enabled():
    s = Settings(live_enabled=False)
    assert safety_block_reason(s, 100000, 100000) == "실거래 비활성(live_enabled=False)"


def test_safety_block_daily_loss():
    s = Settings(live_enabled=True, daily_loss_limit_pct=0.05)
    # 하루 시작 100000 → 현재 94000 (-6% < -5%)
    assert "일일 손실한도" in safety_block_reason(s, 94000, 100000)


def test_safety_pass():
    s = Settings(live_enabled=True, daily_loss_limit_pct=0.05)
    assert safety_block_reason(s, 98000, 100000) is None


def test_disabled_live_does_not_order(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=False)
    priv = PrivateStub(krw=300000)
    trader = LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv)
    out = trader.run_once()
    assert out["blocked"] == "실거래 비활성(live_enabled=False)"
    assert priv.orders == []            # 주문 안 나감


def test_enabled_live_places_buy(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, max_invest_krw=300000, position_pct=0.20)
    priv = PrivateStub(krw=300000)
    trader = LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv)
    out = trader.run_once()
    assert out["blocked"] is None
    assert any(o[0] == "buy" and o[1] == "AAA" for o in priv.orders)
    assert len(store.trades_df()) == 1
    assert "AAA" in store.get_positions("live")


def test_current_total_falls_back_to_entry_price(tmp_path):
    from risk.manager import Position
    store = _store(tmp_path)
    trader = LiveTrader(Settings(), store, MarketStub({}), PrivateStub(krw=0))
    positions = {"XXX": Position("XXX", entry_price=100.0, qty=10.0, high_price=100.0)}
    # XXX가 시세(candles)에 없어도 평단으로 평가 → 500 + 100*10 = 1500
    assert trader._current_total(500.0, positions, {}) == 1500.0


def test_max_invest_krw_caps_buy(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, max_invest_krw=10000, position_pct=1.0)
    priv = PrivateStub(krw=1_000_000)
    LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    buys = [o for o in priv.orders if o[0] == "buy"]
    assert len(buys) == 1
    assert buys[0][2] <= 10000.5          # 상한(10000) 이하로 캡핑


def test_blocked_records_balance_but_no_orders(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, kill_switch=True)
    priv = PrivateStub(krw=300000)
    out = LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    assert out["blocked"] == "비상정지(kill_switch) 켜짐"
    assert priv.orders == []               # 주문 0건
    b = store.balance_df()
    assert len(b[b["mode"] == "live"]) == 1  # 차단돼도 잔고는 기록
