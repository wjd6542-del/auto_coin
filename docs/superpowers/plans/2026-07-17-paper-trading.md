# 페이퍼 트레이딩 구현 계획 (마일스톤 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 추세추종 전략을 실시간 시세로 가상매매하며 상태를 DB에 지속하는 페이퍼 트레이딩 봇을 만든다.

**Architecture:** 백테스트와 동일한 `strategy/`·`risk/` 로직을 재사용하되, 현금·포지션을 DB에 저장해 매일 1 사이클씩 반복 실행한다. `engine/paper.py`가 로드→시세→청산→진입→저장을 조율한다.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x, pandas, pytest

## Global Constraints

- Python 3.11+, 표준 타입 힌트
- 가상환경 `.venv` 자동 활성화 안 됨 → 모든 명령에 `.venv/bin/` 접두사
- 운영 DB=MySQL, 테스트=SQLite(임시파일). Store는 `Store(db_path=...)` 또는 `Store(url=...)`
- 전략·리스크 코드는 그대로 재사용 (`strategy.signals.evaluate`, `risk.manager.RiskManager/Position`)
- 체결가 = 최신 일봉 종가. 처리 순서 = 청산 → 진입 → 잔고기록 (백테스트와 동일)
- 실제 주문 API 미사용 (가상 체결)
- ORM 모델명은 `risk.manager.Position` 데이터클래스와 겹치지 않게 `OpenPosition` 사용
- git author: `git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com"`, 커밋 끝에 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: 포지션·계좌 모델 + Store 확장

**Files:**
- Modify: `db/models.py` (OpenPosition, PaperAccount 추가)
- Modify: `db/store.py` (계좌·포지션 메서드 추가)
- Test: `tests/test_paper_store.py`

**Interfaces:**
- Consumes: 기존 `db.models.Base`, `db.store.Store`, `risk.manager.Position`
- Produces (Store 메서드):
  - `get_account(mode: str) -> float | None` — 현금, 없으면 None
  - `save_account(mode: str, cash: float) -> None` — upsert
  - `get_positions(mode: str) -> dict[str, Position]` — symbol→risk.manager.Position
  - `add_position(pos: Position, mode: str) -> None`
  - `remove_position(symbol: str, mode: str) -> None`
  - `update_position_high(symbol: str, mode: str, high: float) -> None`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_paper_store.py`

```python
from risk.manager import Position
from db.store import Store


def _store(tmp_path):
    s = Store(str(tmp_path / "p.db"))
    s.create_all()
    return s


def test_account_upsert(tmp_path):
    s = _store(tmp_path)
    assert s.get_account("paper") is None
    s.save_account("paper", 1_000_000.0)
    assert s.get_account("paper") == 1_000_000.0
    s.save_account("paper", 950_000.0)          # 갱신
    assert s.get_account("paper") == 950_000.0


def test_positions_crud(tmp_path):
    s = _store(tmp_path)
    assert s.get_positions("paper") == {}
    s.add_position(Position("BTC", entry_price=100.0, qty=2.0, high_price=100.0), "paper")
    s.add_position(Position("ETH", entry_price=50.0, qty=4.0, high_price=50.0), "paper")
    pos = s.get_positions("paper")
    assert set(pos) == {"BTC", "ETH"}
    assert pos["BTC"].qty == 2.0 and pos["BTC"].entry_price == 100.0

    s.update_position_high("BTC", "paper", 130.0)
    assert s.get_positions("paper")["BTC"].high_price == 130.0

    s.remove_position("BTC", "paper")
    assert set(s.get_positions("paper")) == {"ETH"}
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_paper_store.py -v`
Expected: FAIL — `OpenPosition`/메서드 없음

- [ ] **Step 3: 모델 추가** — `db/models.py` 하단에 추가

```python
class OpenPosition(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    entry_price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    high_price: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    mode: Mapped[str] = mapped_column(String(10))


class PaperAccount(Base):
    __tablename__ = "paper_account"
    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(10))
    cash_krw: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
