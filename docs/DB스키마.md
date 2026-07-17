# DB 스키마 문서 — 코인 자동매매 봇

> 봇이 기록하는 **테이블 구조**를 정의한다. 모델 정의는 `db/models.py`(SQLAlchemy ORM), 저장/조회는 `db/store.py`.

## 1. DB 환경

| 용도 | 엔진 | 비고 |
|------|------|------|
| 실제 봇 운영 | **로컬 MySQL** | `.env`의 `DB_ENGINE=mysql` + 접속정보 |
| 테스트 | SQLite 임시파일 | 격리·속도, MySQL 미사용 |

- 접속 URL은 `config.Database.url()`이 생성:
  - MySQL: `mysql+pymysql://user:pass@host:port/dbname?charset=utf8mb4`
  - SQLite: `sqlite:///coin.db`
- 테이블 생성: `Store.create_all()` → `Base.metadata.create_all()` (없는 테이블만 자동 생성).
- 스키마 변경(기존 테이블 컬럼 추가 등)은 자동 반영 안 됨 → 추후 **Alembic** 도입.
- 문자셋: `utf8mb4` (MySQL).

## 2. 사전 준비 (MySQL)

봇 실행 전 데이터베이스(스키마)를 한 번 만들어둔다. 테이블 자체는 `create_all()`이 자동 생성한다.

```sql
CREATE DATABASE IF NOT EXISTS coin
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
```

## 3. 테이블 구조

### 3.1 `trades` — 체결 기록

매수/매도 체결 1건당 1행.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INT PK, auto | 기본키 |
| `ts` | DATETIME | 체결 시각 |
| `symbol` | VARCHAR(20) | 코인 심볼 (예: `BTC`) |
| `side` | VARCHAR(4) | `buy` / `sell` |
| `price` | FLOAT | 체결 가격 (KRW) |
| `qty` | FLOAT | 체결 수량 |
| `fee` | FLOAT | 수수료 (KRW) |
| `mode` | VARCHAR(10) | `backtest` / `paper` / `live` |

### 3.2 `signals` — 신호 기록

전략이 낸 판단의 근거를 남긴다 (왜 사고 팔았는지 추적용).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INT PK, auto | 기본키 |
| `ts` | DATETIME | 신호 발생 시각 |
| `symbol` | VARCHAR(20) | 코인 심볼 |
| `action` | VARCHAR(4) | `buy` / `sell` / `hold` |
| `rsi` | FLOAT | 신호 시점 RSI 값 |
| `short_ma` | FLOAT | 단기 이동평균값 |
| `long_ma` | FLOAT | 장기 이동평균값 |
| `mode` | VARCHAR(10) | `backtest` / `paper` / `live` |

> 마일스톤 1(백테스트)에서는 `trades`·`balance_log`만 기록하고, `signals` 로깅은 페이퍼/실거래 단계에서 활성화 예정. 테이블은 미리 정의해둔다.

### 3.4 `balance_log` — 자산 추이

시점별 총자산(현금 + 보유 평가액). 수익률 그래프의 데이터 소스.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INT PK, auto | 기본키 |
| `ts` | DATETIME | 기록 시각 |
| `total_krw` | FLOAT | 총자산 (KRW) |
| `mode` | VARCHAR(10) | `backtest` / `paper` / `live` |

### 3.5 `positions` — 보유 포지션 (마일스톤 2 구현됨)

페이퍼/실거래의 현재 보유 포지션. 재실행 시 상태 복구용. (ORM 클래스명 `OpenPosition`, `risk.manager.Position` 데이터클래스와 구분)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INT PK, auto | 기본키 |
| `symbol` | VARCHAR(20) | 코인 심볼 |
| `entry_price` | FLOAT | 진입 평단가 |
| `qty` | FLOAT | 보유 수량 |
| `high_price` | FLOAT | 진입 후 고점 (트레일링 기준) |
| `opened_at` | DATETIME | 진입 시각 |
| `mode` | VARCHAR(10) | `paper`/`live` |

> ⚠️ 마일스톤 3(실거래) 전 `(mode, symbol)` 유니크 제약 추가 필요 (중복행 방지).

### 3.6 `paper_account` — 가상 현금 (마일스톤 2 구현됨)

페이퍼 트레이딩의 가상 현금 잔고. mode당 1행.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INT PK, auto | 기본키 |
| `mode` | VARCHAR(10) | `paper` |
| `cash_krw` | FLOAT | 현금 잔고 |
| `updated_at` | DATETIME | 갱신 시각 |

### 3.7 `app_settings` — 전략 설정 (단일 행)

전략/리스크/유니버스 파라미터를 저장. 대시보드 UI에서 수정, 봇이 실행 시 `Store.get_settings()`로 읽음. DB가 비면 config 기본값으로 초기화.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `id` | INT PK | |
| `short_period`,`long_period`,`rsi_period` | INT | 지표 기간 |
| `rsi_oversold`,`rsi_recover` | FLOAT | RSI 임계 |
| `use_rsi_filter` | BOOL | 추세추종(F)/보수적(T) |
| `trailing_stop_pct`,`position_pct`,`max_volume_pct` | FLOAT | 리스크·자금 (fraction) |
| `max_positions`,`top_n` | INT | 동시 종목·유니버스 |
| `min_trade_value_krw`,`initial_capital`,`fee_rate` | FLOAT | 유동성·자본·수수료 |

> 인프라 값(db_path, payment_currency, DB 접속정보)은 DB 대상 아님 — config/.env 유지.

## 4. 향후 확장 (마일스톤 3 예정)

- `positions`/`paper_account`에 `(mode, symbol)` / `(mode)` 유니크 제약 추가 (중복행 방지).
- 실거래(`mode=live`) 시 실제 빗썸 잔고와 동기화.

## 5. ER 개요

```
trades         (독립)   — 체결 이력
signals        (독립)   — 신호 이력 (페이퍼/실거래에서 활성화)
balance_log    (독립)   — 자산 이력
positions      (독립)   — 현재 보유 (페이퍼/실거래, 구현됨)
paper_account  (독립)   — 가상 현금 (페이퍼, 구현됨)
```

테이블 간 외래키 관계 없이 각각 **이벤트 로그/상태 스냅샷**으로 독립 저장한다. `symbol`·`ts`·`mode`로 조인·필터하여 분석한다.

## 6. 인덱스 (추후 최적화)

데이터 누적 시 조회 성능을 위해 아래 인덱스 추가 검토:
- `trades(ts)`, `trades(symbol, ts)`
- `balance_log(ts)`
- `signals(symbol, ts)`
