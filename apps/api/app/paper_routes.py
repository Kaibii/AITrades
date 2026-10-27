from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from quantpilot.ai import StrategySpec
from quantpilot.market_data import Bar, Dataset
from quantpilot.risk import RiskLimits
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import (
    BacktestRun,
    PaperOrder,
    PaperRiskEvent,
    PaperSession,
    PaperWorkerHeartbeat,
    StrategyDraft,
    get_session,
)
from app.paper import advance

router = APIRouter(prefix="/api/paper", tags=["Historical paper replay"])
SessionDep = Annotated[Session, Depends(get_session)]


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backtest_id: UUID
    limits: RiskLimits = Field(default_factory=RiskLimits)


class StepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_cursor: int = Field(ge=0, strict=True)
    bars: int = Field(default=1, ge=1, le=100, strict=True)


def load(db: Session, session_id: UUID) -> PaperSession:
    row = db.scalar(
        select(PaperSession).where(PaperSession.id == str(session_id)).with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Paper replay session not found")
    return row


def summary(row: PaperSession):
    return {
        "id": row.id,
        "mode": row.mode,
        "status": row.status,
        "draft_id": row.draft_id,
        "backtest_id": row.backtest_id,
        "created_at": row.created_at.isoformat(),
        "last_tick_at": row.last_tick_at.isoformat() if row.last_tick_at else None,
        "cursor": row.cursor,
        "total_bars": len(row.bars),
        "specification": row.specification,
        "configuration": row.configuration,
        "cash": str(row.cash),
        "quantity": str(row.quantity),
        "equity": str(row.equity),
        "peak_equity": str(row.peak_equity),
        "market_date": row.history[-1]["date"] if row.history else None,
    }


def detail(db: Session, row: PaperSession):
    orders = db.scalars(
        select(PaperOrder).where(PaperOrder.session_id == row.id).order_by(PaperOrder.bar_index)
    )
    events = db.scalars(
        select(PaperRiskEvent)
        .where(PaperRiskEvent.session_id == row.id)
        .order_by(PaperRiskEvent.created_at)
    )
    return {
        **summary(row),
        "history": row.history,
        "orders": [
            {
                "id": order.id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "status": order.status,
                "quantity": str(order.quantity),
                "filled_quantity": str(order.filled_quantity),
                "price": str(order.fill_price) if order.fill_price else None,
                "fee": str(order.fee),
                "market_date": order.market_date,
                "reason": order.reason,
            }
            for order in orders
        ],
        "risk_events": [
            {
                "reason": event.reason,
                "market_date": event.market_date,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


@router.get("/status")
def worker_status(db: SessionDep):
    seen = db.scalar(select(func.max(PaperWorkerHeartbeat.last_seen)))
    if seen and seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)
    return {
        "mode": "historical_replay",
        "alpaca_execution_enabled": False,
        "live_trading_enabled": False,
        "worker_last_seen": seen.isoformat() if seen else None,
        "worker_recent": bool(seen and (datetime.now(UTC) - seen).total_seconds() < 20),
    }


@router.post("/sessions", status_code=201)
def create_session(request: CreateSession, db: SessionDep):
    run = db.get(BacktestRun, str(request.backtest_id))
    if run is None:
        raise HTTPException(404, "Backtest not found")
    snapshot = run.result.get("strategy_draft")
    draft = db.get(StrategyDraft, snapshot["id"]) if snapshot else None
    if not draft or not draft.approved_at or snapshot["specification"] != draft.specification:
        raise HTTPException(409, "First backtest an explicitly approved strategy version")
    spec = StrategySpec.model_validate(draft.specification)
    raw_data = run.result["data"]
    records = raw_data.get("records")
    if not records:
        raise HTTPException(409, "Backtest has no reproducible bar records")
    dataset = Dataset([Bar.model_validate(record) for record in records], "", "", "")
    if dataset.version != raw_data["version"]:
        raise HTTPException(409, "Historical data hash mismatch")
    config = run.result["configuration"]
    account = PaperSession(
        draft_id=draft.id,
        backtest_id=run.id,
        specification=spec.model_dump(),
        configuration={
            "limits": request.limits.model_dump(mode="json"),
            "initial_cash": config["initial_cash"],
            "commission_bps": config["commission_bps"],
            "slippage_bps": config["slippage_bps"],
            "data_version": raw_data["version"],
            "data_source": raw_data["source"],
            "adjustment": raw_data["adjustment"],
        },
        bars=records,
        cash=config["initial_cash"],
        equity=config["initial_cash"],
        peak_equity=config["initial_cash"],
        quantity=0,
        cursor=0,
        status="paused",
        mode="historical_replay",
        history=[],
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return detail(db, account)


@router.get("/sessions")
def list_sessions(db: SessionDep):
    rows = db.scalars(select(PaperSession).order_by(PaperSession.created_at.desc()).limit(50))
    return [summary(row) for row in rows]


@router.get("/sessions/{session_id}")
def get_session_detail(session_id: UUID, db: SessionDep):
    return detail(db, load(db, session_id))


@router.post("/sessions/{session_id}/advance")
def advance_session(session_id: UUID, request: StepRequest, db: SessionDep):
    row = load(db, session_id)
    if row.status not in ("paused", "running") and request.expected_cursor >= row.cursor:
        raise HTTPException(409, "Replay is stopped, suspended or complete")
    try:
        row = advance(db, str(session_id), request.expected_cursor, request.bars)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    db.commit()
    return detail(db, row)


@router.post("/sessions/{session_id}/start")
def start_session(session_id: UUID, db: SessionDep):
    row = load(db, session_id)
    if row.status not in ("paused", "running"):
        raise HTTPException(409, "Only a paused replay can be started")
    row.status = "running"
    db.commit()
    return detail(db, row)


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: UUID, db: SessionDep):
    row = load(db, session_id)
    if row.status == "running":
        row.status = "paused"
    db.commit()
    return detail(db, row)


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: UUID, db: SessionDep):
    row = load(db, session_id)
    if row.status != "completed":
        row.status = "stopped"
    db.commit()
    # No new orders, no further bars. Already-filled orders and positions are retained.
    return detail(db, row)
