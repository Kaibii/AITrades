from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from quantpilot.ai import (
    GenerationError,
    OpenAIStrategyGenerator,
    Proposal,
    StrategyGenerator,
    StrategySpec,
)
from quantpilot.backtesting import BacktestConfig
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.backtests import execute_backtest
from app.config import settings
from app.database import StrategyDraft, get_session

router = APIRouter(prefix="/api/strategy-drafts", tags=["Strategy drafts"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_generator() -> StrategyGenerator:
    key = settings.ai_api_key.get_secret_value()
    if not key:
        raise HTTPException(
            503, "AI is not configured. Set QUANTPILOT_AI_API_KEY securely on the server."
        )
    return OpenAIStrategyGenerator(key, settings.ai_model)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(min_length=10, max_length=4000)


class SaveDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: StrategySpec
    parent_id: UUID | None = None


class RunOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    provider: Literal["sample", "alpaca"] = "sample"
    start: date = date(2015, 2, 17)
    end: date = date(2017, 2, 16)
    initial_cash: Decimal = Field(default=Decimal("10000"), ge=100, le=100000000)
    allocation: Decimal = Field(default=Decimal("0.95"), gt=0, le=1)
    commission_bps: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0, le=100)


def serialize(draft: StrategyDraft):
    return {
        "id": draft.id,
        "parent_id": draft.parent_id,
        "created_at": draft.created_at.isoformat(),
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "origin": draft.origin,
        "prompt": draft.prompt,
        "explanation": draft.explanation,
        "specification": draft.specification,
    }


def load_draft(session: Session, draft_id: UUID) -> StrategyDraft:
    draft = session.get(StrategyDraft, str(draft_id))
    if draft is None:
        raise HTTPException(404, "Strategy draft not found")
    return draft


@router.post("/generate")
async def generate_draft(
    request: GenerateRequest,
    session: SessionDep,
    generator: Annotated[StrategyGenerator, Depends(get_generator)],
):
    try:
        proposal = await run_in_threadpool(generator.generate, request.prompt)
        # Validate even injected provider implementations before persistence.
        proposal = Proposal.model_validate(proposal.model_dump())
    except (GenerationError, ValidationError):
        raise HTTPException(
            502,
            "AI could not produce a valid strategy draft. Check provider "
            "configuration or clarify the supported SMA crossover rules.",
        ) from None
    if proposal.status == "unsupported":
        return {"status": "unsupported", "explanation": proposal.explanation, "draft": None}
    draft = StrategyDraft(
        origin="ai",
        prompt=request.prompt,
        explanation=proposal.explanation,
        specification=proposal.specification.model_dump(),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return {"status": "supported", "explanation": proposal.explanation, "draft": serialize(draft)}


@router.post("", status_code=201)
def save_draft(request: SaveDraftRequest, session: SessionDep):
    parent = load_draft(session, request.parent_id) if request.parent_id else None
    draft = StrategyDraft(
        parent_id=parent.id if parent else None,
        origin="manual",
        prompt=parent.prompt if parent else None,
        explanation="User-edited strategy version. "
        "Review all rules before approving for backtesting.",
        specification=request.specification.model_dump(),
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)
    return serialize(draft)


@router.get("")
def list_drafts(session: SessionDep):
    drafts = session.scalars(
        select(StrategyDraft).order_by(StrategyDraft.created_at.desc()).limit(50)
    )
    return [serialize(draft) for draft in drafts]


@router.get("/{draft_id}")
def get_draft(draft_id: UUID, session: SessionDep):
    return serialize(load_draft(session, draft_id))


@router.post("/{draft_id}/approve")
def approve_draft(draft_id: UUID, session: SessionDep):
    draft = load_draft(session, draft_id)
    StrategySpec.model_validate(draft.specification)
    if draft.approved_at is None:
        draft.approved_at = datetime.now(UTC)
        session.commit()
        session.refresh(draft)
    return serialize(draft)


@router.post("/{draft_id}/backtests", status_code=201)
async def backtest_draft(draft_id: UUID, options: RunOptions, session: SessionDep):
    draft = load_draft(session, draft_id)
    if draft.approved_at is None:
        raise HTTPException(409, "Review and explicitly approve this strategy version first.")
    spec = StrategySpec.model_validate(draft.specification)
    try:
        config = BacktestConfig(
            **options.model_dump(), symbol=spec.symbol, fast=spec.fast, slow=spec.slow
        )
    except ValidationError:
        raise HTTPException(
            422, "Invalid backtest configuration: check dates and limits."
        ) from None
    return await execute_backtest(config, session, draft)
