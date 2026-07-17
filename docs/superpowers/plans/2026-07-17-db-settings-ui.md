# DB 설정 + UI 편집 + 거래량 제한 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 전략 파라미터를 DB에 저장하고 대시보드 UI에서 수정하며, 종목당 투자금을 코인 거래대금 대비 제한하는 기능을 추가한다.

**Architecture:** `app_settings` 테이블에 파라미터를 저장하고 `Store.get_settings()`로 로드. 봇은 config 대신 DB 설정을 읽는다. `RiskManager.position_size`가 거래량 상한을 적용한다.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x, pandas, Streamlit, pytest

## Global Constraints

- Python 3.11+, 표준 타입 힌트
- `.venv` 자동활성화 안 됨 → 모든 명령 `.venv/bin/` 접두사
- DB-backed 파라미터(14개): `short_period, long_period, rsi_period, rsi_oversold, rsi_recover, use_rsi_filter, trailing_stop_pct, max_positions, position_pct, max_volume_pct, top_n, min_trade_value_krw, initial_capital, fee_rate`
- `max_volume_pct`는 fraction(0.01=1%), 기본 0.01
- 하위호환: `position_size(capital, price, daily_value=None)` — daily_value None이면 기존 동작
- git author `wjd6542`, 커밋 끝 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: config 파라미터 + app_settings 모델 + Store get/save_settings

**Files:**
- Modify: `config.py` (Settings에 max_volume_pct)
- Modify: `db/models.py` (AppSettings)
- Modify: `db/store.py` (get_settings/save_settings)
- Test: `tests/test_settings_store.py`

**Interfaces:**
- Produces:
  - `Settings.max_volume_pct: float = 0.01`
  - `AppSettings` ORM (테이블 `app_settings`), 컬럼 = DB-backed 14개 + `id`
  - `Store.get_settings() -> Settings` — 행 없으면 기본값 저장 후 반환
  - `Store.save_settings(settings: Settings) -> None` — upsert

- [ ] **Step 1: 실패 테스트** — `tests/test_settings_store.py`

```python
from dataclasses import replace
from config import Settings
from db.store import Store


def _store(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    s.create_all()
    return s


def test_get_settings_initializes_defaults(tmp_path):
    s = _store(tmp_path)
    settings = s.get_settings()
    assert isinstance(settings, Settings)
    assert settings.short_period == Settings().short_period
    assert settings.max_volume_pct == 0.01


def test_save_and_get_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.get_settings()  # 초기화
    modified = replace(Settings(), short_period=7, trailing_stop_pct=0.15,
                       max_volume_pct=0.02, min_trade_value_krw=5_000_000_000.0)
    s.save_settings(modified)
    loaded = s.get_settings()
    assert loaded.short_period == 7
    assert loaded.trailing_stop_pct == 0.15
    assert loaded.max_volume_pct == 0.02
    assert loaded.min_trade_value_krw == 5_000_000_000.0
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: FAIL

- [ ] **Step 3: config에 필드 추가** — `config.py` Settings에 추가 (position_pct 아래)

```python
    max_volume_pct: float = 0.01   # 종목당 투자금을 코인 거래대금의 이 비율 이하로 제한
```

- [ ] **Step 4: 모델 추가** — `db/models.py`

상단 import에 `Integer`, `Boolean` 추가: `from sqlalchemy import String, Float, DateTime, Integer, Boolean`. 하단에:

```python
class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    short_period: Mapped[int] = mapped_column(Integer)
    long_period: Mapped[int] = mapped_column(Integer)
    rsi_period: Mapped[int] = mapped_column(Integer)
    rsi_oversold: Mapped[float] = mapped_column(Float)
    rsi_recover: Mapped[float] = mapped_column(Float)
    use_rsi_filter: Mapped[bool] = mapped_column(Boolean)
    trailing_stop_pct: Mapped[float] = mapped_column(Float)
    max_positions: Mapped[int] = mapped_column(Integer)
    position_pct: Mapped[float] = mapped_column(Float)
    max_volume_pct: Mapped[float] = mapped_column(Float)
    top_n: Mapped[int] = mapped_column(Integer)
    min_trade_value_krw: Mapped[float] = mapped_column(Float)
    initial_capital: Mapped[float] = mapped_column(Float)
    fee_rate: Mapped[float] = mapped_column(Float)
