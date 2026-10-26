import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from quantpilot.backtesting import BacktestConfig
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.backtests import execute_backtest
from app.config import settings
from app.database import BacktestRun, get_session
from app.logging import configure_logging
from app.strategy_routes import router as strategy_router

configure_logging()
logger = logging.getLogger("quantpilot")
app = FastAPI(title="QuantPilot Research API", version="0.1.0")
SessionDep = Annotated[Session, Depends(get_session)]
app.include_router(strategy_router)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    # Do not serialize database URLs, parameters, or exception details.
    from fastapi.responses import JSONResponse

    logger.error("database_operation_failed")
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable; check migrations."}
    )


@app.get("/health")
def health(session: SessionDep):
    session.execute(text("SELECT 1 FROM backtest_runs LIMIT 1"))
    return {"status": "ok", "mode": "research-only", "live_trading_enabled": False}


@app.get("/api/capabilities")
def capabilities():
    return {
        "mode": "research-only",
        "live_trading_enabled": False,
        "ai_configured": bool(settings.ai_api_key.get_secret_value()),
        "ai_model": settings.ai_model,
        "sample": {"symbol": "AAPL", "start": "2015-02-17", "end": "2017-02-16"},
        "alpaca_configured": bool(
            settings.apca_api_key_id.get_secret_value()
            and settings.apca_api_secret_key.get_secret_value()
        ),
    }


@app.post("/api/backtests", status_code=201)
async def create_backtest(config: BacktestConfig, session: SessionDep):
    return await execute_backtest(config, session)


@app.get("/api/backtests")
def list_backtests(session: SessionDep):
    rows = session.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(20))
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "configuration": row.result["configuration"],
            "metrics": row.result["metrics"],
        }
        for row in rows
    ]


@app.get("/api/backtests/{run_id}")
def get_backtest(run_id: UUID, session: SessionDep):
    row = session.get(BacktestRun, str(run_id))
    if row is None:
        raise HTTPException(404, "Backtest not found")
    return {"id": row.id, "created_at": row.created_at.isoformat(), **row.result}
