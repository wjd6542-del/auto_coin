# 코인 자동매매 봇 — 마일스톤 1 구현 계획 (백테스트 가능한 봇)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 빗썸 상위 100종목의 일봉 데이터로 이평선 크로스 + RSI 전략을 백테스트하고, 결과를 DB에 저장해 Streamlit 대시보드로 확인할 수 있는 봇을 만든다.

**Architecture:** 전략·리스크·데이터·실행을 독립 모듈로 분리한다. 이번 마일스톤은 `engine/backtest.py`가 데이터→신호→리스크→가상체결→DB저장을 조율한다. 동일한 `strategy/`·`risk/` 코드를 이후 페이퍼·실거래에서 재사용한다.

**Tech Stack:** Python 3.13, pandas, requests, SQLAlchemy 2.x, Streamlit, pytest

## Global Constraints

- Python 3.11+ (개발 환경 3.13). 표준 타입 힌트 사용 (`list[str]`, `X | None`).
- 외부 지표 라이브러리(TA-Lib 등) 사용 안 함 — 지표는 pandas로 직접 계산 (바이너리 의존성 회피).
- 캔들 데이터는 항상 pandas DataFrame, 컬럼 `['open','high','low','close','volume']`, 인덱스는 `DatetimeIndex`(과거→최신 오름차순).
- 코인 심볼은 결제통화 없는 base 심볼 문자열 (`'BTC'`, `'ETH'`). 결제통화는 KRW 고정.
- 모든 금액은 KRW, `float` 사용 (백테스트 한정; 실거래 단계에서 Decimal 재검토).
- 전략 파라미터는 전부 `config.py`의 dataclass에 모아 하드코딩 금지.
- API 키/시크릿은 코드에 넣지 않는다. 이번 마일스톤은 공개 API만 사용하므로 키 불필요.
- TDD: 각 태스크는 실패 테스트 → 최소 구현 → 통과 → 커밋 순서.

---

### Task 0: 프로젝트 스캐폴딩

**Files:**
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `config.py`
- Create: `conftest.py`
- Create: `bithumb/__init__.py`, `strategy/__init__.py`, `risk/__init__.py`, `db/__init__.py`, `engine/__init__.py`, `dashboard/__init__.py`, `tests/__init__.py`

**Interfaces:**
- Produces: `config.Settings` dataclass with fields — `short_period:int=20`, `long_period:int=60`, `rsi_period:int=14`, `rsi_oversold:float=30`, `rsi_recover:float=40`, `trailing_stop_pct:float=0.05`, `max_positions:int=4`, `position_pct:float=0.20`, `top_n:int=100`, `min_trade_value_krw:float=1_000_000_000`, `db_path:str="coin.db"`, `initial_capital:float=1_000_000`.

- [ ] **Step 1: git 저장소 초기화**

```bash
cd /Users/wjd/프로젝트/coin
git init
```

- [ ] **Step 2: `.gitignore` 작성** (API 키·DB·가상환경 보호)

```
__pycache__/
*.pyc
.venv/
venv/
*.db
.env
secrets.py
.pytest_cache/
.DS_Store
```

- [ ] **Step 3: 가상환경 생성 + 활성화**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

- [ ] **Step 4: `requirements.txt` 작성 후 설치**

```
pandas>=2.2
requests>=2.32
SQLAlchemy>=2.0
streamlit>=1.40
pytest>=8.0
```

Run: `pip install -r requirements.txt`
Expected: 설치 성공, 에러 없음.

- [ ] **Step 5: 패키지 디렉토리와 빈 `__init__.py` 생성**

```bash
mkdir -p bithumb strategy risk db engine dashboard tests
touch bithumb/__init__.py strategy/__init__.py risk/__init__.py db/__init__.py engine/__init__.py dashboard/__init__.py tests/__init__.py
```

- [ ] **Step 6: `config.py` 작성**

```python
from dataclasses import dataclass


@dataclass
class Settings:
    short_period: int = 20
    long_period: int = 60
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_recover: float = 40.0
    trailing_stop_pct: float = 0.05
    max_positions: int = 4
    position_pct: float = 0.20
    top_n: int = 100
    min_trade_value_krw: float = 1_000_000_000.0
    db_path: str = "coin.db"
    initial_capital: float = 1_000_000.0


settings = Settings()
```