```

- [ ] **Step 5: Store 메서드** — `db/store.py`

상단에 `from config import Settings`, `from db.models import AppSettings` 추가(기존 import에 병합). 클래스에 추가:

```python
    _SETTINGS_FIELDS = (
        "short_period", "long_period", "rsi_period", "rsi_oversold",
        "rsi_recover", "use_rsi_filter", "trailing_stop_pct", "max_positions",
        "position_pct", "max_volume_pct", "top_n", "min_trade_value_krw",
        "initial_capital", "fee_rate",
    )

    def get_settings(self) -> Settings:
        with Session(self.engine) as s:
            row = s.scalars(select(AppSettings)).first()
            if row is None:
                defaults = Settings()
                s.add(AppSettings(**{f: getattr(defaults, f) for f in self._SETTINGS_FIELDS}))
                s.commit()
                return defaults
            values = {f: getattr(row, f) for f in self._SETTINGS_FIELDS}
        from dataclasses import replace
        return replace(Settings(), **values)

    def save_settings(self, settings: Settings) -> None:
        with Session(self.engine) as s:
            row = s.scalars(select(AppSettings)).first()
            if row is None:
                s.add(AppSettings(**{f: getattr(settings, f) for f in self._SETTINGS_FIELDS}))
            else:
                for f in self._SETTINGS_FIELDS:
                    setattr(row, f, getattr(settings, f))
            s.commit()
```

- [ ] **Step 6: 통과 + 회귀 + 커밋**

Run: `.venv/bin/pytest tests/test_settings_store.py -v` (PASS) 후 `.venv/bin/pytest -q`
```bash
git add config.py db/models.py db/store.py tests/test_settings_store.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: DB 설정 테이블 + get/save_settings + max_volume_pct"
```

---

### Task 2: RiskManager 거래량 상한

**Files:**
- Modify: `risk/manager.py` (position_size)
- Test: `tests/test_risk.py` (케이스 추가)

**Interfaces:**
- Produces: `position_size(capital: float, price: float, daily_value: float | None = None) -> float`
  - daily_value None: `capital*position_pct/price` (기존)
  - daily_value 지정: `min(capital*position_pct, daily_value*max_volume_pct)/price`

- [ ] **Step 1: 실패 테스트** — `tests/test_risk.py`에 추가

```python
def test_position_size_volume_cap():
    from config import Settings
    from risk.manager import RiskManager
    rm = RiskManager(Settings(position_pct=0.20, max_volume_pct=0.01))
    # 총자산 1,000,000의 20% = 200,000
    # 코인 일거래대금 5,000,000의 1% = 50,000 (상한이 더 작음)
    # → 50,000 / 가격 100 = 500
    assert rm.position_size(1_000_000, 100, daily_value=5_000_000) == 500.0
    # 상한이 크면(1억*1%=100만 > 20만) 기존 값 유지 → 200,000/100 = 2000
    assert rm.position_size(1_000_000, 100, daily_value=100_000_000) == 2000.0
    # daily_value 없으면 기존 동작
    assert rm.position_size(1_000_000, 100) == 2000.0
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_risk.py::test_position_size_volume_cap -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `risk/manager.py` position_size 교체

```python
    def position_size(self, capital: float, price: float,
                      daily_value: float | None = None) -> float:
        invest = capital * self.settings.position_pct
        if daily_value is not None and self.settings.max_volume_pct > 0:
            invest = min(invest, daily_value * self.settings.max_volume_pct)
        return invest / price
```

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `.venv/bin/pytest tests/test_risk.py -v` 후 `.venv/bin/pytest -q`
```bash
git add risk/manager.py tests/test_risk.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 거래량 대비 종목당 투자 상한(max_volume_pct)"
```

---

### Task 3: 엔진·CLI를 DB 설정·거래량 상한에 연결

