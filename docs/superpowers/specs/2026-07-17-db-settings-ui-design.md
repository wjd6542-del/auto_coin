# DB 기반 설정 + UI 편집 + 거래량 제한 설계 문서

**작성일:** 2026-07-17
**상태:** 승인됨

## 1. 목적

전략 파라미터를 코드(config)가 아니라 **DB에 저장**하고 **대시보드 UI에서 수정**하면 봇이 그 값을 읽어 동작하게 한다. 추가로 대규모 자금의 슬리피지를 막기 위해 **종목당 투자금을 그 코인 거래대금 대비 일정 %로 제한**하는 파라미터를 도입한다.

## 2. 구성

### 2.1 신규 파라미터 `max_volume_pct`
- 한 종목 투자금을 그 코인 24h 거래대금의 일정 비율 이하로 제한.
- 계산: `투자금 = min(총자산 × position_pct, 코인_일거래대금 × max_volume_pct)`, `수량 = 투자금 / 가격`
- 코인 일거래대금 = 최신 일봉 `종가 × 거래량`(KRW).
- 소수 저장(0.01 = 1%), 기본값 `0.01`. `position_pct`처럼 fraction.

### 2.2 DB 설정 테이블 `app_settings` (단일 행)
전략/리스크/유니버스 파라미터를 저장:
`short_period, long_period, rsi_period, rsi_oversold, rsi_recover, use_rsi_filter, trailing_stop_pct, max_positions, position_pct, max_volume_pct, top_n, min_trade_value_krw, initial_capital, fee_rate`
- 인프라 값(db_path, payment_currency 등)은 DB 대상 아님 — config/.env 유지.

### 2.3 Store 확장
- `get_settings() -> Settings` — DB 행 로드. 없으면 config 기본값으로 초기화·저장 후 반환.
- `save_settings(settings: Settings) -> None` — upsert.

### 2.4 봇 연결
- `main.py`의 backtest/tune/paper가 `config.settings` 대신 `store.get_settings()`로 읽음.
- `risk/manager.py`의 `position_size(capital, price, daily_value=None)` — daily_value 주어지면 거래량 상한 적용(없으면 기존 동작).
- `engine/backtest.py`·`engine/paper.py` — 진입 시 코인 일거래대금(종가×거래량)을 `position_size`에 전달.

### 2.5 UI (Streamlit 설정 섹션)
- "⚙️ 설정" 폼: 모든 파라미터 입력 위젯 + 저장 버튼.
- 현재 DB 값 로드 → 표시 → 수정 → 저장(`save_settings`).
- % 계열은 UI에 % 로 표시(내부 저장은 fraction).

## 3. 하위호환

- `Settings`에 `max_volume_pct` 기본값 추가 → 기존 Settings 생성 코드 무영향.
- `position_size`의 `daily_value` 기본 None → 기존 호출/테스트 무영향.
- ⚠️ 기존 backtest/paper 테스트 픽스처의 `volume`이 작으면(예: 1.0) 기본 1% 상한이 과하게 걸린다. 해당 픽스처의 volume을 충분히 크게(상한 비활성) 조정하거나 검증 갱신 필요.

## 4. 실제 영향

- 소액(예 100만원) + 상위종목: 상한이 거의 안 걸림(거래대금이 큼) → 백테스트 결과 사실상 불변.
- 대규모 자금: 저유동성 종목 투자금이 상한에 걸려 슬리피지 통제.

## 5. 범위 밖
- 실제 주문 슬리피지 정밀 모델(마일스톤 3)
- 종목별 개별 설정(전역 설정만)

## 6. 개발 순서
1. config `max_volume_pct` + `app_settings` 모델 + Store get/save_settings
2. RiskManager 거래량 상한
3. backtest/paper/main 연결 (daily_value 전달, DB 설정 참조)
4. 대시보드 설정 UI
