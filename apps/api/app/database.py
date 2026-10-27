from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    result: Mapped[dict] = mapped_column(JSON, nullable=False)


class StrategyDraft(Base):
    __tablename__ = "strategy_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("strategy_drafts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    specification: Mapped[dict] = mapped_column(JSON, nullable=False)


class PaperSession(Base):
    __tablename__ = "paper_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    draft_id: Mapped[str] = mapped_column(ForeignKey("strategy_drafts.id"), nullable=False)
    backtest_id: Mapped[str] = mapped_column(ForeignKey("backtest_runs.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="historical_replay")
    status: Mapped[str] = mapped_column(String(20), default="paused")
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    specification: Mapped[dict] = mapped_column(JSON, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    bars: Mapped[list] = mapped_column(JSON, nullable=False)
    history: Mapped[list] = mapped_column(JSON, default=list)
    cash: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    equity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    peak_equity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (UniqueConstraint("session_id", "bar_index", "side", name="uq_paper_signal"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("paper_sessions.id"), nullable=False, index=True
    )
    client_order_id: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    bar_index: Mapped[int] = mapped_column(Integer, nullable=False)
    market_date: Mapped[str] = mapped_column(String(10), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(38, 18), nullable=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(38, 18), default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaperRiskEvent(Base):
    __tablename__ = "paper_risk_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("paper_sessions.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    market_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class PaperWorkerHeartbeat(Base):
    __tablename__ = "paper_worker_heartbeats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


def get_session():
    with SessionLocal() as session:
        yield session
