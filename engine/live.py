"""실거래 엔진.

빗썸 실계좌로 시장가 매매를 1회 수행한다. 4중 안전장치
(kill_switch / live_enabled / 일일손실한도 / 투자상한)를 모두 통과해야만
실주문이 나간다. 매매 로직 구조는 페이퍼(engine/paper.py)와 동일하되,
가상 잔고 대신 실계좌 잔고(private_client.get_balance)를 사용한다.

처리 순서: 시세 수집 -> 실잔고 조회 -> 안전장치 검사 -> (통과 시) 청산 -> 진입.
"""

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
        # 시세를 못 받은 보유종목은 평단으로 평가한다(총자산에서 누락 방지).
        # 누락되면 투자상한이 뚫리거나 일일손실이 과소평가될 수 있어 안전상 중요.
        holdings = 0.0
        for s, pos in positions.items():
            if s in candles:
                holdings += pos.qty * float(candles[s]["close"].iloc[-1])
            else:
                holdings += pos.qty * pos.entry_price
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
