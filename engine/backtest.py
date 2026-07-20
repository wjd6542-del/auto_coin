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
            # 1) 청산 검토 (트레일링 스톱/데드크로스, 진입보다 먼저)
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
                    daily_value = price * float(df.loc[date, "volume"])
                    qty = self.risk.position_size(capital, price, daily_value)
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
                                    total_krw=capital + holdings,
                                    cash_krw=capital, holdings_krw=holdings,
                                    mode="backtest")

        final = capital + sum(
            pos.qty * float(candles_by_symbol[s].iloc[-1]["close"])
            for s, pos in positions.items()
        )
        ret = (final - self.settings.initial_capital) / self.settings.initial_capital * 100
        return BacktestResult(final, ret, num_trades)
