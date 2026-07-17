from datetime import datetime

from config import Settings
from db.store import Store
from dashboard.app import load_data


def test_load_data_returns_frames(tmp_path):
    store = Store(str(tmp_path / "d.db"))
    store.create_all()
    store.add_balance(ts=datetime(2025, 1, 1), total_krw=1_000_000.0, mode="backtest")
    store.add_trade(ts=datetime(2025, 1, 1), symbol="BTC", side="buy",
                    price=100.0, qty=1.0, fee=0.1, mode="backtest")
    balance, trades = load_data(store)
    assert len(balance) == 1
    assert len(trades) == 1


def test_load_data_filters_by_mode(tmp_path):
    store = Store(str(tmp_path / "dm.db"))
    store.create_all()
    store.add_balance(ts=datetime(2025, 1, 1), total_krw=1_000_000.0, mode="backtest")
    store.add_balance(ts=datetime(2025, 1, 2), total_krw=1_100_000.0, mode="paper")
    store.add_trade(ts=datetime(2025, 1, 2), symbol="BTC", side="buy",
                    price=1.0, qty=1.0, fee=0.0, mode="paper")

    balance, trades = load_data(store, mode="paper")
    assert len(balance) == 1
    assert balance.iloc[0]["mode"] == "paper"
    assert len(trades) == 1