**Files:**
- Modify: `engine/backtest.py` (진입 시 daily_value 전달)
- Modify: `engine/paper.py` (진입 시 daily_value 전달)
- Modify: `main.py` (store.get_settings() 사용)
- Modify: `tests/test_backtest.py`, `tests/test_paper.py` (픽스처 volume 상향 — 상한 비활성)

**Interfaces:**
- Consumes: `Store.get_settings()`, `RiskManager.position_size(capital, price, daily_value)`
- daily_value = 진입 시점 캔들 `close * volume`

- [ ] **Step 1: 픽스처 테스트 먼저 갱신** — `tests/test_backtest.py`, `tests/test_paper.py`의 `_series`/`_candles` 헬퍼에서 volume을 크게 설정(상한 비활성).

`tests/test_backtest.py`의 `_series` 내 `"volume": [1.0] * len(closes)` → `"volume": [1_000_000.0] * len(closes)` 로 변경.
`tests/test_paper.py`의 `_series` 내 동일 변경.
(이유: daily_value=close*volume가 충분히 커야 max_volume_pct 상한이 안 걸려 기존 단언 유지)

- [ ] **Step 2: 실패 확인 (아직 엔진이 daily_value 안 넘김 → 테스트는 통과하지만 상한 미적용)**

Run: `.venv/bin/pytest tests/test_backtest.py tests/test_paper.py -q`
Expected: PASS (volume 상향으로 기존 동작 유지). 이 단계는 회귀 안전 확인용.

- [ ] **Step 3: backtest 진입에 daily_value 전달** — `engine/backtest.py`

진입 블록에서 `price = float(df.loc[date, "close"])` 다음에 거래대금 계산 후 position_size 호출 변경:
```python
                    price = float(df.loc[date, "close"])
                    daily_value = price * float(df.loc[date, "volume"])
                    qty = self.risk.position_size(capital, price, daily_value)
```

- [ ] **Step 4: paper 진입에 daily_value 전달** — `engine/paper.py`

진입 블록:
```python
            price = float(candles[symbol]["close"].iloc[-1])
            daily_value = price * float(candles[symbol]["volume"].iloc[-1])
            qty = self.risk.position_size(cash, price, daily_value)
```

- [ ] **Step 5: main이 DB 설정 사용** — `main.py`

각 모드에서 store 생성 후 `settings = store.get_settings()`로 읽어 전달. backtest:
```python
    if args.mode == "backtest":
        store = Store(url=database.url())
        store.create_all()
        settings = store.get_settings()
        result = run_backtest(BithumbClient(), store, settings)
```
paper 분기도 동일하게 `settings = store.get_settings()` 후 `run_paper(BithumbClient(), store, settings)`.
tune 분기: `store = Store(url=database.url()); store.create_all(); settings = store.get_settings()` 후 `run_tune(BithumbClient(), settings, DEFAULT_GRID)` (기존 `default_settings` 대신).

- [ ] **Step 6: 통과 + 회귀 + 커밋**

Run: `.venv/bin/pytest -q` (전체 통과)
```bash
git add engine/backtest.py engine/paper.py main.py tests/test_backtest.py tests/test_paper.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 엔진·CLI를 DB설정·거래량상한에 연결"
```

---

### Task 4: 대시보드 설정 UI

**Files:**
- Modify: `dashboard/app.py` (설정 폼 추가)
- Test: `tests/test_dashboard.py` (load_settings 헬퍼 테스트)

**Interfaces:**
- Produces: `load_settings(store) -> Settings` (=store.get_settings()); `render()`에 설정 폼(입력 위젯 + 저장)

- [ ] **Step 1: 실패 테스트** — `tests/test_dashboard.py`에 추가

```python
def test_load_settings_returns_settings(tmp_path):
    from config import Settings
    from db.store import Store
    from dashboard.app import load_settings
    store = Store(str(tmp_path / "ds.db"))
    store.create_all()
    settings = load_settings(store)
    assert isinstance(settings, Settings)
    assert settings.max_volume_pct == 0.01
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/pytest tests/test_dashboard.py::test_load_settings_returns_settings -v`
Expected: FAIL

