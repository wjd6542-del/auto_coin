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


def test_position_size_volume_cap():
    from config import Settings
    from risk.manager import RiskManager
    rm = RiskManager(Settings(position_pct=0.20, max_volume_pct=0.01))
    # 총자산 1,000,000의 20% = 200,000
    # 코인 일거래대금 5,000,000의 1% = 50,000 (상한이 더 작음)
    # → 50,000 / 가격 100 = 500
    assert rm.position_size(1_000_000, 100, daily_value=5_000_000) == 500.0
    # 상한이 크면(1억*1%=100만 > 20만) 기존 값 유지 → 200,000/100 = 2000
    assert rm.position_size(1_000_000, 100, daily_value=100_000_000) == 2000.0
    # daily_value 없으면 기존 동작
    assert rm.position_size(1_000_000, 100) == 2000.0