- [ ] **Step 7: `conftest.py` 작성** (프로젝트 루트를 import path에 추가)

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 8: pytest 동작 확인**

Run: `pytest -q`
Expected: "no tests ran" (에러 없이 수집 성공).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: project scaffolding, config, deps"
```

---

### Task 1: 지표 계산 (SMA, RSI)

**Files:**
- Create: `strategy/indicators.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Consumes: 없음 (pandas만).
- Produces:
  - `sma(series: pd.Series, period: int) -> pd.Series`
  - `rsi(series: pd.Series, period: int = 14) -> pd.Series`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_indicators.py`

```python
import pandas as pd
from strategy.indicators import sma, rsi


def test_sma_basic():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(s, 3)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 2.0   # (1+2+3)/3
    assert result.iloc[4] == 4.0   # (3+4+5)/3


def test_rsi_all_gains_is_100():
    s = pd.Series(range(1, 20), dtype=float)  # 계속 상승
    result = rsi(s, 14)
    assert result.iloc[-1] == 100.0


def test_rsi_bounds():
    s = pd.Series([10, 11, 9, 12, 8, 13, 7, 14, 6, 15, 5, 16, 4, 17, 3], dtype=float)
    result = rsi(s, 14).dropna()
    assert (result >= 0).all() and (result <= 100).all()
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.indicators'`

- [ ] **Step 3: 최소 구현** — `strategy/indicators.py`

```python
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    result = 100 - (100 / (1 + rs))
    # 손실이 0이면 rs=inf → result=100
    result = result.where(avg_loss != 0, 100.0)
    return result
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_indicators.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add strategy/indicators.py tests/test_indicators.py
git commit -m "feat: SMA and RSI indicators"
```

---

### Task 2: 매매 신호 판단

**Files:**
- Create: `strategy/signals.py`
- Test: `tests/test_signals.py`

**Interfaces:**
- Consumes: `strategy.indicators.sma`, `strategy.indicators.rsi`; `config.Settings`.
- Produces:
  - `@dataclass Signal` — 필드 `action: str` (`"buy"`/`"sell"`/`"hold"`), `reason: dict`.
  - `evaluate(candles: pd.DataFrame, settings: Settings, in_position: bool) -> Signal`
    - `candles`: 컬럼 `close` 포함, 오름차순. 마지막 행이 "오늘".
    - 매수: 골든크로스(전일 단기≤장기, 당일 단기>장기) **그리고** RSI가 최근 `rsi_period` 내 `rsi_oversold` 아래를 찍고 현재 `rsi_recover` 초과.
    - 매도: 데드크로스(전일 단기≥장기, 당일 단기<장기). (트레일링 스톱은 리스크 매니저 담당.)
    - 데이터 부족(장기 이평선 계산 불가) 시 `hold`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_signals.py`

```python
import numpy as np
import pandas as pd
from config import Settings
from strategy.signals import evaluate, Signal


def _candles(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def test_insufficient_data_holds():
    s = Settings()
    candles = _candles([100.0] * 10)  # long_period(60) 미만
    sig = evaluate(candles, s, in_position=False)
    assert sig.action == "hold"


def test_golden_cross_with_rsi_recovery_buys():
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40)
    # 하락으로 RSI 과매도 → 반등하여 골든크로스 형성
    closes = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120]
    sig = evaluate(_candles(closes), s, in_position=False)
    assert sig.action == "buy"
    assert "rsi" in sig.reason


def test_dead_cross_sells_when_in_position():
    s = Settings(short_period=3, long_period=5, rsi_period=5)
    closes = [80, 90, 100, 110, 120, 118, 105, 92, 80, 70]  # 상승 후 하락 → 데드크로스
    sig = evaluate(_candles(closes), s, in_position=True)
    assert sig.action == "sell"
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_signals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.signals'`

- [ ] **Step 3: 최소 구현** — `strategy/signals.py`

