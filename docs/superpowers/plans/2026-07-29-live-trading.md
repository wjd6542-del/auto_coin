# 실거래(Live) 구현 계획 — 마일스톤 3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 검증된 추세추종 전략을 빗썸에서 실제 돈으로 자동 매매하되, 여러 겹의 안전장치로 위험을 통제한다.

**Architecture:** 페이퍼와 동일한 `strategy/`·`risk/` 코드를 재사용. 새 `bithumb/private.py`(인증 주문 API)와 `engine/live.py`(안전장치+실주문)를 추가하고, 대시보드에 실거래 페이지를 붙인다. 실주문은 4중 안전장치(활성화 플래그/투자상한/일일손실한도/비상정지)를 모두 통과해야만 나간다.

**Tech Stack:** Python 3.13, requests, SQLAlchemy 2.x, Streamlit, pytest

**Spec:** `docs/superpowers/specs/2026-07-29-live-trading-design.md`

## Global Constraints

- Python 3.11+, 표준 타입 힌트
- `.venv` 자동활성화 안 됨 → 모든 명령 `.venv/bin/` 접두사
- **실제 돈. 테스트는 절대 실 API로 주문하지 않는다** — 전부 mock/stub.
- 새 안전장치 설정 4종: `live_enabled(bool)=False`, `max_invest_krw(float)=300000`, `daily_loss_limit_pct(float)=0.05`, `kill_switch(bool)=False`
- 실주문 4중 게이트: kill_switch OFF **그리고** live_enabled ON **그리고** 일일손실 한도 이내 **그리고** 투자상한 이내
- API 키는 `config.Secrets`(.env)에서만. 로그·DB·화면 노출 금지.
- 빗썸 API 1.0 서명: `HMAC-SHA512(secret, endpoint + chr(0) + urlencode(params) + chr(0) + nonce)` → hex → base64
- git author `wjd6542`, 커밋 끝 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: 안전장치 설정 4종

**Files:**
- Modify: `config.py` (Settings에 4필드)
- Modify: `db/models.py` (AppSettings에 4컬럼)
- Modify: `db/store.py` (`_SETTINGS_FIELDS`에 4개 추가)
- Test: `tests/test_live_settings.py`

**Interfaces:**
- Produces: `Settings.live_enabled: bool=False`, `Settings.max_invest_krw: float=300000.0`, `Settings.daily_loss_limit_pct: float=0.05`, `Settings.kill_switch: bool=False`; `Store.get_settings()/save_settings()`가 이 4개도 저장·로드.

- [ ] **Step 1: 실패 테스트** — `tests/test_live_settings.py`

```python
from dataclasses import replace
from config import Settings
from db.store import Store


def test_live_settings_defaults(tmp_path):
    s = Store(str(tmp_path / "ls.db")); s.create_all()
    cfg = s.get_settings()
    assert cfg.live_enabled is False
    assert cfg.max_invest_krw == 300000.0
    assert cfg.daily_loss_limit_pct == 0.05
    assert cfg.kill_switch is False


def test_live_settings_roundtrip(tmp_path):
    s = Store(str(tmp_path / "ls.db")); s.create_all()
    s.get_settings()
    s.save_settings(replace(Settings(), live_enabled=True, kill_switch=True,
                            max_invest_krw=100000.0, daily_loss_limit_pct=0.03))
    got = s.get_settings()
    assert got.live_enabled is True and got.kill_switch is True
    assert got.max_invest_krw == 100000.0 and got.daily_loss_limit_pct == 0.03
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_live_settings.py -v`
Expected: FAIL (필드 없음)

- [ ] **Step 3: config 필드 추가** — `config.py` Settings, `fee_rate` 아래에 추가

```python
    # 실거래 안전장치
    live_enabled: bool = False          # True여야만 실주문
    max_invest_krw: float = 300000.0    # 총 투입 상한
    daily_loss_limit_pct: float = 0.05  # 일일 손실한도(초과 시 자동정지)
    kill_switch: bool = False           # 비상정지
```

