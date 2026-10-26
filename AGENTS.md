# QuantPilot development

Build one roadmap milestone at a time; keep a runnable vertical feature. Use the existing
checkout: cloud tasks are already isolated. Do not create worktrees unless requested.

## Commands (repository root unless specified)

- Install Python: `UV_CACHE_DIR=/tmp/quantpilot-uv uv sync --frozen`
- Install web: `cd apps/web && npm ci --cache /tmp/quantpilot-npm`
- Database: `docker compose up -d db`; migrate: `.venv/bin/alembic upgrade head`
- API: `.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Web: `cd apps/web && npm run dev`
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
- Phase 1 is **local, single-user research**. No auth or tenant isolation yet. Bind locally;
  do not deploy publicly until those controls are implemented. No customer brokerage accounts.
- No order submission, live trading, arbitrary Python evaluation, or AI execution paths.
  A future execution layer must enforce a server-side gate; no UI toggle can authorize trades.
- Use Decimal for portfolio quantities/cash; float only at analytics/JSON boundaries.
- Completed-bar signals fill at the *next* bar open. Never introduce same-bar closing fills.
- Preserve fixture provenance; never substitute sample data for provider failures.
- No network brokerage calls in tests. Mock market data. Never place real orders.
- Keep secrets in environment settings or ignored `.env`; never in logs, commits or browser bundles.
- Run tests and lint after changes. Document assumptions and unverified behavior honestly.
- Follow `docs/ROADMAP.md`; advanced data licensing, security, and brokerage authorization
  are explicit prerequisites for future commercial functionality.
