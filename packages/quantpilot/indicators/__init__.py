from decimal import Decimal


def sma(values: list[Decimal], period: int) -> list[Decimal | None]:
    """Trailing SMA; warm-up values are unavailable, never zero-filled."""
    if period < 1:
        raise ValueError("SMA period must be positive")
    result: list[Decimal | None] = []
    total = Decimal(0)
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        result.append(total / period if i >= period - 1 else None)
    return result