- [ ] **Step 3: 구현** — `dashboard/app.py`

`from config import Settings` 추가. 함수 추가:
```python
def load_settings(store: Store) -> Settings:
    return store.get_settings()
```
`render()` 하단(차트/표 뒤)에 설정 폼 추가:
```python
    st.divider()
    with st.expander("⚙️ 전략 설정 (수정 후 저장하면 다음 실행부터 반영)"):
        cur = load_settings(store)
        with st.form("settings_form"):
            c1, c2, c3 = st.columns(3)
            short = c1.number_input("단기 이평", 1, 200, cur.short_period)
            long = c2.number_input("장기 이평", 1, 400, cur.long_period)
            rsi_p = c3.number_input("RSI 기간", 1, 100, cur.rsi_period)
            rsi_os = c1.number_input("RSI 과매도", 0.0, 100.0, cur.rsi_oversold)
            rsi_rc = c2.number_input("RSI 회복", 0.0, 100.0, cur.rsi_recover)
            use_rsi = c3.checkbox("RSI 필터 사용(보수적)", cur.use_rsi_filter)
            trail = c1.number_input("트레일링스톱 %", 0.0, 100.0, cur.trailing_stop_pct * 100) / 100
            maxpos = c2.number_input("동시 보유 종목", 1, 50, cur.max_positions)
            pos_pct = c3.number_input("종목당 비중 %", 0.0, 100.0, cur.position_pct * 100) / 100
            vol_pct = c1.number_input("거래량대비 상한 %", 0.0, 100.0, cur.max_volume_pct * 100) / 100
            top_n = c2.number_input("상위 N종목", 1, 500, cur.top_n)
            min_val = c3.number_input("최소 거래대금(KRW)", 0.0, 1e12, cur.min_trade_value_krw)
            init_cap = c1.number_input("초기 자본(KRW)", 0.0, 1e12, cur.initial_capital)
            fee = c2.number_input("수수료율", 0.0, 1.0, cur.fee_rate, format="%.4f")
            if st.form_submit_button("저장"):
                from dataclasses import replace
                store.save_settings(replace(cur,
                    short_period=int(short), long_period=int(long), rsi_period=int(rsi_p),
                    rsi_oversold=rsi_os, rsi_recover=rsi_rc, use_rsi_filter=use_rsi,
                    trailing_stop_pct=trail, max_positions=int(maxpos), position_pct=pos_pct,
                    max_volume_pct=vol_pct, top_n=int(top_n), min_trade_value_krw=min_val,
                    initial_capital=init_cap, fee_rate=fee))
                st.success("저장됐다. 다음 봇 실행부터 반영된다.")
```

- [ ] **Step 4: 통과 + import 확인 + 회귀 + 커밋**

Run: `.venv/bin/pytest tests/test_dashboard.py -v` ; `.venv/bin/python -c "import dashboard.app"` ; `.venv/bin/pytest -q`
```bash
git add dashboard/app.py tests/test_dashboard.py
git -c user.name="wjd6542" -c user.email="wjd6542@gmail.com" commit -m "feat: 대시보드 전략 설정 편집 UI"
```

---

## Self-Review

**스펙 커버리지:** max_volume_pct(Task1,2) ✅, app_settings+get/save(Task1) ✅, RiskManager 상한(Task2) ✅, 엔진·CLI 연결(Task3) ✅, UI(Task4) ✅.

**플레이스홀더:** 없음.

**타입 일관성:** `get_settings()->Settings`, `save_settings(Settings)`, `position_size(capital, price, daily_value=None)`, `_SETTINGS_FIELDS` 14개가 config/모델/UI에서 일치. daily_value=close*volume.

**주의:** Task3 Step1에서 기존 backtest/paper 픽스처 volume을 먼저 상향(상한 비활성)해야 daily_value 전달 후에도 기존 단언이 유지된다. 실데이터·소액에선 상한이 거의 안 걸려 백테스트 수치 불변.
