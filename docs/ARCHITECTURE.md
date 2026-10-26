# Phase 1 decisions

## One local research workflow

The repo remains named AITrades; the product is QuantPilot. The suggested module structure is
consolidated into one installable Python namespace (`packages/quantpilot`) so research code
is directly testable without service dependencies. FastAPI owns HTTP and persistence;
Next.js owns presentation and a same-origin proxy. A single backtest snapshot table stores
the complete validated configuration, canonical input-data SHA-256, engine/strategy versions,
assumptions, fills, trades, metrics and curve. A migration manages the schema. Explicit user,
strategy and ownership models arrive with auth; this is not a multi-user database design.

Redis/workers are deferred: a bounded daily backtest runs in a threadpool, without scheduling.
SciPy/statsmodels/scikit-learn and AI/billing libraries wait for features that need them.
No empty execution/brokerage/risk modules imply functionality that does not exist.

## Accounting and timing

Each bar processes the previous completed close's crossover at today's open, applies adverse
slippage, charges notional commission, then marks equity at today's close. Decimal accounting
and rounded-down six-decimal quantities prevent spending beyond cash. A crossing requires
two fully warmed averages; a first bullish warmed value is not itself a crossover. No pre-range
warm-up means changing start dates can change signals. Last-bar signals have no next-bar fill.
Final holdings remain open; realized profit includes round-trip fees, unrealized profit is
marked value minus original cost, and hypothetical exit costs are not accrued.

CAGR uses elapsed calendar days / 365.25. Sharpe uses sample close-to-close return volatility,
252 sessions and 0 risk-free rate. Undefined ratios are null, never infinity. Drawdown uses
daily closing equity (not intraday troughs). Trade statistics use closed round trips only;
turnover sums both buy and sell notionals / initial cash. The benchmark buys at the first
adjusted close without costs, so it is an indicative comparison with different timing.

## Historical data

`market_data/aapl.csv` is a verbatim public Plotly dataset:
https://github.com/plotly/datasets/blob/master/finance-charts-apple.csv

Retrieved 2026-10-26; 506 daily rows, 2015-02-17 through 2017-02-16. Only OHLC,
adjusted close and volume are used. Supplied precomputed indicator columns are ignored.
Raw file SHA-256 is recorded in `docs/DATA_SHA256.txt`. Upstream public availability does
not certify accuracy or commercial redistribution rights. Review licensing before distribution.

All sample OHLC prices are scaled by adjusted-close/raw-close for each day. This is an
adjusted research series in hypothetical share units; the model is not a raw-price execution
or separate dividend/split ledger. Volume remains the provider's volume. The sample predates
later AAPL splits, so values are not comparable to current unadjusted quotes. Alpaca requests
`adjustment=all`, `feed=iex`, daily bars, with bounded pagination and timeout. IEX coverage is
not the full consolidated market. No real-time or commercial rights are assumed. Errors never
fall back to sample data. Hashes identify exact normalized input snapshots. Each saved/exported run includes the
normalized OHLCV records used in simulation, allowing reruns without re-querying a changing
provider. Persisting licensed provider records is subject to the account's storage rights.

## Deployment boundary

Compose exposes ports only on loopback. There is no registration, tenant authorization,
public ingress, billing, trading or customer credential store. API keys authorize historical
market-data requests only. Environment settings provide server-side keys; frontend contains
no keys. Never deploy this local milestone to the public Internet. Live trading is reported
false and there is no order route/adapter; future live functionality needs more than a flag.
