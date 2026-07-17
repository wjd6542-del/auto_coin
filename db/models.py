from datetime import datetime

from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))
    price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))


class SignalLog(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    symbol: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(4))
    rsi: Mapped[float] = mapped_column(Float)
    short_ma: Mapped[float] = mapped_column(Float)
    long_ma: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))


class BalanceLog(Base):
    __tablename__ = "balance_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    total_krw: Mapped[float] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(10))
