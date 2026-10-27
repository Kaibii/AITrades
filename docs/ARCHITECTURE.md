# Architecture decisions

## One local research workflow

The repo remains named AITrades; the product is QuantPilot. The suggested module structure is
consolidated into one installable Python namespace (`packages/quantpilot`) so research code
is directly testable without service dependencies. FastAPI owns HTTP and persistence;
Next.js owns presentation and a same-origin proxy. A single backtest snapshot table stores
the complete validated configuration, canonical input-data SHA-256, engine/strategy versions,
assumptions, fills, trades, metrics and curve. A migration manages the schema. Explicit user,
ownership models arrive with auth; this is not a multi-user database design.

Redis/workers are deferred: a bounded daily backtest runs in a threadpool, without scheduling.
SciPy/statsmodels/scikit-learn and billing libraries wait for features that need them.
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
public ingress, billing, trading or customer credential store. Provider keys authorize historical
market data or AI drafting only. Environment settings provide server-side keys; frontend contains
no keys. Never deploy this local milestone to the public Internet. Live trading is reported
false and there is no order route/adapter; future live functionality needs more than a flag.

## AI drafts and version approval

`quantpilot.ai` defines a provider protocol, OpenAI implementation and restricted Pydantic
schema. The model uses Responses structured outputs, has no tools, and receives only the
user's bounded strategy prompt. Server validation accepts a single daily long-only SMA
crossover. Entry/exit, indicator, direction and timeframe are fixed enumerations; periods
and symbols are validated. No risk, execution, account, credential or arbitrary-code fields
exist. Prompt instructions request clarification for missing/unsupported conditions; human
review is required because schema validation cannot prove semantic fidelity to an idea.

Migration 0002 creates `strategy_drafts`. Generated drafts preserve prompt/explanation/rules;
edits create a fresh ID with a parent reference. Rules have no update endpoint. Approval
records a server timestamp for a particular immutable version; it authorizes only historical
backtesting. New versions start unapproved even when their parent was approved.

The draft-backtest endpoint refuses unapproved versions, obtains symbol/periods from the
stored specification and accepts only data/dates/capital/cost options. It calls the same
deterministic engine as manual backtests. Results persist approved draft ID/time and exact
specification beside the existing algorithm/data versions and input records. A raw manual
backtest remains available independently; it cannot masquerade as an approved draft run.

Provider refusal, invalid JSON/schema, HTTP errors and missing configuration never create
approval, run a backtest or substitute a canned AI answer. No external research or market
text enters the model in this milestone. Output is rendered as escaped text. Credentials
are server-side, provider errors are sanitized, `store=false` is requested, and provider
data-handling policies still apply. Prompts/explanations are stored in the local database.

Tests mock the AI boundary, including the actual SDK HTTP request/structured-output parser.
Browser tests stub generation only, while using the actual API/PostgreSQL approval and
backtest routes. An authenticated OpenAI call remains a separate credential-dependent check.

## Historical replay portfolios

Migration 0003 adds virtual accounts, simulated order/fill journals, risk events and worker
heartbeats. Accounts can only be seeded from a backtest of an explicitly approved strategy
version. The specification and normalized OHLCV hash are revalidated before copying the exact
source records. Each account freezes risk limits, source hash, commission and slippage.
Balances/quantities use Decimal and PostgreSQL Numeric(38,18); quantities round down to six
decimal places. JSON history is a display/export snapshot, not the accounting authority.

One tick evaluates the preceding completed close, validates modeled opening portfolio risk,
creates an idempotent intent, checks order risk, fills at the next adjusted open with costs,
and marks closing equity. The same crossover function is used by the backtester. Allocation
is intentionally independent of the backtest's allocation. Portfolio loss/drawdown checks
cover opens/closes, not intraday extremes. Position/notional caps apply pre-trade; market
movement can change later exposure. No margin, shorting, separate dividend ledger or liquidity
model exists. Exit orders respect notional caps and may be rejected, leaving a holding.

An exclusive PostgreSQL account-row lock serializes cursor, cash, positions and journal writes.
Unique signal/client IDs provide a second duplicate-order guard. A retry with an already
processed expected cursor is a no-op. A crash rolls back the entire local tick/batch; no network
broker side effects exist. Manual batches are bounded to 100 bars. Stop/pause requests serialize
after the current atomic tick/batch. Completed/stopped/suspended accounts cannot resume; they
retain positions without liquidation. Paused accounts may resume or advance manually.

The separate worker polls running accounts, using SKIP LOCKED to coordinate competing workers,
and rechecks status after acquiring the lock. It resumes durable cursors after restart and
suspends a session after unexpected processing errors. Heartbeats report observed activity.
The local worker processes at most 100 sessions per polling pass; this is not a production
queue or a multi-tenant service. PostgreSQL already supplies coordination here, so Redis is
deferred instead of adding an idle infrastructure dependency. The Docker worker receives
only database configuration, not AI/brokerage credential bindings.

`execution.PaperBroker` separates intents and order updates from strategy logic. Replay uses
the local adapter. The isolated Alpaca adapter has a fixed paper-only HTTPS destination and
defaults submission/cancellation off. It uses one POST, stable client IDs, lookup reconciliation,
and explicit uncertain outcomes for timeouts/5xx/malformed successful responses. It has no
application route or worker integration. Mocked tests exercise partial/terminal states and
refuse cumulative-fill regressions. Persisted external submission attempts, partial-fill
accounting, account authorization, current-session calendars/freshness, cancellation monitoring,
and restart reconciliation are still prerequisites for external Alpaca execution. Neither
replay account creation nor phase-2 approval authorizes a broker order.