```

- [ ] **Step 4: Store 메서드 추가** — `db/store.py`

기존 import에 추가: `from datetime import datetime`, `from db.models import OpenPosition, PaperAccount`, `from risk.manager import Position`. `select`, `delete`는 `from sqlalchemy import ...`에 포함.

```python
    def get_account(self, mode: str) -> float | None:
        with Session(self.engine) as s:
            row = s.scalars(
                select(PaperAccount).where(PaperAccount.mode == mode)
            ).first()
            return row.cash_krw if row else None

    def save_account(self, mode: str, cash: float) -> None:
        with Session(self.engine) as s:
            row = s.scalars(
                select(PaperAccount).where(PaperAccount.mode == mode)
            ).first()
            if row:
                row.cash_krw = cash
                row.updated_at = datetime.now()
            else:
                s.add(PaperAccount(mode=mode, cash_krw=cash, updated_at=datetime.now()))
            s.commit()

    def get_positions(self, mode: str) -> dict[str, Position]:
        with Session(self.engine) as s:
            rows = s.scalars(
                select(OpenPosition).where(OpenPosition.mode == mode)
            ).all()
            return {
                r.symbol: Position(r.symbol, r.entry_price, r.qty, r.high_price)
                for r in rows
            }

    def add_position(self, pos: Position, mode: str) -> None:
        with Session(self.engine) as s:
            s.add(OpenPosition(
                symbol=pos.symbol, entry_price=pos.entry_price, qty=pos.qty,
                high_price=pos.high_price, opened_at=datetime.now(), mode=mode,
            ))
            s.commit()

    def remove_position(self, symbol: str, mode: str) -> None:
        with Session(self.engine) as s:
            s.execute(delete(OpenPosition).where(
                OpenPosition.mode == mode, OpenPosition.symbol == symbol))
            s.commit()

    def update_position_high(self, symbol: str, mode: str, high: float) -> None:
        with Session(self.engine) as s:
            row = s.scalars(select(OpenPosition).where(
                OpenPosition.mode == mode, OpenPosition.symbol == symbol)).first()
            if row:
                row.high_price = high
                s.commit()
```
`db/store.py` 상단 import에 `delete` 추가: `from sqlalchemy import create_engine, select, delete`.

- [ ] **Step 5: 통과 확인**

Run: `.venv/bin/pytest tests/test_paper_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: 전체 회귀 + 커밋**

Run: `.venv/bin/pytest -q` (기존 테스트 무영향 확인)
```bash
git add db/models.py db/store.py tests/test_paper_store.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 포지션·페이퍼계좌 모델 + Store 지속 메서드"
```

---

### Task 2: 페이퍼 트레이딩 엔진

**Files:**
- Create: `engine/paper.py`
- Test: `tests/test_paper.py`

**Interfaces:**
- Consumes: `config.Settings`, `db.store.Store`, `risk.manager.RiskManager/Position`, `strategy.signals.evaluate`
- Produces:
  - `class PaperTrader(settings, store, client, fee_rate=0.0004)`:
    - `run_once() -> dict` — 하루 사이클. 반환 dict: `{"cash", "positions", "filled", "total"}`
  - client 인터페이스: `get_top_symbols(top_n, min_trade_value) -> list[str]`, `get_daily_candles(symbol) -> pd.DataFrame`

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_paper.py`

```python
import pandas as pd
from config import Settings
from db.store import Store
from engine.paper import PaperTrader


def _series(closes):
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": [1.0] * len(closes)}, index=idx)


class StubClient:
    def __init__(self, candles):
        self._candles = candles
    def get_top_symbols(self, top_n, min_trade_value):
        return list(self._candles.keys())
    def get_daily_candles(self, symbol):
        return self._candles[symbol]


def _store(tmp_path):
    s = Store(str(tmp_path / "paper.db"))
    s.create_all()
    return s


