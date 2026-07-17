from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session

from db.models import Base, Trade, SignalLog, BalanceLog, OpenPosition, PaperAccount
from risk.manager import Position


class Store:
    def __init__(self, db_path: str | None = None, url: str | None = None):
        if url is None:
            if db_path is None:
                raise ValueError("db_path 또는 url 중 하나는 필요하다")
            url = f"sqlite:///{db_path}"
        self.engine = create_engine(url)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def add_trade(self, **kwargs) -> None:
        with Session(self.engine) as s:
            s.add(Trade(**kwargs))
            s.commit()

    def add_signal(self, **kwargs) -> None:
        with Session(self.engine) as s:
            s.add(SignalLog(**kwargs))
            s.commit()

    def add_balance(self, **kwargs) -> None:
        with Session(self.engine) as s:
            s.add(BalanceLog(**kwargs))
            s.commit()

    def trades_df(self) -> pd.DataFrame:
        return pd.read_sql(select(Trade).order_by(Trade.ts), self.engine)

    def balance_df(self) -> pd.DataFrame:
        return pd.read_sql(select(BalanceLog).order_by(BalanceLog.ts), self.engine)

    def get_account(self, mode: str) -> float | None:
        with Session(self.engine) as s:
            row = s.scalars(
                select(PaperAccount).where(PaperAccount.mode == mode)
            ).first()
            return row.cash_krw if row else None

    def save_account(self, mode: str, cash: float) -> None:
        with Session(self.engine) as s:
            row = s.scalars(
                select(PaperAccount).where(PaperAccount.mode == mode)
            ).first()
            if row:
                row.cash_krw = cash
                row.updated_at = datetime.now()
            else:
                s.add(PaperAccount(mode=mode, cash_krw=cash, updated_at=datetime.now()))
            s.commit()

    def get_positions(self, mode: str) -> dict[str, Position]:
        with Session(self.engine) as s:
            rows = s.scalars(
                select(OpenPosition).where(OpenPosition.mode == mode)
            ).all()
            return {
                r.symbol: Position(r.symbol, r.entry_price, r.qty, r.high_price)
                for r in rows
            }

    def add_position(self, pos: Position, mode: str) -> None:
        with Session(self.engine) as s:
            s.add(OpenPosition(
                symbol=pos.symbol, entry_price=pos.entry_price, qty=pos.qty,
                high_price=pos.high_price, opened_at=datetime.now(), mode=mode,
            ))
            s.commit()

    def remove_position(self, symbol: str, mode: str) -> None:
        with Session(self.engine) as s:
            s.execute(delete(OpenPosition).where(
                OpenPosition.mode == mode, OpenPosition.symbol == symbol))
            s.commit()

    def update_position_high(self, symbol: str, mode: str, high: float) -> None:
        with Session(self.engine) as s:
            row = s.scalars(select(OpenPosition).where(
                OpenPosition.mode == mode, OpenPosition.symbol == symbol)).first()
            if row:
                row.high_price = high
                s.commit()
