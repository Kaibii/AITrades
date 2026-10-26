# QuantPilot

An incremental quantitative research platform. Phase 1 provides a working daily SMA crossover
backtester, a Next.js dashboard, and a FastAPI/PostgreSQL backend. **All performance is
hypothetical. No real trades are executed.** This milestone is for local, single-user research.

## Launch with Docker

Requires Docker Engine and Docker Compose v2. From the repository root:

```bash
cp .env.example .env   # only if .env does not already exist
docker compose up --build -d
docker compose ps
docker compose logs api web
```

Open the web app on your machine at port 3000. The API runs on port 8000 with interactive
API documentation at `/docs`; PostgreSQL is on port 5432. All host bindings use loopback.
Compose waits for PostgreSQL, applies Alembic migrations, checks the API and starts the web.
The database persists in a named volume. `docker compose down` stops services and keeps data;
do not add `-v` unless you intend to delete the local database.

In a cloud machine behind an injected HTTPS proxy, use
`bash infrastructure/scripts/build.sh` followed by `docker compose up -d --no-build --wait`.
The helper forwards standard proxy build arguments, resolves proxy hostnames for build
containers, and mounts the existing trusted CA bundle as an optional build secret. It never
disables TLS checks or embeds proxy values in image layers. It requires Python 3.12+.

In the dashboard, retain **Bundled AAPL · 2015–2017**, select fast/slow SMA periods and costs,
then **Run backtest**. Inspect hypothetical equity, drawdown, metrics and completed trades.
The run is saved to PostgreSQL; reopen it with Saved runs or download its JSON snapshot.
No API key is needed for the bundled historical workflow. Other symbols require Alpaca.

## Native development

Requires Python 3.12+, uv, Node.js 24 LTS and Docker Compose. Use the existing checkout.

```bash
UV_CACHE_DIR=/tmp/quantpilot-uv uv sync --frozen
cd apps/web
npm ci --cache /tmp/quantpilot-npm
cd ../..
docker compose up -d db
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd apps/web
npm run dev
```

For an optimized web server, `npm run build && npm start` in `apps/web`. The native backend
reads the root `.env`. Next.js proxies browser API calls to `API_INTERNAL_URL` (defaults to
the local API on port 8000); for a custom native destination export it in the web process.
Docker sets the internal URL automatically. No credentials are passed to the browser.
The default database credentials in `.env.example` are local development values only.

## Interactive historical queries with Alpaca

Set `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` securely on the server or in ignored `.env`.
They must belong to an entitled Alpaca account; no customer passwords or OAuth are used in
this milestone. In Docker, recreate the API after editing keys:

```bash
docker compose up -d --force-recreate api
```

Choose **Alpaca · IEX daily history**, enter SPY or another supported U.S. equity/ETF and a
completed historical date range. The adapter uses HTTPS `data.alpaca.markets`, daily bars,
IEX feed and `adjustment=all`. Network access and provider entitlement are required. Current
day/incomplete daily bars are rejected. A provider error is shown explicitly; there is no
silent sample fallback. Live authenticated queries require your credentials and have not
been validated without them. Free data does not imply consolidated coverage or commercial
redistribution rights. In a restricted cloud environment, allow `data.alpaca.markets`.

In this cloud machine, use the native API process for external Alpaca queries so it inherits
the platform's proxy and trusted certificates. The Docker build helper configures build-time
networking only; container runtime external access requires equivalent proxy/trust settings.
The bundled historical workflow needs no external runtime connection.

## Verification

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python infrastructure/scripts/smoke.py  # API and DB running
cd apps/web
npm run lint
npm run typecheck
npm run build
# API/DB and web must be running for browser tests:
npx playwright install chromium
npm run test:e2e
```

For a system browser use `CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e`. Unit/API tests
use fixtures, HTTP mocks and an isolated SQLite database; the smoke test exercises the actual
running API and PostgreSQL. Browser tests exercise configuration, results, export, saved runs,
validation and mobile layout. CI runs these against PostgreSQL; it never submits orders.

## Scope and assumptions

- Daily, single-symbol, long-only SMA crossovers. No pre-range warm-up; require at least
  `slow + 2` daily observations. First eligible signal uses two fully warmed moving averages.
- Completed-bar signals fill at the next available bar's open, with adverse slippage and
  notional fees. Fractional adjusted shares; no leverage, interest, taxes or liquidity model.
- Open holdings are marked at the final close; no forced liquidation. Completed-trade
  metrics exclude open holdings; unrealized P/L and cash are shown separately.
- Adjusted-series research: dividends are implicit in adjusted prices, not a separate cash
  ledger. Benchmark is cost-free buy-and-hold from the first close. See in-app assumptions.
- Every run persists configuration, data hash, versions, assumptions, fills, curve and metrics.
  Null ratios mean undefined, not zero. No claim of profitability or future performance.
- No auth, tenant isolation, AI, billing, workers or brokerage execution yet. Do not expose
  this local application publicly. Live order submission has no implementation or API route.

See [architecture and dataset provenance](docs/ARCHITECTURE.md),
[development conventions](AGENTS.md), and [roadmap](docs/ROADMAP.md).
Next milestone: validated, versioned AI-assisted strategy drafts, with explicit approval and
deterministic validation before any future activation.