- [ ] **Step 4: AppSettings 컬럼 추가** — `db/models.py`의 `AppSettings`에 추가

```python
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_invest_krw: Mapped[float] = mapped_column(Float, default=300000.0)
    daily_loss_limit_pct: Mapped[float] = mapped_column(Float, default=0.05)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 5: `_SETTINGS_FIELDS`에 추가** — `db/store.py`

```python
    _SETTINGS_FIELDS = (
        "short_period", "long_period", "rsi_period", "rsi_oversold",
        "rsi_recover", "use_rsi_filter", "trailing_stop_pct", "max_positions",
        "position_pct", "max_volume_pct", "top_n", "min_trade_value_krw",
        "initial_capital", "fee_rate",
        "live_enabled", "max_invest_krw", "daily_loss_limit_pct", "kill_switch",
    )
```

- [ ] **Step 6: 통과 + 회귀 + 커밋**

Run: `.venv/bin/pytest tests/test_live_settings.py -v` (PASS), 이어 `.venv/bin/pytest -q`
```bash
git add config.py db/models.py db/store.py tests/test_live_settings.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 실거래 안전장치 설정 4종 (live_enabled/max_invest_krw/daily_loss_limit_pct/kill_switch)"
```

- [ ] **Step 7: MySQL 운영 테이블에 컬럼 추가** (수동, 네트워크 필요)

Run:
```bash
.venv/bin/python -c "
from sqlalchemy import text
from db.store import Store
from config import database
s = Store(url=database.url())
with s.engine.begin() as c:
    cols = {r[0] for r in c.execute(text('SHOW COLUMNS FROM app_settings'))}
    adds = [('live_enabled','TINYINT(1) DEFAULT 0'),('max_invest_krw','FLOAT DEFAULT 300000'),
            ('daily_loss_limit_pct','FLOAT DEFAULT 0.05'),('kill_switch','TINYINT(1) DEFAULT 0')]
    for name,ddl in adds:
        if name not in cols:
            c.execute(text(f'ALTER TABLE app_settings ADD COLUMN {name} {ddl}'))
            print('added', name)
print('done')
"
```
Expected: 4개 컬럼 추가. (SQLite 테스트는 create_all이 처리하므로 무관)

---

### Task 2: 빗썸 인증 API (읽기전용 우선)

**Files:**
- Create: `bithumb/private.py`
- Test: `tests/test_private.py`

**Interfaces:**
- Produces:
  - `class BithumbPrivate(api_key, secret_key, session=None)`:
    - `get_balance(currency="ALL") -> dict` (`/info/balance`)
    - `market_buy(symbol, units) -> dict` (`/trade/market_buy`)
    - `market_sell(symbol, units) -> dict` (`/trade/market_sell`)
  - 모듈 함수: `parse_krw_available(balance: dict) -> float`, `parse_units(balance: dict, symbol: str) -> float`

- [ ] **Step 1: 실패 테스트** — `tests/test_private.py`

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_private.py -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현** — `bithumb/private.py`

```python
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
```

- [ ] **Step 4: 통과**

Run: `.venv/bin/pytest tests/test_private.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 실 API 읽기전용 스모크** (수동, 실제 키 필요, **주문 아님**)

Run:
```bash
.venv/bin/python -c "
from config import secrets
from bithumb.private import BithumbPrivate, parse_krw_available
api = BithumbPrivate(secrets.bithumb_api_key, secrets.bithumb_secret_key)
bal = api.get_balance()
print('status:', bal.get('status'))   # 0000 이면 인증 성공
print('KRW 가용:', parse_krw_available(bal))
"
```
Expected: `status: 0000` + 실제 KRW 잔고. `5100` 등 에러코드면 키/서명/권한 확인. **주문은 안 나감(읽기전용).**

