from risk.manager import Position
from db.store import Store


def _store(tmp_path):
    s = Store(str(tmp_path / "p.db"))
    s.create_all()
    return s


def test_account_upsert(tmp_path):
    s = _store(tmp_path)
    assert s.get_account("paper") is None
    s.save_account("paper", 1_000_000.0)
    assert s.get_account("paper") == 1_000_000.0
    s.save_account("paper", 950_000.0)          # 갱신
    assert s.get_account("paper") == 950_000.0


def test_positions_crud(tmp_path):
    s = _store(tmp_path)
    assert s.get_positions("paper") == {}
    s.add_position(Position("BTC", entry_price=100.0, qty=2.0, high_price=100.0), "paper")
    s.add_position(Position("ETH", entry_price=50.0, qty=4.0, high_price=50.0), "paper")
    pos = s.get_positions("paper")
    assert set(pos) == {"BTC", "ETH"}
    assert pos["BTC"].qty == 2.0 and pos["BTC"].entry_price == 100.0

    s.update_position_high("BTC", "paper", 130.0)
    assert s.get_positions("paper")["BTC"].high_price == 130.0

    s.remove_position("BTC", "paper")
    assert set(s.get_positions("paper")) == {"ETH"}
