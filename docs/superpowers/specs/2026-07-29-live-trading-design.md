# 마일스톤 3 — 실거래(Live) 설계 문서

**작성일:** 2026-07-29
**상태:** 승인됨
**⚠️ 실제 돈이 오가는 기능. 안전장치가 최우선.**

## 1. 목적

검증된 추세추종 전략을 **빗썸에서 실제 돈으로 자동 매매**한다. 시작 자본 30만원, 시장가 주문. 여러 겹의 안전장치로 위험을 통제한다.

## 2. 안전장치 (최우선)

실주문은 아래를 **모두 통과**해야만 나간다. 하나라도 막히면 주문 안 함(판단·기록만).

| 장치 | 설정 | 기본값 | 동작 |
|------|------|--------|------|
| 실거래 활성화 | `live_enabled` | **False** | True여야만 실주문. False면 dry-run(판단만) |
| 투자 상한 | `max_invest_krw` | 300000 | 총 투입 KRW가 이 값 초과 못 함 |
| 일일 손실한도 | `daily_loss_limit_pct` | 0.05 | 오늘 손실이 5% 넘으면 자동정지 + kill_switch ON |
| 비상정지 | `kill_switch` | False | True면 모든 실주문 즉시 중단 |

- 네 설정은 `app_settings`(DB)에 저장, 대시보드에서 수정.
- 최소주문금액(빗썸 기준) 미달 주문은 스킵.

## 3. 컴포넌트

### 3.1 빗썸 인증 API — `bithumb/private.py`
- `BithumbPrivate(api_key, secret_key, session=None)` — HMAC 서명 인증.
  - `get_balance() -> dict` — KRW 가용액 + 코인 보유량 (`/info/balance`, 읽기전용).
  - `market_buy(symbol, units) -> dict` — 시장가 매수 (`/trade/market_buy`).
  - `market_sell(symbol, units) -> dict` — 시장가 매도 (`/trade/market_sell`).
- 인증: `Api-Key`, `Api-Sign`(HMAC-SHA512), `Api-Nonce` 헤더 (빗썸 API 1.0 규격).
- 응답 `status == "0000"` 확인. 실패 시 예외/에러 dict 반환 → 엔진이 해당 주문 스킵.
- 키는 `config.Secrets`(`.env`)에서만 로드. 로그·DB·화면에 절대 노출 안 함.

### 3.2 실거래 엔진 — `engine/live.py`
`LiveTrader(settings, store, market_client, private_client, fee_rate)`:
- `run_once() -> dict` 순서:
  1. **안전장치 체크** — kill_switch/live_enabled/일일손실한도. 막히면 사유와 함께 dry-run 표시하고 주문 없이 반환.
  2. **실잔고 조회** — 빗썸에서 KRW 가용액 + 보유코인. 가용자본 = min(KRW 가용, `max_invest_krw` − 현재 투입액).
  3. **포지션 동기화** — DB(mode=live) 포지션과 실보유 대조. 전략 판단용 entry_price·high_price는 DB가 소스, 평가·가용액은 실잔고가 소스.
  4. **신호 판단** — 페이퍼와 동일 `evaluate()`.
  5. **청산** — 트레일링스톱/데드크로스면 `market_sell`(실주문) → 체결 확인 → DB 기록(사유 포함).
  6. **진입** — 매수신호+슬롯+자본이면 `market_buy`(실주문). 최소주문금액·상한 체크 → 체결 확인 → DB 기록.
  7. balance_log(mode=live)·현금·포지션 저장, 요약 반환.
- **체결 확인:** 주문 후 잔고 재조회로 실제 체결 수량/평단 반영(부분체결 대응). v1은 시장가라 즉시 체결 가정하되, 응답의 체결 정보를 우선 사용.
- **중복주문 방지:** 매 실행이 실잔고 기준으로 판단하므로 재실행 안전. 주문 실패 시 재시도 안 함(중복 위험 회피).

### 3.3 CLI — `--mode live`
- `run_live(...)` 실행. `live_enabled=False`면 dry-run(주문 없이 판단만 출력).

### 3.4 대시보드 "💰 실거래" 페이지
- 상단 **🔴 경고 배너** "실거래 — 진짜 돈".
- **빗썸 실잔고**(KRW + 보유 평가), 실거래 손익, 투입액/상한.
- **🛑 비상정지 토글**(kill_switch), **실거래 ON/OFF 토글**(live_enabled) — 크게, 확인 문구.
- **▶️ 실거래 지금 실행** 버튼.
- 보유·거래내역(사유)·현재상황 요약 (mode=live 필터).

## 4. 데이터 흐름

```
[안전장치 체크] → [빗썸 실잔고] → [지표·신호(동일코드)] → [리스크]
   → [빗썸 실주문(시장가)] → [체결확인·동기화] → [DB(mode=live)] → [대시보드 실거래]
```

## 5. 출시 순서 (단계별 검증)

1. **실잔고 조회** (읽기전용, 위험 0) — 인증·서명 작동 확인.
2. **소액 실주문 1건**(수동, 예 5천원) — 주문 경로 확인.
3. **live_enabled ON** — 자동 매매 시작 (cron/launchd는 페이퍼와 별도 결정).

## 6. 에러 처리

- API 에러(네트워크/인증/잔고부족/최소금액): 로그 남기고 **해당 주문만 스킵**, 봇 안 죽음.
- 주문 실패 시 재시도 안 함 (중복주문 방지).
- 부분체결: 잔고 재조회로 실제 수량 반영.

## 7. 테스트

- `FakeBithumbPrivate`(mock)로 매수/매도/잔고 시뮬 → 엔진·안전장치 단위테스트(실 API 안 씀).
- 안전장치 각각 테스트: live_enabled OFF, kill_switch ON, 손실한도 초과, 상한 초과, 최소금액 미달.
- 실 API는 ①읽기전용 조회부터 수동 검증.

## 8. 범위 밖

- 지정가 주문, 고급 슬리피지 모델
- 실거래 cron/launchd 자동화 (수동·검증 후 별도 결정)
- 다중 거래소

## 9. 개발 순서

1. 안전장치 설정 4종 (config + app_settings + Store) + UI 반영
2. 빗썸 인증 API (`bithumb/private.py`) + 서명 + 잔고조회 (읽기전용 먼저)
3. 실거래 엔진 (`engine/live.py`) — 안전장치·주문·체결확인
4. CLI `--mode live`
5. 대시보드 실거래 페이지