- [ ] **Step 6: 회귀 + 커밋**

Run: `.venv/bin/pytest -q`
```bash
git add bithumb/private.py tests/test_private.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 빗썸 인증 API (잔고조회·시장가 주문, HMAC 서명)"
```

---

### Task 3: 실거래 엔진 (안전장치 + 실주문)

**Files:**
- Create: `engine/live.py`
- Test: `tests/test_live.py`

**Interfaces:**
- Consumes: `config.Settings`, `db.store.Store`, `risk.manager.RiskManager/Position`, `strategy.signals.evaluate`, `bithumb.private`(parse_krw_available/parse_units)
- Produces:
  - `safety_block_reason(settings, current_total, day_start_total) -> str | None` — 막는 사유(문자열) 또는 None(통과)
  - `class LiveTrader(settings, store, market_client, private_client, fee_rate=0.0004)`:
    - `run_once() -> dict` — 반환 `{"cash","positions","filled","total","blocked"}`. blocked는 안전장치 사유(없으면 None).
  - market_client: `get_top_symbols`, `get_daily_candles` (기존 BithumbClient)
  - private_client: `get_balance`, `market_buy`, `market_sell`

- [ ] **Step 1: 실패 테스트** — `tests/test_live.py`

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_live.py -v`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현** — `engine/live.py`

```python
from datetime import datetime

from config import Settings
from db.store import Store
from risk.manager import RiskManager, Position
from strategy.signals import evaluate
from bithumb.private import parse_krw_available, order_ok

MODE = "live"


def safety_block_reason(settings: Settings, current_total: float,
                        day_start_total: float) -> str | None:
    """실주문을 막아야 하면 사유 문자열, 통과면 None."""
    if settings.kill_switch:
        return "비상정지(kill_switch) 켜짐"
    if not settings.live_enabled:
        return "실거래 비활성(live_enabled=False)"
    if day_start_total > 0:
        loss = (current_total - day_start_total) / day_start_total
        if loss <= -settings.daily_loss_limit_pct:
            return f"일일 손실한도 초과 ({loss*100:.1f}%)"
    return None


def _day_start_total(store: Store) -> float:
    """오늘 첫 balance_log(mode=live) 총자산. 없으면 0."""
    b = store.balance_df()
    b = b[b["mode"] == MODE]
    if b.empty:
        return 0.0
    today = datetime.now().date()
    b = b[b["ts"].apply(lambda t: t.date() == today)]
    return float(b.iloc[0]["total_krw"]) if not b.empty else 0.0


