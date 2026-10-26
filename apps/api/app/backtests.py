import logging

from fastapi import HTTPException
from quantpilot.ai import StrategySpec
from quantpilot.backtesting import BacktestConfig, run_backtest
from quantpilot.market_data import AlpacaProvider, DataError, SampleProvider
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import BacktestRun, StrategyDraft


async def execute_backtest(
    config: BacktestConfig, session: Session, draft: StrategyDraft | None = None
):
    provider = (
        SampleProvider()
        if config.provider == "sample"
        else AlpacaProvider(
            settings.apca_api_key_id.get_secret_value(),
            settings.apca_api_secret_key.get_secret_value(),
        )
    )
    try:
        data = await run_in_threadpool(provider.history, config.symbol, config.start, config.end)
        result = await run_in_threadpool(run_backtest, config, data)
    except (DataError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if draft is not None:
        result["strategy_draft"] = {
            "id": draft.id,
            "approved_at": draft.approved_at.isoformat(),
            "origin": draft.origin,
            "specification": StrategySpec.model_validate(draft.specification).model_dump(),
        }
    row = BacktestRun(result=result)
    session.add(row)
    session.commit()
    session.refresh(row)
    logging.getLogger("quantpilot").info(
        "backtest_completed", extra={"run_id": row.id, "provider": config.provider}
    )
    return {"id": row.id, "created_at": row.created_at.isoformat(), **result}
