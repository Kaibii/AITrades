"""Deterministic pre-trade controls, independent of AI and brokerage access."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    allocation_pct: Decimal = Field(default=Decimal("10"), gt=0, le=100)
    max_position_pct: Decimal = Field(default=Decimal("25"), gt=0, le=100)
    max_order_notional: Decimal = Field(default=Decimal("2500"), ge=1, le=100000000)
    max_daily_loss_pct: Decimal = Field(default=Decimal("2"), gt=0, le=100)
    max_drawdown_pct: Decimal = Field(default=Decimal("10"), gt=0, le=100)
    max_orders_per_bar: int = Field(default=1, ge=1, le=1, strict=True)

    @model_validator(mode="after")
    def valid_allocation(self):
        if self.allocation_pct > self.max_position_pct:
            raise ValueError("Allocation must not exceed the maximum position limit")
        return self


def portfolio_breach(
    equity: Decimal, peak: Decimal, day_start: Decimal, limits: RiskLimits
) -> str | None:
    if equity <= 0:
        return "Portfolio equity is non-positive"
    if peak > 0 and (peak - equity) / peak * 100 >= limits.max_drawdown_pct:
        return "Maximum drawdown reached"
    if day_start > 0 and (day_start - equity) / day_start * 100 >= limits.max_daily_loss_pct:
        return "Maximum daily loss reached"
    return None


def order_breach(
    *,
    side: str,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal,
    cash: Decimal,
    current_quantity: Decimal,
    equity: Decimal,
    orders_this_bar: int,
    limits: RiskLimits,
) -> str | None:
    notional = quantity * price
    if quantity <= 0 or price <= 0:
        return "Order quantity and price must be positive"
    if orders_this_bar >= limits.max_orders_per_bar:
        return "Order frequency limit reached"
    if notional > limits.max_order_notional:
        return "Maximum order notional exceeded"
    if side == "buy":
        if notional + fee > cash:
            return "Insufficient buying power"
        if (current_quantity + quantity) * price > equity * limits.max_position_pct / 100:
            return "Maximum position exposure exceeded"
    elif side == "sell":
        if quantity > current_quantity:
            return "Short selling is prohibited"
    else:
        return "Unsupported order side"
    return None