class LiveTrader:
    def __init__(self, settings: Settings, store: Store, market_client,
                 private_client, fee_rate: float = 0.0004):
        self.settings = settings
        self.store = store
        self.market = market_client
        self.private = private_client
        self.fee_rate = fee_rate
        self.risk = RiskManager(settings)

    def _current_total(self, cash: float, positions: dict, candles: dict) -> float:
        holdings = sum(
            pos.qty * float(candles[s]["close"].iloc[-1])
            for s, pos in positions.items() if s in candles)
        return cash + holdings

    def run_once(self) -> dict:
        positions = self.store.get_positions(MODE)

        # 시세 수집 (후보 + 보유)
        symbols = self.market.get_top_symbols(
            self.settings.top_n, self.settings.min_trade_value_krw)
        candles: dict = {}
        for symbol in set(symbols) | set(positions):
            try:
                df = self.market.get_daily_candles(symbol)
                if len(df) >= self.settings.long_period + 1:
                    candles[symbol] = df
            except Exception as e:
                print(f"skip {symbol}: {e}")

        # 실잔고 조회
        balance = self.private.get_balance()
        cash = parse_krw_available(balance)
        total = self._current_total(cash, positions, candles)

        # 안전장치
        blocked = safety_block_reason(self.settings, total, _day_start_total(self.store))
        self.store.add_balance(ts=datetime.now(), total_krw=total,
                               cash_krw=cash,
                               holdings_krw=total - cash, mode=MODE)
        if blocked:
            print(f"실거래 차단: {blocked}")
            return {"cash": cash, "positions": len(positions),
                    "filled": 0, "total": total, "blocked": blocked}

        filled = 0
        holdings_value = total - cash

        # 1) 청산
        for symbol in list(positions.keys()):
            if symbol not in candles:
                continue
            price = float(candles[symbol]["close"].iloc[-1])
            pos = positions[symbol]
            self.risk.update_high(pos, price)
            self.store.update_position_high(symbol, MODE, pos.high_price)
            sig = evaluate(candles[symbol], self.settings, in_position=True)
            hit_stop = self.risk.hit_trailing_stop(pos, price)
            if hit_stop or sig.action == "sell":
                resp = self.private.market_sell(symbol, pos.qty)
                if not order_ok(resp):
                    print(f"매도 실패 {symbol}: {resp}")
                    continue
                loss_pct = (price / pos.entry_price - 1) * 100
                note = (f"트레일링스톱 매도 (손익 {loss_pct:+.1f}%)" if hit_stop
                        else f"데드크로스 매도 (손익 {loss_pct:+.1f}%)")
                self.store.add_trade(ts=datetime.now(), symbol=symbol, side="sell",
                                     price=price, qty=pos.qty,
                                     fee=pos.qty * price * self.fee_rate,
                                     note=note, mode=MODE)
                self.store.remove_position(symbol, MODE)
                del positions[symbol]
                filled += 1

        # 2) 진입 (투자상한 이내)
        for symbol in sorted(candles.keys()):
            if symbol in positions or not self.risk.can_enter(positions):
                continue
            sig = evaluate(candles[symbol], self.settings, in_position=False)
            if sig.action != "buy":
                continue
            price = float(candles[symbol]["close"].iloc[-1])
            daily_value = price * float(candles[symbol]["volume"].iloc[-1])
            room = self.settings.max_invest_krw - holdings_value
            budget = min(cash, room)
            qty = self.risk.position_size(budget, price, daily_value)
            cost = qty * price * (1 + self.fee_rate)
            if qty <= 0 or cost > cash or cost < 5000:   # 빗썸 최소주문 ~5000원
                continue
            krw_to_spend = qty * price   # 시장가 매수는 금액 기준
            resp = self.private.market_buy(symbol, krw_to_spend)
            if not order_ok(resp):
                print(f"매수 실패 {symbol}: {resp}")
                continue
            cash -= cost
            holdings_value += qty * price
            new_pos = Position(symbol, price, qty, price)
            positions[symbol] = new_pos
            self.store.add_position(new_pos, MODE)
            note = f"골든크로스 매수 (RSI {sig.reason.get('rsi', 0):.0f})"
            self.store.add_trade(ts=datetime.now(), symbol=symbol, side="buy",
                                 price=price, qty=qty,
                                 fee=qty * price * self.fee_rate,
                                 note=note, mode=MODE)
            filled += 1

        return {"cash": cash, "positions": len(positions),
                "filled": filled, "total": total, "blocked": None}
```

- [ ] **Step 4: 통과**

Run: `.venv/bin/pytest tests/test_live.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 회귀 + 커밋**

Run: `.venv/bin/pytest -q`
```bash
git add engine/live.py tests/test_live.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 실거래 엔진 (4중 안전장치 + 실주문)"
```

---

### Task 4: CLI `--mode live`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py` (live 케이스 추가)

**Interfaces:**
- Consumes: `engine.live.LiveTrader`, `bithumb.private.BithumbPrivate`, `config.secrets`
- Produces: `run_live(market_client, private_client, store, settings) -> dict`; `--mode live` 분기

- [ ] **Step 1: 실패 테스트** — `tests/test_main.py` 하단에 추가

