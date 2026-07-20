"""페이퍼 트레이딩 엔진.

실시간(최신) 시세로 가상매매를 1회 수행하고, 현금·포지션 상태를 DB에
지속시킨다. 백테스트(engine/backtest.py)와 동일한 매매 로직 구조를 따르되,
과거 전체 구간을 반복하는 대신 "현재 시점 1회"만 처리한다.

처리 순서: 청산 검토 -> 진입 검토 -> 잔고 기록/저장.
"""

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
            daily_value = price * float(candles[symbol]["volume"].iloc[-1])
            qty = self.risk.position_size(cash, price, daily_value)
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
        self.store.add_balance(ts=datetime.now(), total_krw=total,
                               cash_krw=cash, holdings_krw=holdings, mode=MODE)

        return {"cash": cash, "positions": len(positions),
                "filled": filled, "total": total}
