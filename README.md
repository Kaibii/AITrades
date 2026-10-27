# QuantPilot

An incremental quantitative research platform. Includes an AI-assisted daily SMA strategy
builder, deterministic backtester, Next.js dashboard, and FastAPI/PostgreSQL backend. **All performance is
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

## AI strategy creation and approval

1. Set `QUANTPILOT_AI_API_KEY` securely in the server environment or ignored root `.env`.
   An existing native `OPENAI_API_KEY` is also accepted. The default model is `gpt-4.1-mini`;
   override `QUANTPILOT_AI_MODEL` with a model supporting Responses structured outputs.
2. Restart the native API, or recreate the Docker API after changing configuration.
3. In **AI strategy builder**, describe one symbol and two daily SMA periods, for example:
   “Buy AAPL when the 20-day SMA crosses above its 50-day SMA; sell on the reverse crossover.”
4. Generate a draft. Review the entry/exit rules and structured specification. Edit the symbol,
   periods, name or description if needed; edits save as a new, unapproved version.
5. Click **Approve for backtesting**, select historical data/dates/capital/costs below, and
   click **Backtest approved version**. The server loads the exact approved rules; the
   browser cannot override their symbol or SMA periods in that request.
6. Reopen drafts and approved versions from **Saved strategy versions**. Approved parents
   stay unchanged when you save edits. Results retain the approved version and rule snapshot.

Only daily long-only SMA crossovers are supported by this milestone. Unsupported/ambiguous
requests receive a clarification instead of a runnable draft. RSI, EMA, other indicators,
additional filters, stops, multi-asset rules and intraday strategies are rejected by the
restricted output schema or require clarification. Review is necessary: schema validation
checks allowed structure, not whether a model perfectly understood your intent. AI name,
description and explanation are advisory text; only validated structured fields drive signals.

Generation calls the real OpenAI Responses API using structured JSON outputs, with no tools,
`store=false`, bounded input/output and no automatic retries. Only your strategy prompt is
sent, without portfolio data or brokerage credentials. Provider data-handling policies still
apply. Prompts, explanations and accepted specifications are stored locally with each draft;
do not put secrets in strategy descriptions. Server keys never go to the browser or model.
No arbitrary code is evaluated, and the model cannot alter simulation capital/cost controls,
approve versions, activate trading or submit orders.

Without a key, the UI reports setup is required; there is no fake AI or sample-generation
fallback. Existing drafts and the manual backtester still work. A generated draft is not
approval, and approval is for historical backtesting only. Phase 2 tests use mocked AI
responses; authenticated OpenAI calls have not been validated without credentials.

For restricted cloud environments allow `api.openai.com` and use native API processes to
inherit platform proxy/trust configuration. The Docker build helper configures build-time
networking only; external calls inside API containers need equivalent runtime proxy/trust.

## Historical paper portfolio replay

After backtesting an explicitly approved strategy version, open **Paper portfolio replay**.
Set limits for a new virtual account and click **Create virtual replay account**. Each account
starts paused with the source backtest's exact historical bars, initial cash, fees and slippage.
Approval is still for research: this creates no brokerage connection or external order.

- **Advance 100 bars** processes a bounded batch manually. Warm-up and crossover signals
  determine when orders appear. This works without a background worker.
- **Start automatic replay** arms the account. The replay worker advances one historical bar
  every five seconds. **Pause replay** freezes the historical clock.
- **Emergency stop** permanently blocks further bars/orders after any current atomic tick/batch
  finishes. Already-filled orders and positions remain; there is no liquidation. Replay fills
  are immediate, so there are no pending external orders to cancel.
- Suspensions/completion preserve holdings too. Create a new account to change immutable limits
  or restart a stopped/suspended replay. Saved accounts show cash, shares, equity, fills and events.

Docker Compose starts the replay worker automatically. For native development, run a third terminal:

```bash
.venv/bin/python -m app.paper_worker
```

Use `--once` to process one tick and exit; `--interval 1` changes the replay interval for local
testing. The worker resumes persisted running accounts after restart. Stop this project's
`api web worker` containers when switching to native services. Worker heartbeat reports recent
activity; absent workers leave accounts armed without advancing them.

Allocation, maximum position/notional, buying power and one-order-per-bar checks run before
fills. Daily-loss and drawdown limits check modeled opening and closing equity; breaches
suspend further processing without automatically selling. Exit orders also obey the notional
cap and can be rejected. Risk limits are not intrabar guarantees. All balances use Decimal
accounting stored at 18 decimal places. Replay allocation can differ from the original
backtest, so performance can differ. Saved adjusted-price assumptions still apply.

This feature replays **historical** bars; it does not use current quotes or submit Alpaca paper
orders. An isolated, default-disabled Alpaca paper adapter is present as a tested foundation.
It is not wired into the application. Full paper brokerage execution requires the remaining
authorization, submission-journal and reconciliation work in the roadmap. There is no live adapter.

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
- No auth, tenant isolation, billing or external brokerage execution yet. Do not expose
  this local application publicly. Live order submission has no implementation or API route.

See [architecture and dataset provenance](docs/ARCHITECTURE.md),
[development conventions](AGENTS.md), and [roadmap](docs/ROADMAP.md).
Next milestone: dedicated Alpaca paper-account authorization, durable external-order intents,
current-data checks and restart reconciliation before enabling scheduled paper brokerage execution.
