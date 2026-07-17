from config import Settings
from risk.manager import RiskManager, Position


def test_can_enter_respects_max_positions():
    rm = RiskManager(Settings(max_positions=2))
    assert rm.can_enter({}) is True
    two = {"BTC": Position("BTC", 1, 1, 1), "ETH": Position("ETH", 1, 1, 1)}
    assert rm.can_enter(two) is False


def test_position_size():
    rm = RiskManager(Settings(position_pct=0.20))
    # 자본 1,000,000의 20% = 200,000 / 가격 100 = 2000
    assert rm.position_size(1_000_000, 100) == 2000.0


def test_trailing_stop_triggers_after_high():
    rm = RiskManager(Settings(trailing_stop_pct=0.05))
    pos = Position("BTC", entry_price=100, qty=1, high_price=100)
    rm.update_high(pos, 120)
    assert pos.high_price == 120
    assert rm.hit_trailing_stop(pos, 115) is False   # 120*0.95=114 > 115
    assert rm.hit_trailing_stop(pos, 113) is True     # 113 < 114
