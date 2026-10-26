# QuantPilot roadmap

## Phase 1 — Foundation and Backtesting

- [x] Python/Next.js monorepo and local development conventions
- [x] FastAPI + PostgreSQL + Alembic; persisted immutable run snapshots
- [x] Docker Compose for database/API/web
- [x] Market-data protocol, bundled real AAPL history and Alpaca IEX adapter
- [x] SMA calculations and validated long-only crossover configuration
- [x] Event-driven next-open simulation, Decimal accounting, fees and slippage
- [x] Total/annualized return, volatility, drawdown, Sharpe, trade statistics
- [x] Dashboard, benchmark/equity/drawdown charts, completed trades, JSON export, saved runs
- [x] Unit/API tests, HTTP/PostgreSQL smoke, browser tests, CI configuration
- [ ] Validate authenticated Alpaca queries using entitled user credentials (external prerequisite)

Scope: daily, one symbol, long-only, no leverage; adjusted price-series research, fractional
units, no separate corporate-action ledger, no intraday liquidity or execution modeling.
No public deployment, multi-user support, AI, paper trading, or live orders in this milestone.

## Phase 2 — AI strategy builder

- [x] OpenAI Responses integration with strict structured outputs and provider abstraction
- [x] Natural-language daily SMA drafting, explanation and clarification UI
- [x] Restricted schema, no executable code/tools, no risk or execution fields
- [x] Immutable draft versions, editing, saved history and explicit per-version approval
- [x] Backtest exact approved rules with version/specification snapshot in saved results
- [x] Automated schema/provider/API tests and browser workflow tests using mocked AI
- [ ] Validate an authenticated OpenAI generation with a configured API key (external prerequisite)
- [ ] Expand supported indicators only with deterministic engine support and tests

Approval authorizes historical backtesting only. AI has no brokerage/account access and cannot
approve its output, alter risk settings or submit orders. The server requires a real provider
key; it never substitutes a fake AI result. This milestone remains local and single-user.

## Phase 3 — Paper trading

Alpaca-authorized paper adapter, order intents/state machines, idempotency, partial fills,
timeouts/reconciliation, scheduled workers/Redis, risk limits and emergency suspension.
Specify cancel/prevent-new-order behavior; connectivity loss must never trigger liquidation.

## Phase 4 — SaaS foundation

Established auth provider, sessions/MFA, database ownership and tenant isolation, access tests,
rate limiting, secure audit logging, Stripe signature-verified billing and entitlements.
Credential encryption/rotation, data export/deletion, security scanning and monitoring.
No shared local database access model in a public product.

## Phase 5 — Live trading readiness

Disabled-by-default server gate, authorized account integration, brokerage/legal approvals,
entitlements, operational risk controls, incident procedures and independent security review.
No live orders until every required authorization and operational condition is satisfied.

## Phase 6 — Commercial expansion

Additional brokers/assets, walk-forward and out-of-sample evaluation, corporate-action ledger,
advanced research, licensing review, team workflows and reporting, based on validated needs.
