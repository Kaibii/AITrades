import math
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantpilot.market_data import Dataset
from quantpilot.strategies import crossovers


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    symbol: str = Field(default="AAPL", pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")
    provider: Literal["sample", "alpaca"] = "sample"
    start: date = date(2015, 2, 17)
    end: date = date(2017, 2, 16)
    fast: int = Field(default=20, ge=1, le=250, strict=True)
    slow: int = Field(default=50, ge=2, le=500, strict=True)
    initial_cash: Decimal = Field(default=Decimal("10000"), ge=100, le=100000000)
    allocation: Decimal = Field(default=Decimal("0.95"), gt=0, le=1)
    commission_bps: Decimal = Field(default=Decimal("5"), ge=0, le=100)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0, le=100)

    @model_validator(mode="after")
    def validate_config(self):
        if self.fast >= self.slow:
            raise ValueError("Fast period must be smaller than slow period")
        if self.start >= self.end or (self.end - self.start).days > 7305:
            raise ValueError("Date range must be increasing and at most 20 years")
        if self.end >= date.today():
            raise ValueError("End date must precede today to exclude incomplete daily bars")
        return self


def run_backtest(config: BacktestConfig, data: Dataset) -> dict:
    bars = data.bars
    if not config.slow + 2 <= len(bars) <= 6000:
        raise ValueError("Need at least slow period + 2 daily bars and at most 6000 bars")
    if any(a.date >= b.date for a, b in zip(bars, bars[1:], strict=False)):
        raise ValueError("Bars must have unique, strictly increasing dates")
    if bars[0].date < config.start or bars[-1].date > config.end:
        raise ValueError("Provider returned bars outside the requested date range")
    signals = crossovers([bar.close for bar in bars], config.fast, config.slow)
    zero = Decimal(0)
    cash, qty = config.initial_cash, zero
    fee_rate, slip = config.commission_bps / 10000, config.slippage_bps / 10000
    entry = None
    trades, fills, curve = [], [], []
    turnover, total_fees = zero, zero
    for i, bar in enumerate(bars):
        # Today's open only sees the preceding completed bar's signal.
        signal = signals[i - 1] if i else None
        if signal == "buy" and qty == 0:
            price = bar.open * (1 + slip)
            qty = (cash * config.allocation / (price * (1 + fee_rate))).quantize(
                Decimal("0.000001"), rounding=ROUND_DOWN
            )
            if qty:
                notional = qty * price
                fee = notional * fee_rate
                cost = notional + fee
                cash -= cost
                entry = {"date": bar.date, "price": price, "cost": cost, "index": i}
                fills.append(
                    {
                        "date": str(bar.date),
                        "side": "buy",
                        "quantity": float(qty),
                        "price": float(price),
                        "fee": float(fee),
                    }
                )
                turnover += notional
                total_fees += fee
        elif signal == "sell" and qty > 0:
            price = bar.open * (1 - slip)
            notional = qty * price
            fee = notional * fee_rate
            proceeds = notional - fee
            profit = proceeds - entry["cost"]
            cash += proceeds
            fills.append(
                {
                    "date": str(bar.date),
                    "side": "sell",
                    "quantity": float(qty),
                    "price": float(price),
                    "fee": float(fee),
                }
            )
            trades.append(
                {
                    "entry_date": str(entry["date"]),
                    "exit_date": str(bar.date),
                    "quantity": float(qty),
                    "entry_price": float(entry["price"]),
                    "exit_price": float(price),
                    "net_pnl": float(profit),
                    "return_pct": float(profit / entry["cost"] * 100),
                    "holding_bars": i - entry["index"],
                }
            )
            turnover += notional
            total_fees += fee
            qty, entry = zero, None
        equity = cash + qty * bar.close
        curve.append(
            {
                "date": str(bar.date),
                "equity": float(equity),
                "benchmark": float(config.initial_cash * bar.close / bars[0].close),
                "cash": float(cash),
            }
        )

    values = [float(config.initial_cash)] + [point["equity"] for point in curve]
    returns = [b / a - 1 for a, b in zip(values, values[1:], strict=False)]
    # Sample standard deviation; risk-free rate 0; 252 trading sessions/year.
    daily = returns[1:]
    mean = sum(daily) / len(daily)
    variance = sum((x - mean) ** 2 for x in daily) / (len(daily) - 1)
    volatility = math.sqrt(variance)
    sharpe = mean / volatility * math.sqrt(252) if volatility > 1e-12 else None
    peak, max_drawdown = values[0], 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        point["drawdown_pct"] = (point["equity"] / peak - 1) * 100
        max_drawdown = min(max_drawdown, point["drawdown_pct"])
    final = values[-1]
    ratio = final / float(config.initial_cash)
    years = (bars[-1].date - bars[0].date).days / 365.25
    annualized_log = math.log(ratio) / years
    annualized = math.expm1(annualized_log) * 100 if annualized_log < 700 else None
    wins = [t["net_pnl"] for t in trades if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in trades if t["net_pnl"] < 0]
    realized = sum(t["net_pnl"] for t in trades)
    unrealized = qty * bars[-1].close - entry["cost"] if entry else zero
    return {
        "engine_version": "sma-next-open-v1",
        "strategy_version": "sma-crossover-v1",
        "configuration": config.model_dump(mode="json"),
        "data": {
            "source": data.source,
            "records": [bar.model_dump(mode="json") for bar in bars],
            "version": data.version,
            "adjustment": data.adjustment,
            "license_note": data.license_note,
            "bars": len(bars),
            "first_date": str(bars[0].date),
            "last_date": str(bars[-1].date),
        },
        "assumptions": [
            "Hypothetical research only. No real trades executed.",
            "Long-only, one security; crossover at completed close fills next available bar open.",
            "No pre-range warm-up; first eligible signal requires two fully formed SMAs.",
            "Fractional adjusted-share quantities to 6 decimals; no leverage or shorting.",
            "Slippage and commission applied per fill; no cash interest, taxes or liquidity model.",
            "Open final position marked at last close, not forcibly sold; exit costs not accrued.",
            "Sharpe uses sample daily volatility, 252 sessions/year and zero risk-free rate.",
            "Benchmark buys adjusted series at first close, without fees; "
            "comparison is indicative.",
            "Historical sample selection may introduce survivorship bias; no predictive claims.",
        ],
        "metrics": {
            "initial_equity": float(config.initial_cash),
            "final_equity": final,
            "total_return_pct": (ratio - 1) * 100,
            "annualized_return_pct": annualized,
            "max_drawdown_pct": max_drawdown,
            "sharpe_ratio": sharpe,
            "annualized_volatility_pct": volatility * math.sqrt(252) * 100,
            "completed_trades": len(trades),
            "win_rate_pct": len(wins) / len(trades) * 100 if trades else None,
            "profit_factor": sum(wins) / -sum(losses) if losses else None,
            "average_trade_return_pct": (
                sum(t["return_pct"] for t in trades) / len(trades) if trades else None
            ),
            "average_holding_bars": (
                sum(t["holding_bars"] for t in trades) / len(trades) if trades else None
            ),
            "turnover": float(turnover / config.initial_cash),
            "realized_pnl": realized,
            "unrealized_pnl": float(unrealized),
            "cash": float(cash),
            "open_quantity": float(qty),
            "fees_paid": float(total_fees),
            "benchmark_return_pct": (curve[-1]["benchmark"] / float(config.initial_cash) - 1) * 100,
        },
        "equity_curve": curve,
        "trades": trades,
        "fills": fills,
    }
