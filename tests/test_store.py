from datetime import datetime

from db.store import Store


def test_add_and_read_trade(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.create_all()
    store.add_trade(ts=datetime(2025, 1, 1), symbol="BTC", side="buy",
                    price=100.0, qty=2.0, fee=0.5, mode="backtest")
    df = store.trades_df()
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "BTC"
    assert df.iloc[0]["side"] == "buy"


def test_balance_log(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.create_all()
    store.add_balance(ts=datetime(2025, 1, 1), total_krw=1_000_000.0, mode="backtest")
    store.add_balance(ts=datetime(2025, 1, 2), total_krw=1_050_000.0, mode="backtest")
    df = store.balance_df()
    assert len(df) == 2
    assert df.iloc[-1]["total_krw"] == 1_050_000.0
