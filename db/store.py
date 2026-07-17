import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db.models import Base, Trade, SignalLog, BalanceLog


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
        return pd.read_sql(select(Trade), self.engine)

    def balance_df(self) -> pd.DataFrame:
        return pd.read_sql(select(BalanceLog), self.engine)
