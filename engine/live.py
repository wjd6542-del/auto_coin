"""실거래 엔진.

빗썸 실계좌로 시장가 매매를 1회 수행한다. 4중 안전장치
(kill_switch / live_enabled / 일일손실한도 / 투자상한)를 모두 통과해야만
실주문이 나간다. 매매 로직 구조는 페이퍼(engine/paper.py)와 동일하되,
가상 잔고 대신 실계좌 잔고(private_client.get_balance)를 사용하고,
주문 후 잔고를 재조회해 실제 체결 수량을 반영한다(유령 포지션 방지).

처리 순서: 시세 수집 -> 실잔고 조회 -> 안전장치 검사 -> (통과 시) 청산 -> 진입.
"""

from dataclasses import replace
from datetime import datetime

from config import Settings
from db.store import Store
from risk.manager import RiskManager, Position
from strategy.signals import evaluate
from bithumb.private import parse_krw_available, parse_units, order_ok

MODE = "live"
MIN_ORDER_KRW = 5000.0   # 빗썸 최소 주문금액(대략)


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


def _loss_baseline(store: Store) -> float:
    """일일 손실 기준선.

    오늘 첫 기록이 있으면 그것을, 없으면(그날 첫 실행) 직전(어제 등) 마지막
    기록을 쓴다. 하루 1회 실행에서도 손실한도가 동작하도록 함(직전 자산 대비).
    기록이 전혀 없으면 0(미발동).
    """
    b = store.balance_df()
    b = b[b["mode"] == MODE]
    if b.empty:
        return 0.0
    today = datetime.now().date()
    today_rows = b[b["ts"].apply(lambda t: t.date() == today)]
    if not today_rows.empty:
        return float(today_rows.iloc[0]["total_krw"])
    return float(b.iloc[-1]["total_krw"])


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
        # 시세를 못 받은 보유종목은 평단으로 평가한다(총자산에서 누락 방지).
        holdings = 0.0
        for s, pos in positions.items():
            if s in candles:
                holdings += pos.qty * float(candles[s]["close"].iloc[-1])
            else:
                holdings += pos.qty * pos.entry_price
        return cash + holdings

    def _safe_balance(self):
        """잔고 조회. 실패하면 None."""
        try:
            return self.private.get_balance()
        except Exception as e:
            print(f"잔고조회 오류: {e}")
            return None

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

        # 실잔고 조회 (실패 시 안전하게 중단 — 주문 없음)
        balance = self._safe_balance()
        if balance is None:
            return {"cash": 0.0, "positions": len(positions),
                    "filled": 0, "total": 0.0, "blocked": "잔고조회 실패"}
        cash = parse_krw_available(balance)
        total = self._current_total(cash, positions, candles)

        # 안전장치 (baseline은 오늘 기록 추가 전에 계산)
        baseline = _loss_baseline(self.store)
        blocked = safety_block_reason(self.settings, total, baseline)
        self.store.add_balance(ts=datetime.now(), total_krw=total,
                               cash_krw=cash, holdings_krw=total - cash, mode=MODE)
        if blocked:
            # 손실한도 초과면 kill_switch 래치(다음 실행 자동 재개 방지)
            if blocked.startswith("일일 손실한도"):
                self.settings = replace(self.settings, kill_switch=True)
                self.store.save_settings(self.settings)
                print("일일 손실한도 초과 → 비상정지(kill_switch) 자동 ON")
            print(f"실거래 차단: {blocked}")
            return {"cash": cash, "positions": len(positions),
                    "filled": 0, "total": total, "blocked": blocked}

        filled = 0
        holdings_value = total - cash

        # 1) 청산 (실보유 수량 기준)
        for symbol in list(positions.keys()):
            if symbol not in candles:
                continue
            price = float(candles[symbol]["close"].iloc[-1])
            pos = positions[symbol]
            self.risk.update_high(pos, price)
            self.store.update_position_high(symbol, MODE, pos.high_price)
            sig = evaluate(candles[symbol], self.settings, in_position=True)
            hit_stop = self.risk.hit_trailing_stop(pos, price)
            if not (hit_stop or sig.action == "sell"):
                continue
            held = parse_units(balance, symbol)
            sell_qty = held if held > 0 else pos.qty
            try:
                resp = self.private.market_sell(symbol, sell_qty)
            except Exception as e:
                resp = {"error": {"message": str(e)}}
            if not order_ok(resp):
                print(f"매도 실패 {symbol}: {resp}")
                continue
            proceeds = sell_qty * price
            cash += proceeds
            loss_pct = (price / pos.entry_price - 1) * 100
            note = (f"트레일링스톱 매도 (손익 {loss_pct:+.1f}%)" if hit_stop
                    else f"데드크로스 매도 (손익 {loss_pct:+.1f}%)")
            self.store.add_trade(ts=datetime.now(), symbol=symbol, side="sell",
                                 price=price, qty=sell_qty,
                                 fee=proceeds * self.fee_rate, note=note, mode=MODE)
            self.store.remove_position(symbol, MODE)
            del positions[symbol]
            filled += 1

        # 2) 진입 (투자상한 이내, 체결 후 실수량 반영)
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
            krw_to_spend = qty * price   # 시장가 매수는 금액 기준
            if qty <= 0 or krw_to_spend > cash or krw_to_spend < MIN_ORDER_KRW:
                continue
            units_before = parse_units(balance, symbol)
            try:
                resp = self.private.market_buy(symbol, krw_to_spend)
            except Exception as e:
                resp = {"error": {"message": str(e)}}
            # 체결 재확인: 주문이 타임아웃돼도 잔고로 실제 체결분을 확인
            new_bal = self._safe_balance()
            filled_qty = (parse_units(new_bal, symbol) - units_before) if new_bal else 0.0
            if filled_qty <= 0:
                if not order_ok(resp):
                    print(f"매수 실패/미체결 {symbol}: {resp}")
                    continue
                filled_qty = qty   # 주문 성공했으나 잔고 재확인 실패 → 추정치
            entry = krw_to_spend / filled_qty if filled_qty > 0 else price
            cash -= krw_to_spend
            holdings_value += krw_to_spend
            new_pos = Position(symbol, entry, filled_qty, entry)
            positions[symbol] = new_pos
            self.store.add_position(new_pos, MODE)
            note = f"골든크로스 매수 (RSI {sig.reason.get('rsi', 0):.0f})"
            self.store.add_trade(ts=datetime.now(), symbol=symbol, side="buy",
                                 price=entry, qty=filled_qty,
                                 fee=krw_to_spend * self.fee_rate, note=note, mode=MODE)
            filled += 1

        return {"cash": cash, "positions": len(positions),
                "filled": filled, "total": total, "blocked": None}
