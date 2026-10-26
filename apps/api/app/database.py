from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, create_engine
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


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


def get_session():
    with SessionLocal() as session:
        yield session
