from datetime import datetime

from config import Settings
from db.store import Store
from dashboard.app import load_data, load_settings


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


def test_load_settings_returns_settings(tmp_path):
    store = Store(str(tmp_path / "ds.db"))
    store.create_all()
    settings = load_settings(store)
    assert isinstance(settings, Settings)
    assert settings.max_volume_pct == 0.01


def test_format_trades_korean_columns():
    import pandas as pd
    from dashboard.app import format_trades, TRADE_COLUMNS
    trades = pd.DataFrame([
        {"ts": "2026-07-18 08:00", "symbol": "ETH", "side": "buy",
         "price": 2_700_000.0, "qty": 0.1, "fee": 100.0, "mode": "paper"},
        {"ts": "2026-07-18 09:00", "symbol": "ETH", "side": "sell",
         "price": 2_900_000.0, "qty": 0.1, "fee": 116.0, "mode": "paper"},
    ])
    out = format_trades(trades)
    assert list(out.columns) == TRADE_COLUMNS
    # 최신순 → 매도가 먼저
    assert out.iloc[0]["구분"] == "매도"
    assert out.iloc[1]["구분"] == "매수"
    # 거래금액 = 체결가 × 수량
    assert out.iloc[1]["거래금액(원)"] == 270000.0   # 2,700,000 × 0.1
    assert out.iloc[0]["거래금액(원)"] == 290000.0   # 2,900,000 × 0.1


def test_format_trades_empty():
    import pandas as pd
    from dashboard.app import format_trades, TRADE_COLUMNS
    out = format_trades(pd.DataFrame())
    assert list(out.columns) == TRADE_COLUMNS
    assert len(out) == 0


def test_holdings_table():
    from dashboard.app import holdings_table, HOLDING_COLUMNS
    from risk.manager import Position
    pos = {"ETH": Position("ETH", entry_price=2_700_000.0, qty=0.1, high_price=2_800_000.0)}
    out = holdings_table(pos)
    assert list(out.columns) == HOLDING_COLUMNS
    assert out.iloc[0]["종목"] == "ETH"
    assert out.iloc[0]["매수금액(원)"] == 270000.0
    assert out.iloc[0]["고점(원)"] == 2_800_000.0


def test_holdings_table_empty():
    from dashboard.app import holdings_table, HOLDING_COLUMNS
    out = holdings_table({})
    assert list(out.columns) == HOLDING_COLUMNS
    assert len(out) == 0


def test_row_color():
    from dashboard.app import row_color
    assert "ffe3e3" in row_color("매수")   # 빨강 계열
    assert "e2edff" in row_color("매도")   # 파랑 계열
    assert row_color("기타") == ""