```python
def test_run_live_blocked_when_disabled(tmp_path):
    import pandas as pd
    from db.store import Store
    from config import Settings
    from main import run_live

    class MarketStub:
        def get_top_symbols(self, top_n, mv): return ["AAA"]
        def get_daily_candles(self, s):
            closes = [100, 95, 90, 85, 80, 78, 85, 95]
            idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
            return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                                 "close": closes, "volume": [1e6]*len(closes)}, index=idx)

    class PrivateStub:
        def get_balance(self):
            return [{"currency": "KRW", "balance": "300000"}]
        def market_buy(self, s, krw): return {"uuid": "x"}
        def market_sell(self, s, u): return {"uuid": "x"}

    store = Store(str(tmp_path / "ml.db")); store.create_all()
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 live_enabled=False)
    out = run_live(MarketStub(), PrivateStub(), store, s)
    assert out["blocked"] == "실거래 비활성(live_enabled=False)"
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_main.py::test_run_live_blocked_when_disabled -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `main.py`

상단 import 추가: `from engine.live import LiveTrader`, `from bithumb.private import BithumbPrivate`, `from config import secrets`.
```python
def run_live(market_client, private_client, store, settings) -> dict:
    return LiveTrader(settings, store, market_client, private_client,
                      fee_rate=settings.fee_rate).run_once()
```
argparse choices에 `"live"` 추가, 분기 추가:
```python
    elif args.mode == "live":
        store = Store(url=database.url())
        store.create_all()
        settings = store.get_settings()
        private = BithumbPrivate(secrets.bithumb_api_key, secrets.bithumb_secret_key)
        summary = run_live(BithumbClient(), private, store, settings)
        if summary["blocked"]:
            print(f"⛔ 실거래 차단: {summary['blocked']}")
        print(f"현금: {summary['cash']:,.0f} KRW / 보유 {summary['positions']}종목 "
              f"/ 체결 {summary['filled']}건 / 총자산 {summary['total']:,.0f} KRW")
```
choices: `choices=["backtest", "tune", "paper", "live"]`

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `.venv/bin/pytest tests/test_main.py -v` 후 `.venv/bin/pytest -q`
```bash
git add main.py tests/test_main.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: CLI --mode live (안전장치 차단 표시)"
```

---

### Task 5: 대시보드 실거래 페이지

**Files:**
- Modify: `dashboard/app.py`
- Test: `tests/test_dashboard.py` (실거래 헬퍼 테스트 추가)

**Interfaces:**
- Produces: `live_safety_badge(settings) -> str` (실거래 상태 요약 문자열); 대시보드 모드에 "live" 추가 + 안전장치 토글/버튼.

- [ ] **Step 1: 실패 테스트** — `tests/test_dashboard.py`에 추가

```python
def test_live_safety_badge():
    from config import Settings
    from dashboard.app import live_safety_badge
    on = live_safety_badge(Settings(live_enabled=True, kill_switch=False))
    off = live_safety_badge(Settings(live_enabled=False, kill_switch=False))
    kill = live_safety_badge(Settings(live_enabled=True, kill_switch=True))
    assert "실거래 ON" in on
    assert "실거래 OFF" in off
    assert "비상정지" in kill
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_live_safety_badge -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `dashboard/app.py`

