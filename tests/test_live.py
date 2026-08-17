from datetime import datetime

import pandas as pd

from config import Settings
from db.store import Store
from risk.manager import Position
from engine.live import LiveTrader, safety_block_reason, _loss_baseline


def _series(closes, vol=1_000_000.0):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [vol] * len(closes)}, index=idx)


class MarketStub:
    def __init__(self, candles):
        self._c = candles
    def get_top_symbols(self, top_n, min_trade_value):
        return list(self._c)
    def get_daily_candles(self, symbol):
        return self._c[symbol]


class PrivateStub:
    """빗썸 인증 API 스텁. 매수 시 buy_fill 만큼 잔고에 코인이 잡히도록 시뮬."""
    def __init__(self, krw, units=None, buy_fill=None):
        self.krw = krw
        self.units = dict(units or {})
        self.buy_fill = dict(buy_fill or {})
        self.orders = []
    def get_balance(self):
        bal = [{"currency": "KRW", "balance": str(self.krw)}]
        for sym, u in self.units.items():
            bal.append({"currency": sym.upper(), "balance": str(u)})
        return bal
    def market_buy(self, symbol, krw_amount):
        self.orders.append(("buy", symbol, krw_amount))
        if symbol in self.buy_fill:
            self.units[symbol] = self.units.get(symbol, 0.0) + self.buy_fill[symbol]
        return {"order_id": "x"}
    def market_sell(self, symbol, units):
        self.orders.append(("sell", symbol, units))
        self.units[symbol] = 0.0
        return {"order_id": "x"}


def _store(tmp_path):
    s = Store(str(tmp_path / "live.db")); s.create_all(); return s


UP = [100, 95, 90, 85, 80, 78, 85, 95]        # 마지막 봉 골든크로스
DOWN = [80, 90, 100, 110, 120, 118, 105, 92]  # 마지막 봉 데드크로스


# ---- 안전장치 순수함수 ----

def test_safety_block_kill_switch():
    assert safety_block_reason(Settings(kill_switch=True, live_enabled=True),
                               100000, 100000) == "비상정지(kill_switch) 켜짐"


def test_safety_block_not_enabled():
    assert safety_block_reason(Settings(live_enabled=False),
                               100000, 100000) == "실거래 비활성(live_enabled=False)"


def test_safety_block_daily_loss():
    r = safety_block_reason(Settings(live_enabled=True, daily_loss_limit_pct=0.05),
                            94000, 100000)
    assert "일일 손실한도" in r


def test_safety_pass():
    assert safety_block_reason(Settings(live_enabled=True, daily_loss_limit_pct=0.05),
                               98000, 100000) is None


# ---- I-1: 손실 기준선 ----

def test_loss_baseline_uses_prior_record(tmp_path):
    store = _store(tmp_path)
    store.add_balance(ts=datetime(2020, 1, 1), total_krw=100000.0,
                      cash_krw=100000.0, holdings_krw=0.0, mode="live")
    # 오늘 기록이 없으면 직전(어제) 마지막 총자산을 기준선으로
    assert _loss_baseline(store) == 100000.0


def test_loss_baseline_empty_is_zero(tmp_path):
    assert _loss_baseline(_store(tmp_path)) == 0.0


# ---- 차단 동작 ----

def test_disabled_live_does_not_order(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False, live_enabled=False)
    priv = PrivateStub(krw=300000)
    out = LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    assert out["blocked"] == "실거래 비활성(live_enabled=False)"
    assert priv.orders == []


def test_blocked_records_balance_but_no_orders(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, kill_switch=True)
    priv = PrivateStub(krw=300000)
    out = LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    assert out["blocked"] == "비상정지(kill_switch) 켜짐"
    assert priv.orders == []
    b = store.balance_df()
    assert len(b[b["mode"] == "live"]) == 1


# ---- I-2: 손실한도 초과 시 kill_switch 래치 ----

def test_loss_limit_latches_kill_switch(tmp_path):
    store = _store(tmp_path)
    store.get_settings()  # app_settings 행 초기화
    store.add_balance(ts=datetime(2020, 1, 1), total_krw=100000.0,
                      cash_krw=100000.0, holdings_krw=0.0, mode="live")
    s = Settings(live_enabled=True, daily_loss_limit_pct=0.05)
    priv = PrivateStub(krw=90000)   # 오늘 총자산 90000 = 직전 대비 -10%
    out = LiveTrader(s, store, MarketStub({}), priv).run_once()
    assert out["blocked"].startswith("일일 손실한도")
    assert store.get_settings().kill_switch is True     # 자동 래치됨


# ---- 진입 ----

def test_enabled_live_places_buy(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, max_invest_krw=300000, position_pct=0.20)
    priv = PrivateStub(krw=300000)
    out = LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    assert out["blocked"] is None
    assert any(o[0] == "buy" and o[1] == "AAA" for o in priv.orders)
    assert len(store.trades_df()) == 1
    assert "AAA" in store.get_positions("live")


def test_max_invest_krw_caps_buy(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, max_invest_krw=10000, position_pct=1.0)
    priv = PrivateStub(krw=1_000_000)
    LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    buys = [o for o in priv.orders if o[0] == "buy"]
    assert len(buys) == 1
    assert buys[0][2] <= 10000.5           # 상한 이하로 캡핑


# ---- I-3: 체결 재확인 (실수량 반영) ----

def test_buy_records_actual_filled_qty(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=True, max_invest_krw=300000, position_pct=0.20)
    # 매수 후 잔고에 실제로 0.5개만 잡힘(추정치와 다름)
    priv = PrivateStub(krw=300000, buy_fill={"AAA": 0.5})
    LiveTrader(s, store, MarketStub({"AAA": _series(UP)}), priv).run_once()
    pos = store.get_positions("live")["AAA"]
    assert pos.qty == 0.5                   # 잔고 실체결 수량 기록


def test_sell_uses_actual_held_units(tmp_path):
    store = _store(tmp_path)
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False, live_enabled=True)
    # DB엔 1.0 보유로 기록됐지만 실제 잔고엔 0.4만 (수수료 등)
    store.add_position(Position("BBB", entry_price=100.0, qty=1.0, high_price=200.0), "live")
    priv = PrivateStub(krw=0, units={"BBB": 0.4})
    LiveTrader(s, store, MarketStub({"BBB": _series(DOWN)}), priv).run_once()
    sells = [o for o in priv.orders if o[0] == "sell"]
    assert len(sells) == 1
    assert sells[0][2] == 0.4               # 실보유(0.4) 매도, DB의 1.0 아님


# ---- I-4: 잔고조회 실패 시 안전 중단 ----

def test_balance_fetch_failure_blocks(tmp_path):
    store = _store(tmp_path)
    class FailPrivate:
        def get_balance(self):
            raise RuntimeError("network")
    out = LiveTrader(Settings(live_enabled=True), store,
                     MarketStub({"AAA": _series(UP)}), FailPrivate()).run_once()
    assert out["blocked"] == "잔고조회 실패"


# ---- 시세 누락 평가 폴백 ----

def test_current_total_falls_back_to_entry_price(tmp_path):
    store = _store(tmp_path)
    trader = LiveTrader(Settings(), store, MarketStub({}), PrivateStub(krw=0))
    positions = {"XXX": Position("XXX", entry_price=100.0, qty=10.0, high_price=100.0)}
    assert trader._current_total(500.0, positions, {}) == 1500.0
