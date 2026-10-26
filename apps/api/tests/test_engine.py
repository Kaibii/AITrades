from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from quantpilot.backtesting import BacktestConfig, run_backtest
from quantpilot.indicators import sma
from quantpilot.market_data import Bar, Dataset, SampleProvider
from quantpilot.strategies import crossovers


def dataset(closes=(10, 9, 8, 9, 11, 12, 9, 7), opens=None):
    opens = opens or list(closes)
    return Dataset(
        [
            Bar(
                date=date(2020, 1, 1) + timedelta(days=i),
                open=opens[i],
                close=close,
                high=max(opens[i], close) + 1,
                low=min(opens[i], close) - 1,
            )
            for i, close in enumerate(closes)
        ],
        "hand-calculated fixture",
        "none",
        "synthetic unit-test data",
    )


def config(**kwargs):
    return BacktestConfig(
        start=date(2020, 1, 1),
        end=date(2020, 2, 1),
        fast=2,
        slow=3,
        initial_cash=1000,
        allocation=1,
        commission_bps=0,
        slippage_bps=0,
        **kwargs,
    )


def test_sma_trailing_and_warmup():
    assert sma(list(map(Decimal, [1, 2, 3, 7])), 3) == [None, None, Decimal(2), Decimal(4)]
    with pytest.raises(ValueError):
        sma([], 0)


def test_signals_only_after_full_warmup():
    assert crossovers(list(map(Decimal, [10, 9, 8, 9, 11, 12, 9, 7])), 2, 3) == [
        None,
        None,
        None,
        None,
        "buy",
        None,
        "sell",
        None,
    ]


def test_next_open_and_exact_cash_accounting():
    data = dataset(opens=[10, 9, 8, 9, 11, 13, 9, 6])
    result = run_backtest(config(), data)
    buy, sell = result["fills"]
    assert buy["date"] == "2020-01-06" and buy["price"] == 13
    assert sell["date"] == "2020-01-08" and sell["price"] == 6
    assert result["metrics"]["final_equity"] == pytest.approx(461.538468)
    assert result["metrics"]["realized_pnl"] == pytest.approx(-538.461532)
    assert result["metrics"]["unrealized_pnl"] == 0
    assert result["metrics"]["open_quantity"] == 0
    assert result["metrics"]["win_rate_pct"] == 0
    assert result["trades"][0]["holding_bars"] == 2
    assert all(p["cash"] >= 0 for p in result["equity_curve"])


def test_costs_are_applied_on_both_sides():
    cfg = config().model_copy(update={"commission_bps": Decimal(100), "slippage_bps": Decimal(100)})
    result = run_backtest(cfg, dataset(opens=[10, 9, 8, 9, 11, 13, 9, 6]))
    buy, sell = result["fills"]
    assert buy["price"] == pytest.approx(13.13)
    assert sell["price"] == pytest.approx(5.94)
    assert buy["fee"] == pytest.approx(buy["quantity"] * 13.13 * 0.01)
    assert sell["fee"] == pytest.approx(buy["quantity"] * 5.94 * 0.01)
    assert result["metrics"]["fees_paid"] == pytest.approx(buy["fee"] + sell["fee"])
    expected = 1000 - buy["quantity"] * 13.13 - buy["fee"] + sell["quantity"] * 5.94 - sell["fee"]
    assert result["metrics"]["final_equity"] == pytest.approx(expected)


def test_future_bars_cannot_change_past_results_and_open_position_not_forced_closed():
    short = dataset([10, 9, 8, 9, 11, 12])
    long = dataset([10, 9, 8, 9, 11, 12, 9, 7])
    a, b = run_backtest(config(), short), run_backtest(config(), long)
    assert a["equity_curve"] == b["equity_curve"][:6]
    assert a["metrics"]["completed_trades"] == 0
    assert a["metrics"]["open_quantity"] > 0
    assert a["metrics"]["realized_pnl"] == 0
    assert a["metrics"]["final_equity"] == pytest.approx(1000 + a["metrics"]["unrealized_pnl"])


def test_flat_prices_have_no_trades_and_undefined_sharpe():
    result = run_backtest(config(), dataset([10] * 8))
    assert result["metrics"]["total_return_pct"] == 0
    assert result["metrics"]["annualized_return_pct"] == 0
    assert result["metrics"]["max_drawdown_pct"] == 0
    assert result["metrics"]["sharpe_ratio"] is None
    assert result["metrics"]["win_rate_pct"] is None
    assert not result["fills"]


def test_last_bar_signal_cannot_fill_without_next_bar():
    result = run_backtest(config(), dataset([10, 9, 8, 8, 9]))
    assert not result["fills"]


@pytest.mark.parametrize(
    "update",
    [
        {"fast": 3, "slow": 3},
        {"allocation": 1.1},
        {"slippage_bps": -1},
        {"initial_cash": "NaN"},
        {"fast": 2.5},
        {"symbol": "../SPY"},
        {"end": "2100-01-01"},
        {"start": "2017-02-17", "end": "2015-02-17"},
        {"execute_live": True},
    ],
)
def test_invalid_configuration_rejected(update):
    with pytest.raises(ValidationError):
        BacktestConfig(**{**BacktestConfig().model_dump(), **update})


def test_invalid_data_rejected():
    data = dataset()
    with pytest.raises(ValueError, match="increasing"):
        run_backtest(config(), Dataset(list(reversed(data.bars)), "", "", ""))
    with pytest.raises(ValueError, match="at least"):
        run_backtest(config(), Dataset(data.bars[:3], "", "", ""))
    with pytest.raises(ValidationError):
        Bar(date="2020-01-01", open=10, high=8, low=5, close=9)


def test_historical_sample_reproducible_and_reconciles():
    cfg = BacktestConfig()
    sample = SampleProvider().history(cfg.symbol, cfg.start, cfg.end)
    result = run_backtest(cfg, sample)
    assert len(sample.bars) == 506
    assert result == run_backtest(cfg, sample)
    restored = Dataset(
        [Bar(**row) for row in result["data"]["records"]],
        sample.source,
        sample.adjustment,
        sample.license_note,
    )
    assert result == run_backtest(cfg, restored)
    m = result["metrics"]
    assert m["completed_trades"] > 0
    assert m["final_equity"] == pytest.approx(
        m["initial_equity"] + m["realized_pnl"] + m["unrealized_pnl"]
    )
    assert m["final_equity"] == pytest.approx(
        m["cash"] + m["open_quantity"] * float(sample.bars[-1].close)
    )


def test_drawdown_from_running_peak_and_total_return():
    result = run_backtest(config(), dataset(opens=[10, 9, 8, 9, 11, 13, 9, 6]))
    m = result["metrics"]
    assert m["total_return_pct"] == pytest.approx(-53.8461532)
    assert m["max_drawdown_pct"] == pytest.approx(-53.8461532)
