"""Atomic, restart-safe historical paper replay; never calls a network broker."""

import hashlib
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from quantpilot.ai import StrategySpec
from quantpilot.execution import HistoricalPaperBroker, OrderIntent, validate_order_update
from quantpilot.market_data import Bar
from quantpilot.risk import RiskLimits, order_breach, portfolio_breach
from quantpilot.strategies import crossovers
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import PaperOrder, PaperRiskEvent, PaperSession


def risk_event(db: Session, account: PaperSession, reason: str, market_date: str | None):
    account.status = "suspended"
    db.add(PaperRiskEvent(session_id=account.id, reason=reason, market_date=market_date))


def tick(db: Session, account: PaperSession) -> None:
    if account.mode != "historical_replay":
        raise ValueError("Only historical replay is enabled")
    if account.status not in ("paused", "running"):
        return
    i = account.cursor
    if i >= len(account.bars):
        account.status = "completed"
        return
    bar = Bar.model_validate(account.bars[i])
    spec = StrategySpec.model_validate(account.specification)
    limits = RiskLimits.model_validate(account.configuration["limits"])
    previous_equity = account.equity
    opening_equity = account.cash + account.quantity * bar.open
    reason = portfolio_breach(opening_equity, account.peak_equity, previous_equity, limits)
    if reason:
        risk_event(db, account, reason, str(bar.date))
    else:
        # The current bar close is excluded from signal evaluation.
        closes = [Bar.model_validate(row).close for row in account.bars[:i]]
        signal = crossovers(closes, spec.fast, spec.slow)[-1] if closes else None
        if signal == "buy" and account.quantity == 0 or signal == "sell" and account.quantity > 0:
            _execute(db, account, bar, signal, opening_equity, limits)
    account.equity = account.cash + account.quantity * bar.close
    closing_breach = portfolio_breach(account.equity, account.peak_equity, previous_equity, limits)
    if closing_breach and account.status != "suspended":
        risk_event(db, account, closing_breach, str(bar.date))
    account.peak_equity = max(account.peak_equity, account.equity)
    account.history = [
        *account.history,
        {
            "date": str(bar.date),
            "cash": str(account.cash),
            "quantity": str(account.quantity),
            "equity": str(account.equity),
            "close": str(bar.close),
        },
    ]
    account.cursor += 1
    account.last_tick_at = datetime.now(UTC)
    if account.cursor >= len(account.bars) and account.status != "suspended":
        account.status = "completed"


def _execute(
    db: Session, account: PaperSession, bar: Bar, side: str, equity: Decimal, limits: RiskLimits
):
    config = account.configuration
    broker = HistoricalPaperBroker(
        bar.open, Decimal(config["slippage_bps"]), Decimal(config["commission_bps"])
    )
    price = broker.quote(side)
    fee_rate = Decimal(config["commission_bps"]) / 10000
    if side == "buy":
        budget = min(
            equity * limits.allocation_pct / 100,
            limits.max_order_notional,
            equity * limits.max_position_pct / 100,
            account.cash / (1 + fee_rate),
        )
        quantity = (budget / price).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    else:
        quantity = account.quantity
    if quantity <= 0:
        risk_event(db, account, "Order rounded below minimum replay quantity", str(bar.date))
        return
    client_id = hashlib.sha256(f"{account.id}:{account.cursor}:{side}".encode()).hexdigest()[:40]
    intent = OrderIntent(
        client_order_id=client_id,
        symbol=account.specification["symbol"],
        side=side,
        quantity=quantity,
    )
    # Persisted uniqueness and the session row lock prevent duplicate signals across workers.
    existing = db.scalar(select(PaperOrder).where(PaperOrder.client_order_id == client_id))
    if existing is not None:
        raise ValueError("Order already exists for unprocessed bar; inspect replay state")
    fee = quantity * price * fee_rate
    reason = order_breach(
        side=side,
        quantity=quantity,
        price=price,
        fee=fee,
        cash=account.cash,
        current_quantity=account.quantity,
        equity=equity,
        orders_this_bar=0,
        limits=limits,
    )
    order = PaperOrder(
        session_id=account.id,
        client_order_id=client_id,
        bar_index=account.cursor,
        market_date=str(bar.date),
        symbol=intent.symbol,
        side=side,
        status="rejected" if reason else "accepted",
        quantity=quantity,
        filled_quantity=Decimal(0),
        fee=Decimal(0),
        reason=reason,
    )
    db.add(order)
    if reason:
        risk_event(db, account, reason, str(bar.date))
        return
    update = broker.submit_order(intent)
    validate_order_update(intent, None, update)
    notional = update.filled_quantity * update.average_fill_price
    if side == "buy":
        account.cash -= notional + update.fee
        account.quantity += update.filled_quantity
    else:
        account.cash += notional - update.fee
        account.quantity -= update.filled_quantity
    order.status, order.filled_quantity = update.status, update.filled_quantity
    order.fill_price, order.fee = update.average_fill_price, update.fee


def advance(
    db: Session, session_id: str, expected_cursor: int, bars: int = 1, *, skip_locked: bool = False
) -> PaperSession | None:
    # PostgreSQL serializes state transitions; a crash rolls back cursor, journal and cash together.
    account = db.scalar(
        select(PaperSession)
        .where(PaperSession.id == session_id)
        .with_for_update(skip_locked=skip_locked)
    )
    if account is None:
        return None
    if skip_locked and account.status != "running":
        return account
    if expected_cursor < account.cursor:
        return account  # Retry of an already processed request has no additional effects.
    if expected_cursor > account.cursor:
        raise ValueError("Replay cursor is ahead of persisted state")
    for _ in range(bars):
        if account.status not in ("paused", "running"):
            break
        tick(db, account)
    db.flush()
    return account
