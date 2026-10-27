"""Paper-only order interfaces. No live execution adapter exists."""

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    client_order_id: str = Field(min_length=1, max_length=48, pattern=r"^[a-zA-Z0-9_-]+$")
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)


class OrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    client_order_id: str
    broker_order_id: str
    status: Literal["accepted", "partially_filled", "filled", "rejected", "canceled", "unknown"]
    filled_quantity: Decimal = Field(ge=0)
    average_fill_price: Decimal | None = Field(default=None, gt=0)
    fee: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def priced_fills(self):
        if self.filled_quantity > 0 and self.average_fill_price is None:
            raise ValueError("A fill must have a positive price")
        return self


class PaperBroker(Protocol):
    def submit_order(self, intent: OrderIntent) -> OrderUpdate: ...
    def get_order(self, client_order_id: str) -> OrderUpdate | None: ...
    def cancel_order(self, broker_order_id: str) -> None: ...


def validate_order_update(
    intent: OrderIntent, previous: OrderUpdate | None, update: OrderUpdate
) -> None:
    if update.client_order_id != intent.client_order_id or update.filled_quantity > intent.quantity:
        raise ValueError("Order update does not match its persisted intent")
    if update.status == "filled" and update.filled_quantity != intent.quantity:
        raise ValueError("Filled status requires the entire ordered quantity")
    if update.status == "partially_filled" and not 0 < update.filled_quantity < intent.quantity:
        raise ValueError("Partial-fill quantity must be between zero and order quantity")
    if update.status in ("accepted", "rejected") and update.filled_quantity:
        raise ValueError("Unfilled order state cannot contain executions")
    if previous:
        if previous.broker_order_id != update.broker_order_id:
            raise ValueError("Broker order identifier changed")
        if update.filled_quantity < previous.filled_quantity or update.fee < previous.fee:
            raise ValueError("Cumulative executions cannot decrease")
        if previous.status in ("filled", "rejected", "canceled") and update != previous:
            raise ValueError("Terminal order state cannot change")
        if previous.status == "partially_filled" and update.status == "accepted":
            raise ValueError("Order state cannot move backwards")


class HistoricalPaperBroker:
    """One-bar fill adapter. The application persists fills and idempotency in PostgreSQL."""

    def __init__(self, opening_price: Decimal, slippage_bps: Decimal, commission_bps: Decimal):
        self.opening_price = opening_price
        self.slippage_bps, self.commission_bps = slippage_bps, commission_bps

    def quote(self, side: str) -> Decimal:
        adjustment = self.slippage_bps / 10000
        return self.opening_price * (1 + adjustment if side == "buy" else 1 - adjustment)

    def submit_order(self, intent: OrderIntent) -> OrderUpdate:
        price = self.quote(intent.side)
        return OrderUpdate(
            client_order_id=intent.client_order_id,
            broker_order_id=intent.client_order_id,
            status="filled",
            filled_quantity=intent.quantity,
            average_fill_price=price,
            fee=intent.quantity * price * self.commission_bps / 10000,
        )

    def get_order(self, client_order_id: str) -> OrderUpdate | None:
        # Replay has no external service to reconcile; durable journal is authoritative.
        return None

    def cancel_order(self, broker_order_id: str) -> None:
        raise ValueError("Replay fills are immediate and cannot be canceled retroactively")