`live_safety_badge` 함수 추가:
```python
def live_safety_badge(settings: Settings) -> str:
    if settings.kill_switch:
        return "🛑 비상정지 켜짐 — 거래 중단"
    if settings.live_enabled:
        return "🟢 실거래 ON — 진짜 돈으로 매매 중"
    return "⚪ 실거래 OFF — 판단만(주문 안 함)"
```
`render()`의 모드 선택에 `"live"` 추가:
```python
    mode = st.radio("모드", ["backtest", "paper", "live"], horizontal=True,
                    format_func=lambda m: {"backtest": "백테스트",
                                           "paper": "페이퍼(실시간 가상)",
                                           "live": "💰 실거래"}[m])
```
`if mode == "live":` 블록 추가 (mode==paper 블록 아래):
```python
    if mode == "live":
        st.error("⚠️ 실거래 페이지 — 진짜 돈으로 거래됩니다.")
        cs = load_settings(store)
        st.info(live_safety_badge(cs))
        col1, col2 = st.columns(2)
        with col1:
            new_enabled = st.toggle("실거래 활성화 (live_enabled)", cs.live_enabled)
        with col2:
            new_kill = st.toggle("🛑 비상정지 (kill_switch)", cs.kill_switch)
        if new_enabled != cs.live_enabled or new_kill != cs.kill_switch:
            from dataclasses import replace
            store.save_settings(replace(cs, live_enabled=new_enabled, kill_switch=new_kill))
            st.rerun()
        st.caption(f"투자 상한 {cs.max_invest_krw:,.0f}원 · 일일 손실한도 "
                   f"{cs.daily_loss_limit_pct*100:.0f}%")
        if st.button("▶️ 실거래 지금 실행", type="primary"):
            try:
                from bithumb.private import BithumbPrivate
                from bithumb.client import BithumbClient
                from config import secrets as _sec
                from engine.live import LiveTrader
                with st.spinner("실잔고 조회 후 매매 판단 중..."):
                    priv = BithumbPrivate(_sec.bithumb_api_key, _sec.bithumb_secret_key)
                    res = LiveTrader(cs, store, BithumbClient(), priv,
                                     fee_rate=cs.fee_rate).run_once()
                if res["blocked"]:
                    st.warning(f"차단됨: {res['blocked']}")
                else:
                    st.success(f"실행 완료 — 현금 {res['cash']:,.0f}원 / "
                               f"보유 {res['positions']}종목 / 체결 {res['filled']}건")
            except Exception as e:
                st.error(f"실행 실패: {e}")
```
(실거래 모드에서도 기존 balance/trades/holdings/거래내역 표는 `load_data(store, mode="live")`로 그대로 표시된다. mode 변수만 "live"로 흐르면 됨.)

- [ ] **Step 4: 통과 + import 확인 + 회귀 + 커밋**

Run: `.venv/bin/pytest tests/test_dashboard.py -v` ; `.venv/bin/python -c "import dashboard.app"` ; `.venv/bin/pytest -q`
```bash
git add dashboard/app.py tests/test_dashboard.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 대시보드 실거래 페이지 (안전장치 토글·실행버튼·경고)"
```

---

## Self-Review

**스펙 커버리지:** 안전장치 4종(Task1) ✅, 빗썸 인증API(Task2) ✅, 실거래 엔진+4중 게이트(Task3) ✅, CLI(Task4) ✅, 대시보드 실거래 페이지(Task5) ✅. 단계별 출시(읽기전용 스모크=Task2 Step5, 소액주문=수동, 자동ON=대시보드 토글) 반영.

**플레이스홀더:** 없음. 모든 스텝에 실제 코드·명령.

**타입 일관성:** `safety_block_reason(settings, current_total, day_start_total) -> str|None`, `LiveTrader.run_once()->dict{cash,positions,filled,total,blocked}`, `BithumbPrivate.get_balance/market_buy/market_sell`, `parse_krw_available/parse_units`, `_SETTINGS_FIELDS` 18개가 config/모델/엔진/대시보드에서 일치.

**주의:**
- 실 API 테스트 전무(전부 mock). 실 검증은 Task2 Step5(읽기전용) → 수동 소액주문 → 대시보드 토글 순.
- v1은 시장가 즉시체결 가정(체결가=최신종가). 부분체결·실체결가 정밀 반영은 후속.
- 일일손실한도는 balance_log(mode=live) 오늘 첫 기록 기준. 첫날은 baseline 없어 미발동.