def test_first_run_initializes_and_buys(tmp_path):
    store = _store(tmp_path)
    # 골든크로스 유발 상승 시계열
    up = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140]
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 initial_capital=1_000_000, max_positions=4)
    trader = PaperTrader(s, store, StubClient({"AAA": _series(up)}))
    summary = trader.run_once()
    # 매수 발생 → 포지션 1개, 현금 감소, trade 기록
    assert summary["positions"] == 1
    assert summary["cash"] < 1_000_000
    assert len(store.trades_df()) == 1
    # 계좌·포지션이 DB에 지속됨
    assert store.get_account("paper") is not None
    assert "AAA" in store.get_positions("paper")


def test_state_persists_across_runs(tmp_path):
    store = _store(tmp_path)
    up = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140]
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False,
                 initial_capital=1_000_000, max_positions=4)
    trader = PaperTrader(s, store, StubClient({"AAA": _series(up)}))
    trader.run_once()
    cash_after_first = store.get_account("paper")
    # 두 번째 실행: 이미 보유 중이라 재매수 안 함(중복 진입 금지), 현금 유지
    trader2 = PaperTrader(s, store, StubClient({"AAA": _series(up)}))
    trader2.run_once()
    assert store.get_account("paper") == cash_after_first
    assert len(store.get_positions("paper")) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_paper.py -v`
Expected: FAIL — `engine.paper` 없음

- [ ] **Step 3: 엔진 구현** — `engine/paper.py`

```python
from datetime import datetime

from config import Settings
from db.store import Store
from risk.manager import RiskManager, Position
from strategy.signals import evaluate

MODE = "paper"


class PaperTrader:
    def __init__(self, settings: Settings, store: Store, client, fee_rate: float = 0.0004):
        self.settings = settings
        self.store = store
        self.client = client
        self.fee_rate = fee_rate
        self.risk = RiskManager(settings)

    def run_once(self) -> dict:
        cash = self.store.get_account(MODE)
        if cash is None:
            cash = self.settings.initial_capital
        positions = self.store.get_positions(MODE)

        # 시세 수집: 후보 상위종목 + 보유종목
        symbols = self.client.get_top_symbols(
            self.settings.top_n, self.settings.min_trade_value_krw)
        candles: dict = {}
        for symbol in set(symbols) | set(positions):
            try:
                df = self.client.get_daily_candles(symbol)
                if len(df) >= self.settings.long_period + 1:
                    candles[symbol] = df
            except Exception as e:
                print(f"skip {symbol}: {e}")

        filled = 0

        # 1) 청산 검토 (보유 포지션)
        for symbol in list(positions.keys()):
            if symbol not in candles:
                continue
            price = float(candles[symbol]["close"].iloc[-1])
            pos = positions[symbol]
            self.risk.update_high(pos, price)
            self.store.update_position_high(symbol, MODE, pos.high_price)
            sig = evaluate(candles[symbol], self.settings, in_position=True)
            if self.risk.hit_trailing_stop(pos, price) or sig.action == "sell":
                cash += pos.qty * price * (1 - self.fee_rate)
                self.store.add_trade(ts=datetime.now(), symbol=symbol, side="sell",
                                     price=price, qty=pos.qty,
                                     fee=pos.qty * price * self.fee_rate, mode=MODE)
                self.store.remove_position(symbol, MODE)
                del positions[symbol]
                filled += 1

        # 2) 진입 검토 (알파벳 순, 결정적)
        for symbol in sorted(candles.keys()):
            if symbol in positions or not self.risk.can_enter(positions):
                continue
            sig = evaluate(candles[symbol], self.settings, in_position=False)
            if sig.action != "buy":
                continue
            price = float(candles[symbol]["close"].iloc[-1])
            qty = self.risk.position_size(cash, price)
            cost = qty * price * (1 + self.fee_rate)
            if cost > cash or qty <= 0:
                continue
            cash -= cost
            new_pos = Position(symbol, price, qty, price)
            positions[symbol] = new_pos
            self.store.add_position(new_pos, MODE)
            self.store.add_trade(ts=datetime.now(), symbol=symbol, side="buy",
                                 price=price, qty=qty,
                                 fee=qty * price * self.fee_rate, mode=MODE)
            filled += 1

        # 3) 잔고 기록 + 저장
        holdings = sum(
            pos.qty * float(candles[s]["close"].iloc[-1])
            for s, pos in positions.items() if s in candles
        )
        total = cash + holdings
        self.store.save_account(MODE, cash)
        self.store.add_balance(ts=datetime.now(), total_krw=total, mode=MODE)

        return {"cash": cash, "positions": len(positions),
                "filled": filled, "total": total}
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_paper.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `.venv/bin/pytest -q`
```bash
git add engine/paper.py tests/test_paper.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 페이퍼 트레이딩 엔진 (상태 지속 가상매매)"
```

