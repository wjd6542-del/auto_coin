# 마일스톤 2 — 페이퍼 트레이딩 설계 문서

**작성일:** 2026-07-17
**상태:** 승인됨

## 1. 목적

확정된 추세추종 전략(15/60, 트레일링 10%)을 **실시간 시세로 가상매매**하며 며칠~몇 주 검증한다. 실제 주문은 하지 않는다(가상 체결). 백테스트가 과거 최적화 값이므로, 실전 시장에서도 동작하는지 확인한 뒤 실거래(마일스톤 3)로 넘어간다.

## 2. 백테스트와의 차이

| | 백테스트 | 페이퍼 |
|---|---|---|
| 데이터 | 과거 전체 일괄 | 실행 시점 최신 일봉 |
| 상태 | 메모리(1회성) | **DB 지속**(현금·포지션) |
| 실행 | 한 번 쭉 | 매일 1 사이클 반복 |
| 전략·리스크 코드 | `strategy/`,`risk/` | **동일 재사용** |

## 3. 새 구성요소

### 3.1 DB 테이블 신설

**`positions`** — 현재 보유 포지션
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INT PK | |
| symbol | VARCHAR(20) | 코인 |
| entry_price | FLOAT | 평단가 |
| qty | FLOAT | 수량 |
| high_price | FLOAT | 진입 후 고점(트레일링 기준) |
| opened_at | DATETIME | 진입 시각 |
| mode | VARCHAR(10) | `paper`/`live` |

**`paper_account`** — 가상 현금
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | INT PK | |
| mode | VARCHAR(10) | `paper` |
| cash_krw | FLOAT | 현금 잔고 |
| updated_at | DATETIME | 갱신 시각 |

### 3.2 엔진 `engine/paper.py`

`PaperTrader(settings, store, client, fee_rate)`:
- `run_once() -> dict` — 하루치 사이클:
  1. DB에서 현금·보유 포지션 로드 (없으면 `initial_capital`로 초기화)
  2. 상위 N종목 + 보유종목 최신 일봉 수집
  3. **청산 먼저**: 보유 포지션마다 고점 갱신 → 트레일링스톱 OR 데드크로스면 현재가(최신 종가)로 가상 매도 → 현금 증가, 포지션 삭제, trade 기록
  4. **진입 나중**: 심볼 알파벳 순, 슬롯 여유(`can_enter`) + 매수신호면 현재가로 가상 매수 → 현금 감소, 포지션 생성, trade 기록
  5. balance_log 기록(현금+보유평가액), 현금·포지션 DB 저장
  6. 요약 dict 반환(현금, 보유수, 당일 체결수, 총자산)

체결가 = 최신 일봉 종가(일봉 전략이라 백테스트와 일관). 처리 순서(청산→진입→기록)도 백테스트와 동일.

### 3.3 Store 확장

- `Position` ORM 모델, `PaperAccount` ORM 모델 추가.
- 메서드: `get_account(mode)`, `save_account(mode, cash)`, `get_positions(mode)`, `add_position(...)`, `remove_position(symbol, mode)`, `update_position_high(symbol, mode, high)`.

### 3.4 CLI + cron

- `main.py --mode paper` — `PaperTrader.run_once()` 실행 후 요약 출력.
- cron 등록: 매일 KST 00:30 (일봉 마감 직후). 래퍼 스크립트(`scripts/run_paper.sh`)로 venv 활성화 + 실행 + 로그 기록.

### 3.5 대시보드 개선

- 모드 선택(backtest/paper) 필터 추가. `load_data(store, mode)`로 해당 모드만 조회. 백테스트 12.5년치와 페이퍼 신규 데이터가 한 차트에 섞이지 않게.

## 4. 안전/제약

- **실제 주문 API 미사용** — 가상 체결만. 빗썸 키 불필요.
- 백테스트 데이터에 영향 없음 (mode 컬럼으로 분리).
- 재실행 안전(idempotent 지향): 같은 날 두 번 실행돼도 상태가 크게 어긋나지 않게 유의(포지션은 DB 기준).

## 5. 범위 밖 (마일스톤 3)

- 실제 빗썸 주문 API 연동, 잔고 동기화
- 실시간(intraday) 체결
- 슬리피지 정밀 모델

## 6. 개발 순서

1. Position/PaperAccount 모델 + Store 메서드
2. PaperTrader 엔진
3. CLI `--mode paper`
4. cron 래퍼 스크립트
5. 대시보드 모드 필터
