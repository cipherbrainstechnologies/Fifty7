from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Index,
)

from .db import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=True, index=True)

    symbol = Column(String(64), nullable=False, index=True)
    side = Column(String(4), nullable=False)  # BUY/SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(18, 6), nullable=False)
    fees = Column(Numeric(18, 6), nullable=True)

    order_id = Column(String(64), nullable=True, index=True)
    broker = Column(String(32), nullable=True)

    traded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", "order_id", "symbol", "traded_at", name="uq_trade_idem"),
        Index("ix_trades_org_user_time", "org_id", "user_id", "traded_at"),
    )


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)

    symbol = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    average_price = Column(Numeric(18, 6), nullable=False)
    mtm_pnl = Column(Numeric(18, 6), nullable=True)

    snapshot_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_pos_snap_org_user_symbol_time", "org_id", "user_id", "symbol", "snapshot_at"),
    )


class MissedTrade(Base):
    __tablename__ = "missed_trades"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)

    direction = Column(String(4), nullable=False)
    strike = Column(Integer, nullable=True)

    entry_price = Column(Numeric(18, 6), nullable=True)
    sl_price = Column(Numeric(18, 6), nullable=True)
    tp_price = Column(Numeric(18, 6), nullable=True)

    range_high = Column(Numeric(18, 6), nullable=True)
    range_low = Column(Numeric(18, 6), nullable=True)

    inside_bar_time = Column(DateTime(timezone=True), nullable=True)
    signal_time = Column(DateTime(timezone=True), nullable=True)
    breakout_close = Column(Numeric(18, 6), nullable=True)

    reason = Column(String(255), nullable=True)

    logged_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_missed_trades_org_user_logged", "org_id", "user_id", "logged_at"),
    )