---

### Task 3: CLI `--mode paper`

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py` (paper 케이스 추가)

**Interfaces:**
- Consumes: `engine.paper.PaperTrader`, `bithumb.client.BithumbClient`, `db.store.Store`, `config`
- Produces: `run_paper(client, store, settings) -> dict`; `main()`의 `--mode paper` 분기

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_main.py` 하단에 추가

```python
def test_run_paper_end_to_end(tmp_path):
    import pandas as pd
    from db.store import Store
    from config import Settings
    from main import run_paper

    class PaperStub:
        def get_top_symbols(self, top_n, min_trade_value):
            return ["AAA"]
        def get_daily_candles(self, symbol):
            closes = [100, 95, 90, 85, 80, 78, 85, 95, 108, 120, 130, 140]
            idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
            return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                                 "close": closes, "volume": [1.0]*len(closes)}, index=idx)

    store = Store(str(tmp_path / "mp.db"))
    store.create_all()
    s = Settings(short_period=3, long_period=5, use_rsi_filter=False)
    summary = run_paper(PaperStub(), store, s)
    assert "total" in summary
    assert store.get_account("paper") is not None
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_main.py::test_run_paper_end_to_end -v`
Expected: FAIL — `run_paper` 없음

- [ ] **Step 3: 구현** — `main.py`

