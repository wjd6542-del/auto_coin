from dataclasses import dataclass

from config import Settings


@dataclass
class Position:
    symbol: str
    entry_price: float
    qty: float
    high_price: float


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def can_enter(self, open_positions: dict[str, Position]) -> bool:
        return len(open_positions) < self.settings.max_positions

    def position_size(self, capital: float, price: float) -> float:
        return capital * self.settings.position_pct / price

    def update_high(self, pos: Position, price: float) -> None:
        if price > pos.high_price:
            pos.high_price = price

    def hit_trailing_stop(self, pos: Position, price: float) -> bool:
        stop = pos.high_price * (1 - self.settings.trailing_stop_pct)
        return price <= stop
