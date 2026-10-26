from decimal import Decimal

from quantpilot.indicators import sma


def crossovers(closes: list[Decimal], fast: int, slow: int) -> list[str | None]:
    if not 1 <= fast < slow:
        raise ValueError("Require 1 <= fast < slow")
    short, long = sma(closes, fast), sma(closes, slow)
    signals: list[str | None] = [None] * len(closes)
    for i in range(slow, len(closes)):
        previous = short[i - 1] - long[i - 1]
        current = short[i] - long[i]
        if previous <= 0 < current:
            signals[i] = "buy"
        elif previous >= 0 > current:
            signals[i] = "sell"
    return signals
