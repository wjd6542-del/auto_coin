from datetime import datetime

from sqlalchemy import String, Float, DateTime, Integer, Boolean
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


class OpenPosition(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    entry_price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    high_price: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    mode: Mapped[str] = mapped_column(String(10))


class PaperAccount(Base):
    __tablename__ = "paper_account"
    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(10))
    cash_krw: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class AppSettings(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    short_period: Mapped[int] = mapped_column(Integer)
    long_period: Mapped[int] = mapped_column(Integer)
    rsi_period: Mapped[int] = mapped_column(Integer)
    rsi_oversold: Mapped[float] = mapped_column(Float)
    rsi_recover: Mapped[float] = mapped_column(Float)
    use_rsi_filter: Mapped[bool] = mapped_column(Boolean)
    trailing_stop_pct: Mapped[float] = mapped_column(Float)
    max_positions: Mapped[int] = mapped_column(Integer)
    position_pct: Mapped[float] = mapped_column(Float)
    max_volume_pct: Mapped[float] = mapped_column(Float)
    top_n: Mapped[int] = mapped_column(Integer)
    min_trade_value_krw: Mapped[float] = mapped_column(Float)
    initial_capital: Mapped[float] = mapped_column(Float)
    fee_rate: Mapped[float] = mapped_column(Float)