```python
from dataclasses import dataclass, field

import pandas as pd

from config import Settings
from strategy.indicators import sma, rsi


@dataclass
class Signal:
    action: str  # "buy" | "sell" | "hold"
    reason: dict = field(default_factory=dict)


def evaluate(candles: pd.DataFrame, settings: Settings, in_position: bool) -> Signal:
    close = candles["close"]
    if len(close) < settings.long_period + 1:
        return Signal("hold", {"why": "insufficient_data"})

    short = sma(close, settings.short_period)
    long = sma(close, settings.long_period)
    r = rsi(close, settings.rsi_period)

    short_now, short_prev = short.iloc[-1], short.iloc[-2]
    long_now, long_prev = long.iloc[-1], long.iloc[-2]
    rsi_now = r.iloc[-1]
    rsi_window = r.iloc[-settings.rsi_period:]

    golden = short_prev <= long_prev and short_now > long_now
    dead = short_prev >= long_prev and short_now < long_now
    rsi_recovered = (rsi_window.min() < settings.rsi_oversold) and (rsi_now > settings.rsi_recover)

    reason = {"short": float(short_now), "long": float(long_now), "rsi": float(rsi_now)}

    if not in_position and golden and rsi_recovered:
        return Signal("buy", reason)
    if in_position and dead:
        return Signal("sell", reason)
    return Signal("hold", reason)
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_signals.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add strategy/signals.py tests/test_signals.py
git commit -m "feat: buy/sell signal evaluation"
```

---

### Task 3: 리스크 매니저 (포지션·비중·트레일링 스톱)

**Files:**
- Create: `risk/manager.py`
- Test: `tests/test_risk.py`

**Interfaces:**
- Consumes: `config.Settings`.
- Produces:
  - `@dataclass Position` — `symbol:str`, `entry_price:float`, `qty:float`, `high_price:float`.
  - `class RiskManager(settings: Settings)`:
    - `can_enter(open_positions: dict[str, Position]) -> bool` — 보유 수 < max_positions.
    - `position_size(capital: float, price: float) -> float` — `capital*position_pct/price` 수량.
    - `update_high(pos: Position, price: float) -> None` — high_price 갱신.
    - `hit_trailing_stop(pos: Position, price: float) -> bool` — price ≤ high*(1-trailing_stop_pct).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_risk.py`

```python
from config import Settings
from risk.manager import RiskManager, Position


def test_can_enter_respects_max_positions():
    rm = RiskManager(Settings(max_positions=2))
    assert rm.can_enter({}) is True
    two = {"BTC": Position("BTC", 1, 1, 1), "ETH": Position("ETH", 1, 1, 1)}
    assert rm.can_enter(two) is False


def test_position_size():
    rm = RiskManager(Settings(position_pct=0.20))
    # 자본 1,000,000의 20% = 200,000 / 가격 100 = 2000
    assert rm.position_size(1_000_000, 100) == 2000.0


def test_trailing_stop_triggers_after_high():
    rm = RiskManager(Settings(trailing_stop_pct=0.05))
    pos = Position("BTC", entry_price=100, qty=1, high_price=100)
    rm.update_high(pos, 120)
    assert pos.high_price == 120
    assert rm.hit_trailing_stop(pos, 115) is False   # 120*0.95=114 > 115
    assert rm.hit_trailing_stop(pos, 113) is True     # 113 < 114
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_risk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'risk.manager'`

- [ ] **Step 3: 최소 구현** — `risk/manager.py`

```python
from dataclasses import dataclass

from config import Settings


@dataclass
class Position:
    symbol: str
    entry_price: float
    qty: float
    high_price: float


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def can_enter(self, open_positions: dict[str, Position]) -> bool:
        return len(open_positions) < self.settings.max_positions

    def position_size(self, capital: float, price: float) -> float:
        return capital * self.settings.position_pct / price

    def update_high(self, pos: Position, price: float) -> None:
        if price > pos.high_price:
            pos.high_price = price

    def hit_trailing_stop(self, pos: Position, price: float) -> bool:
        stop = pos.high_price * (1 - self.settings.trailing_stop_pct)
        return price <= stop
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_risk.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add risk/manager.py tests/test_risk.py
git commit -m "feat: risk manager with trailing stop"
```

---

### Task 4: DB 계층 (SQLAlchemy 모델 + 저장)

**Files:**
- Create: `db/models.py`
- Create: `db/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: 없음 (SQLAlchemy).
- Produces:
  - `db/models.py`: `Base`, ORM 클래스 `Trade`, `SignalLog`, `BalanceLog`. (positions는 마일스톤1 백테스트에선 메모리로 충분 — 테이블 생략, 이후 확장.)
    - `Trade`: `id, ts(datetime), symbol, side('buy'/'sell'), price(float), qty(float), fee(float), mode(str)`
    - `SignalLog`: `id, ts, symbol, action, rsi(float), short_ma(float), long_ma(float), mode`
    - `BalanceLog`: `id, ts, total_krw(float), mode`
  - `db/store.py`:
    - `class Store(db_path: str)`: `create_all()`, `add_trade(**kwargs)`, `add_signal(**kwargs)`, `add_balance(**kwargs)`, `trades_df() -> pd.DataFrame`, `balance_df() -> pd.DataFrame`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_store.py`

```python
from datetime import datetime