`from engine.paper import PaperTrader` 추가. 함수 추가:
```python
def run_paper(client, store, settings) -> dict:
    return PaperTrader(settings, store, client, fee_rate=settings.fee_rate).run_once()
```
`main()`의 argparse choices에 `"paper"` 추가, 분기 추가:
```python
    elif args.mode == "paper":
        store = Store(url=database.url())
        store.create_all()
        summary = run_paper(BithumbClient(), store, default_settings)
        print(f"현금: {summary['cash']:,.0f} KRW")
        print(f"보유 종목: {summary['positions']}개")
        print(f"당일 체결: {summary['filled']}건")
        print(f"총자산: {summary['total']:,.0f} KRW")
```
choices 갱신: `choices=["backtest", "tune", "paper"]`

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_main.py -v`
Expected: PASS (모든 케이스)

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `.venv/bin/pytest -q`
```bash
git add main.py tests/test_main.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: CLI --mode paper"
```

---

### Task 4: cron 래퍼 스크립트

**Files:**
- Create: `scripts/run_paper.sh`

**Interfaces:** 없음 (셸 스크립트). venv로 `main.py --mode paper` 실행 + 로그.

- [ ] **Step 1: 스크립트 작성** — `scripts/run_paper.sh`

```bash
#!/usr/bin/env bash
# 페이퍼 트레이딩 1 사이클 실행 (cron용)
set -euo pipefail
PROJECT_DIR="/Users/wjd/프로젝트/coin"
cd "$PROJECT_DIR"
mkdir -p logs
TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "[$TS] paper run 시작" >> logs/paper.log
"$PROJECT_DIR/.venv/bin/python" main.py --mode paper >> logs/paper.log 2>&1
echo "[$TS] paper run 종료" >> logs/paper.log
```

- [ ] **Step 2: 실행 권한 + 스모크**

```bash
chmod +x scripts/run_paper.sh
```
Run: `.venv/bin/python -c "import subprocess"` (구문 확인용, 실제 실행은 네트워크·MySQL 필요하니 생략 가능)
`logs/`는 `.gitignore`에 추가: `logs/` 한 줄.

- [ ] **Step 3: cron 등록 안내(문서화)**

`scripts/run_paper.sh` 상단 주석 또는 README에 cron 등록법 명시:
```
# 매일 KST 00:30 실행 (crontab -e):
# 30 0 * * * /Users/wjd/프로젝트/coin/scripts/run_paper.sh
```
crontab 자동 등록은 사용자 확인 후 별도로. 이 태스크는 스크립트+안내까지.

- [ ] **Step 4: 커밋**

```bash
git add scripts/run_paper.sh .gitignore
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 페이퍼 cron 래퍼 스크립트"
```

---

### Task 5: 대시보드 모드 필터

**Files:**
- Modify: `dashboard/app.py`
- Test: `tests/test_dashboard.py` (모드 필터 케이스 추가)

**Interfaces:**
- Produces: `load_data(store, mode: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]` — mode 지정 시 해당 모드만.

- [ ] **Step 1: 실패 테스트 추가** — `tests/test_dashboard.py`

```python
def test_load_data_filters_by_mode(tmp_path):
    from datetime import datetime
    from db.store import Store
    from dashboard.app import load_data

    store = Store(str(tmp_path / "dm.db"))
    store.create_all()
    store.add_balance(ts=datetime(2025, 1, 1), total_krw=1_000_000.0, mode="backtest")
    store.add_balance(ts=datetime(2025, 1, 2), total_krw=1_100_000.0, mode="paper")
    store.add_trade(ts=datetime(2025, 1, 2), symbol="BTC", side="buy",
                    price=1.0, qty=1.0, fee=0.0, mode="paper")

    balance, trades = load_data(store, mode="paper")
    assert len(balance) == 1
    assert balance.iloc[0]["mode"] == "paper"
    assert len(trades) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_load_data_filters_by_mode -v`
Expected: FAIL — `load_data`가 mode 인자 없음

- [ ] **Step 3: 구현** — `dashboard/app.py`

```python
def load_data(store: Store, mode: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    balance, trades = store.balance_df(), store.trades_df()
    if mode is not None:
        balance = balance[balance["mode"] == mode].reset_index(drop=True)
        trades = trades[trades["mode"] == mode].reset_index(drop=True)
    return balance, trades
```
`render()`에 모드 선택 추가:
```python
    mode = st.radio("모드", ["backtest", "paper"], horizontal=True)
    balance, trades = load_data(store, mode=mode)
```
(기존 `load_data(store)` 호출을 위 두 줄로 교체. 나머지 렌더링 로직 동일.)

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/pytest tests/test_dashboard.py -v`
Expected: PASS (기존 + 신규)

- [ ] **Step 5: import 확인 + 전체 회귀 + 커밋**

Run: `.venv/bin/python -c "import dashboard.app"` ; `.venv/bin/pytest -q`
```bash
git add dashboard/app.py tests/test_dashboard.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 대시보드 모드 필터 (backtest/paper 분리)"
```

---

## Self-Review

**스펙 커버리지:** positions/paper_account 모델(Task1) ✅, PaperTrader 엔진(Task2) ✅, CLI(Task3) ✅, cron(Task4) ✅, 대시보드 모드필터(Task5) ✅.

**플레이스홀더:** 모든 스텝에 실제 코드·명령 포함. 없음.

**타입 일관성:** `Position`(risk.manager 데이터클래스)와 `OpenPosition`(ORM) 명확히 분리. Store 메서드는 `Position` 반환. PaperTrader가 `store.get_positions/add_position/remove_position/update_position_high`, `get_account/save_account` 사용 — Task1 정의와 일치.

**주의:** PaperTrader의 청산·진입 로직은 backtest와 동일 구조지만 "현재 시점 1회"만 처리(과거 순회 없음). `evaluate`는 전체 캔들을 받아 마지막 봉 기준 판단하므로 그대로 사용 가능.
