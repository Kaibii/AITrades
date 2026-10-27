# QuantPilot development

Build one roadmap milestone at a time; keep a runnable vertical feature. Use the existing
checkout: cloud tasks are already isolated. Do not create worktrees unless requested.

## Commands (repository root unless specified)

- Install Python: `UV_CACHE_DIR=/tmp/quantpilot-uv uv sync --frozen`
- Install web: `cd apps/web && npm ci --cache /tmp/quantpilot-npm`
- Database: `docker compose up -d db`; migrate: `.venv/bin/alembic upgrade head`
- API: `.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Web: `cd apps/web && npm run dev`
- Historical replay worker: `.venv/bin/python -m app.paper_worker` (5-second ticks).
  `--once` processes one tick and exits. Native development: stop only this project's
  `api web worker` containers before starting native processes. PostgreSQL stays running.
- Backend tests/lint: `.venv/bin/pytest -q`; `.venv/bin/ruff check .`; `.venv/bin/ruff format --check .`
- Web checks: `cd apps/web && npm run lint && npm run typecheck && npm run build`
- HTTP/PostgreSQL smoke (running API): `.venv/bin/python infrastructure/scripts/smoke.py`
- Browser tests (running API, DB, web): `cd apps/web && npm run test:e2e`
  Set `CHROMIUM_PATH=/usr/bin/chromium` to use an installed browser or run
  `npx playwright install chromium` first. Tests use only sample historical data.

## Architecture and safety

- `packages/quantpilot`: deterministic market-data, indicators, strategies, backtesting.
- `apps/api`: FastAPI, configuration, SQLAlchemy persistence; Alembic at root.
- `apps/web`: Next.js App Router, typed React, Tailwind, shadcn-style Button, Recharts,
  TanStack Query. Browser calls same-origin Next.js API proxy; secrets remain server-side.
- The current app is **local, single-user research**. No auth or tenant isolation yet. Bind locally;
  do not deploy publicly until those controls are implemented. No customer brokerage accounts.
- No network brokerage order routes, live trading, arbitrary Python evaluation, or AI execution.
  Paper accounts are historical replay only. `app.paper_worker` must never instantiate
  a network broker; it coordinates through PostgreSQL row locks and persisted cursors.
  `execution.alpaca` is a default-disabled adapter foundation tested with HTTP mocks only.
  Do not wire it into jobs/routes until journal-before-submit, uncertain-outcome recovery,
  account authorization, current-data checks and explicit paper activation are implemented.
  Keep replay clearly labeled; no claims of current quotes or Alpaca paper fills.
  AI only drafts the restricted schema in `quantpilot.ai`; explicit approval is per immutable
  version, required server-side for draft backtesting. Edits create new unapproved versions.
  Do not add a fake AI fallback or send market/account/credential data to the model.
  A future execution layer must enforce a server-side gate; no UI toggle can authorize trades.
- Use Decimal for portfolio quantities/cash; float only at analytics/JSON boundaries.
- Completed-bar signals fill at the *next* bar open. Never introduce same-bar closing fills.
- Preserve fixture provenance; never substitute sample data for provider failures.
- No network brokerage calls in tests. Mock market data. Never place real orders.
- Keep secrets in environment settings or ignored `.env`; never in logs, commits or browser bundles.
- Run tests and lint after changes. Document assumptions and unverified behavior honestly.
- Follow `docs/ROADMAP.md`; advanced data licensing, security, and brokerage authorization
  are explicit prerequisites for future commercial functionality.