from db.store import Store


def test_add_and_read_trade(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.create_all()
    store.add_trade(ts=datetime(2025, 1, 1), symbol="BTC", side="buy",
                    price=100.0, qty=2.0, fee=0.5, mode="backtest")
    df = store.trades_df()
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "BTC"
    assert df.iloc[0]["side"] == "buy"


def test_balance_log(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.create_all()
    store.add_balance(ts=datetime(2025, 1, 1), total_krw=1_000_000.0, mode="backtest")
    store.add_balance(ts=datetime(2025, 1, 2), total_krw=1_050_000.0, mode="backtest")
    df = store.balance_df()
    assert len(df) == 2
    assert df.iloc[-1]["total_krw"] == 1_050_000.0
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db.store'`

- [ ] **Step 3: 모델 구현** — `db/models.py`

```python
from datetime import datetime

from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))


class SignalLog(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    symbol: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(4))
    rsi: Mapped[float] = mapped_column(Float)
    short_ma: Mapped[float] = mapped_column(Float)
    long_ma: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))


class BalanceLog(Base):
    __tablename__ = "balance_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    total_krw: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))
```

- [ ] **Step 4: store 구현** — `db/store.py`

```python
import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db.models import Base, Trade, SignalLog, BalanceLog


class Store:
    def __init__(self, db_path: str):
        self.engine = create_engine(f"sqlite:///{db_path}")

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def add_trade(self, **kwargs) -> None:
        with Session(self.engine) as s:
            s.add(Trade(**kwargs))
            s.commit()

    def add_signal(self, **kwargs) -> None:
        with Session(self.engine) as s:
            s.add(SignalLog(**kwargs))
            s.commit()

    def add_balance(self, **kwargs) -> None:
        with Session(self.engine) as s:
            s.add(BalanceLog(**kwargs))
            s.commit()

    def trades_df(self) -> pd.DataFrame:
        return pd.read_sql(select(Trade), self.engine)

    def balance_df(self) -> pd.DataFrame:
        return pd.read_sql(select(BalanceLog), self.engine)
```

- [ ] **Step 5: 통과 확인**

Run: `pytest tests/test_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add db/models.py db/store.py tests/test_store.py
git commit -m "feat: SQLAlchemy models and store"
```

---

### Task 5: 빗썸 시장 데이터 클라이언트

**Files:**
- Create: `bithumb/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: 없음 (requests).
- Produces:
  - `class BithumbClient(session=None)` — 주입 가능한 requests 세션(테스트용 mock).
    - `get_top_symbols(top_n: int, min_trade_value: float) -> list[str]` — `/public/ticker/ALL_KRW` 응답의 `acc_trade_value_24H` 기준 내림차순, min 필터 통과분 상위 top_n base 심볼.
    - `get_daily_candles(symbol: str) -> pd.DataFrame` — `/public/candlestick/{symbol}_KRW/24h` 응답을 DataFrame(`open/high/low/close/volume`, DatetimeIndex 오름차순)으로 변환.
- 참고: 빗썸 캔들 배열 순서는 `[timestamp(ms), open, close, high, low, volume]` (open, **close**, high, low 순서 주의).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_client.py`

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bithumb.client'`

- [ ] **Step 3: 최소 구현** — `bithumb/client.py`

```python
import pandas as pd
import requests

BASE = "https://api.bithumb.com/public"


class BithumbClient:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def get_top_symbols(self, top_n: int, min_trade_value: float) -> list[str]:
        url = f"{BASE}/ticker/ALL_KRW"
        resp = self.session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"]
        rows = []
        for symbol, info in data.items():
            if symbol == "date" or not isinstance(info, dict):
                continue
            value = float(info["acc_trade_value_24H"])
            if value >= min_trade_value:
                rows.append((symbol, value))
        rows.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in rows[:top_n]]

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
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 실제 API 스모크 체크** (네트워크 필요, 수동)

```bash
python3 -c "from bithumb.client import BithumbClient; c=BithumbClient(); print(c.get_top_symbols(5, 1_000_000_000)); print(c.get_daily_candles('BTC').tail(3))"
```
Expected: 상위 5개 심볼 리스트와 BTC 최근 3일 캔들 출력. (실패 시 빗썸 API 응답 포맷 변화 확인.)

- [ ] **Step 6: Commit**

```bash
git add bithumb/client.py tests/test_client.py
git commit -m "feat: Bithumb public market data client"
```

---

### Task 6: 백테스트 엔진

**Files:**
- Create: `engine/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `config.Settings`, `strategy.signals.evaluate`, `risk.manager.RiskManager`/`Position`, `db.store.Store`.
- Produces:
  - `@dataclass BacktestResult` — `final_capital:float`, `return_pct:float`, `num_trades:int`.
  - `class Backtest(settings, store, fee_rate=0.0004)`:
    - `run(candles_by_symbol: dict[str, pd.DataFrame]) -> BacktestResult`
    - 로직: 모든 심볼의 공통 날짜 인덱스를 오름차순 순회. 각 날짜 t에서 (1) 보유 포지션의 트레일링 스톱/데드크로스 청산 먼저, (2) 남는 슬롯 있으면 매수 신호 심볼 진입. 체결 시 `store.add_trade`, 매일 `store.add_balance` 기록. 수수료 `fee_rate` 반영.
    - 매수 가능 슬롯보다 신호가 많으면 심볼 알파벳 순으로 진입 (결정적 동작 → 테스트 가능).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_backtest.py`

```python
import pandas as pd
from config import Settings
from db.store import Store
from engine.backtest import Backtest


def _series(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [1.0] * len(closes)},
        index=idx,
    )


def test_backtest_runs_and_records(tmp_path):
    store = Store(str(tmp_path / "bt.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40, max_positions=2,
                 initial_capital=1_000_000)
    # 매수 유발 후 상승 → 이익 실현되는 패턴
    up = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140, 150, 160, 170]
    result = Backtest(s, store).run({"AAA": _series(up)})
    assert result.num_trades >= 1
    assert result.final_capital > 0
    assert len(store.balance_df()) == len(up)


def test_no_signal_keeps_capital_flat(tmp_path):
    store = Store(str(tmp_path / "flat.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, initial_capital=1_000_000)
    flat = [100.0] * 15  # 크로스 없음
    result = Backtest(s, store).run({"AAA": _series(flat)})
    assert result.num_trades == 0
    assert result.final_capital == 1_000_000
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_backtest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.backtest'`

- [ ] **Step 3: 최소 구현** — `engine/backtest.py`

```python
from dataclasses import dataclass

import pandas as pd

from config import Settings
from db.store import Store
from risk.manager import RiskManager, Position
from strategy.signals import evaluate


@dataclass
class BacktestResult:
    final_capital: float
    return_pct: float
    num_trades: int


class Backtest:
    def __init__(self, settings: Settings, store: Store, fee_rate: float = 0.0004):
        self.settings = settings
        self.store = store
        self.fee_rate = fee_rate
        self.risk = RiskManager(settings)

    def run(self, candles_by_symbol: dict[str, pd.DataFrame]) -> BacktestResult:
        all_dates = sorted(
            set().union(*[df.index for df in candles_by_symbol.values()])
        )
        capital = self.settings.initial_capital
        positions: dict[str, Position] = {}
        num_trades = 0

        for date in all_dates:
            # 1) 청산 검토
            for symbol in list(positions.keys()):
                df = candles_by_symbol[symbol]
                if date not in df.index:
                    continue
                price = float(df.loc[date, "close"])
                pos = positions[symbol]
                self.risk.update_high(pos, price)
                window = df.loc[:date]
                sig = evaluate(window, self.settings, in_position=True)
                if self.risk.hit_trailing_stop(pos, price) or sig.action == "sell":
                    proceeds = pos.qty * price * (1 - self.fee_rate)
                    capital += proceeds
                    self.store.add_trade(ts=date.to_pydatetime(), symbol=symbol,
                                         side="sell", price=price, qty=pos.qty,
                                         fee=pos.qty * price * self.fee_rate,
                                         mode="backtest")
                    del positions[symbol]
                    num_trades += 1

            # 2) 진입 검토 (알파벳 순, 결정적)
            for symbol in sorted(candles_by_symbol.keys()):
                if symbol in positions or not self.risk.can_enter(positions):
                    continue
                df = candles_by_symbol[symbol]
                if date not in df.index:
                    continue
                window = df.loc[:date]
                sig = evaluate(window, self.settings, in_position=False)
                if sig.action == "buy":
                    price = float(df.loc[date, "close"])
                    qty = self.risk.position_size(capital, price)
                    cost = qty * price * (1 + self.fee_rate)
                    if cost > capital:
                        continue
                    capital -= cost
                    positions[symbol] = Position(symbol, price, qty, price)
                    self.store.add_trade(ts=date.to_pydatetime(), symbol=symbol,
                                         side="buy", price=price, qty=qty,
                                         fee=qty * price * self.fee_rate,
                                         mode="backtest")
                    num_trades += 1

            # 3) 잔고 기록 (현금 + 보유 평가액)
            holdings = 0.0
            for symbol, pos in positions.items():
                df = candles_by_symbol[symbol]
                if date in df.index:
                    holdings += pos.qty * float(df.loc[date, "close"])
                else:
                    holdings += pos.qty * pos.entry_price
            self.store.add_balance(ts=date.to_pydatetime(),
                                   total_krw=capital + holdings, mode="backtest")

        final = capital + sum(
            pos.qty * float(candles_by_symbol[s].iloc[-1]["close"])
            for s, pos in positions.items()
        )
        ret = (final - self.settings.initial_capital) / self.settings.initial_capital * 100
        return BacktestResult(final, ret, num_trades)
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_backtest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 전체 테스트 확인**

Run: `pytest -q`
Expected: 모든 테스트 통과 (약 13개).

- [ ] **Step 6: Commit**

```bash
git add engine/backtest.py tests/test_backtest.py
git commit -m "feat: backtest engine"
```

---

### Task 7: CLI 진입점 (백테스트 실행)

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `config.settings`, `bithumb.client.BithumbClient`, `db.store.Store`, `engine.backtest.Backtest`.
- Produces:
  - `run_backtest(client, store, settings) -> BacktestResult` — 상위 심볼 캔들 수집 후 백테스트 실행.
  - `main()` — `argparse`로 `--mode backtest` 처리, 결과 출력.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_main.py`

```python
import pandas as pd
from config import Settings
from db.store import Store
from main import run_backtest


class StubClient:
    def get_top_symbols(self, top_n, min_trade_value):
        return ["AAA"]

    def get_daily_candles(self, symbol):
        closes = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140, 150, 160, 170]
        idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
        return pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1.0] * len(closes)}, index=idx)


def test_run_backtest_end_to_end(tmp_path):
    store = Store(str(tmp_path / "m.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, rsi_period=5,
                 rsi_oversold=35, rsi_recover=40)
    result = run_backtest(StubClient(), store, s)
    assert result.num_trades >= 1
    assert len(store.trades_df()) >= 1
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: 최소 구현** — `main.py`

```python
import argparse

from config import settings as default_settings
from bithumb.client import BithumbClient
from db.store import Store
from engine.backtest import Backtest, BacktestResult


def run_backtest(client, store, settings) -> BacktestResult:
    symbols = client.get_top_symbols(settings.top_n, settings.min_trade_value_krw)
    candles = {}
    for symbol in symbols:
        try:
            df = client.get_daily_candles(symbol)
            if len(df) >= settings.long_period + 1:
                candles[symbol] = df
        except Exception as e:
            print(f"skip {symbol}: {e}")
    return Backtest(settings, store).run(candles)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="backtest", choices=["backtest"])
    args = parser.parse_args()

    store = Store(default_settings.db_path)
    store.create_all()

    if args.mode == "backtest":
        result = run_backtest(BithumbClient(), store, default_settings)
        print(f"최종 자본: {result.final_capital:,.0f} KRW")
        print(f"수익률: {result.return_pct:.2f}%")
        print(f"거래 수: {result.num_trades}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_main.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 실제 백테스트 실행** (네트워크 필요, 수동)

Run: `python3 main.py --mode backtest`
Expected: 최종 자본·수익률·거래 수 출력. `coin.db` 생성됨.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: CLI entrypoint for backtest"
```

---

### Task 8: Streamlit 대시보드

**Files:**
- Create: `dashboard/app.py`
- Test: `tests/test_dashboard.py` (데이터 준비 함수만 단위 테스트; UI는 스모크)

**Interfaces:**
- Consumes: `db.store.Store`, `config.settings`.
- Produces:
  - `dashboard/app.py`:
    - `load_data(store) -> tuple[pd.DataFrame, pd.DataFrame]` — (balance_df, trades_df) 반환.
    - Streamlit 본문: 총자산 추이 라인차트, 최근 거래 테이블, 요약 지표(수익률·거래 수).

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_dashboard.py`

```python
from datetime import datetime
from config import Settings
from db.store import Store
from dashboard.app import load_data


def test_load_data_returns_frames(tmp_path):
    store = Store(str(tmp_path / "d.db"))
    store.create_all()
    store.add_balance(ts=datetime(2025, 1, 1), total_krw=1_000_000.0, mode="backtest")
    store.add_trade(ts=datetime(2025, 1, 1), symbol="BTC", side="buy",
                    price=100.0, qty=1.0, fee=0.1, mode="backtest")
    balance, trades = load_data(store)
    assert len(balance) == 1
    assert len(trades) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.app'`

- [ ] **Step 3: 최소 구현** — `dashboard/app.py`

```python
import pandas as pd
import streamlit as st

from config import settings
from db.store import Store


def load_data(store: Store) -> tuple[pd.DataFrame, pd.DataFrame]:
    return store.balance_df(), store.trades_df()


def render() -> None:
    st.title("코인 자동매매 봇 대시보드")
    store = Store(settings.db_path)
    balance, trades = load_data(store)

    if balance.empty:
        st.info("아직 데이터가 없다. `python3 main.py --mode backtest` 먼저 실행.")
        return

    start = balance.iloc[0]["total_krw"]
    end = balance.iloc[-1]["total_krw"]
    ret = (end - start) / start * 100
    c1, c2, c3 = st.columns(3)
    c1.metric("현재 자산", f"{end:,.0f} KRW")
    c2.metric("수익률", f"{ret:.2f}%")
    c3.metric("거래 수", f"{len(trades)}")

    st.subheader("총자산 추이")
    st.line_chart(balance.set_index("ts")["total_krw"])

    st.subheader("거래 내역")
    st.dataframe(trades.sort_values("ts", ascending=False))


if __name__ == "__main__":
    render()
```

- [ ] **Step 4: 통과 확인**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 대시보드 스모크 실행** (수동)

Run: `streamlit run dashboard/app.py`
Expected: 브라우저에서 대시보드 로드. 데이터 없으면 안내 문구, 있으면 차트·표 표시.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.py tests/test_dashboard.py
git commit -m "feat: Streamlit dashboard"
```

---

## Self-Review 결과

**1. 스펙 커버리지:**
- 빗썸 API 연동 → Task 5 ✅
- 지표·신호(이평선/RSI) → Task 1, 2 ✅
- 백테스트 엔진 → Task 6 ✅
- 리스크(트레일링·포지션·비중) → Task 3 ✅
- DB 저장(trades/signals/balance) → Task 4 ✅
- 대시보드 → Task 8 ✅
- 유동성 필터·상위100 → Task 5(`get_top_symbols`) ✅
- 페이퍼/실거래 → **이번 마일스톤 범위 밖** (검증 후 별도 계획, 스펙과 일치)

**2. 플레이스홀더 스캔:** 모든 스텝에 실제 코드/명령 포함, "TBD"·"적절히 처리" 없음 ✅

**3. 타입 일관성:** `Position(symbol, entry_price, qty, high_price)`, `Signal(action, reason)`, `Store` 메서드명, `Settings` 필드명이 태스크 전반에서 일치 ✅

**참고 사항:**
- `signals` 테이블 모델은 정의했으나 백테스트 엔진에서 아직 기록하지 않음 (trades·balance만 기록). 신호 로깅은 페이퍼/실거래 단계에서 활용 예정 — 마일스톤1 동작에는 영향 없음.
- `positions`는 백테스트에서 메모리로만 관리 (DB 테이블 미사용). 실거래 단계에서 재시작 복구용으로 테이블화 예정.
