# Main / Codex integration boundary

This branch joins two previously unrelated Git histories. Both histories remain intact.

## Current application

The current fresh-Joolan application is `backend-ai/api_server.py` with `frontend/`. Follow the root [QUICK_START.md](../QUICK_START.md). It includes automatic exports, catalogue prices, business scope, customer history, corrected forecasting, seasonal allocation and financial order simulation. Its Python regression tests are `backend-ai/tests/`.

Conflicting forecast pages, season persistence and nullable financial/stock types follow this current API contract. The earlier CSV-import UI, old fixed scenario multipliers and old financial estimates are not substituted into the fresh-Joolan workflow.

## Preserved main components

- `preduit-app/` and `preduit-engine/`, including authentication, RBAC, local users, backup/backtest helpers and tests, remain unchanged by the conflict resolution.
- Frontend MSAL/AuthProvider, login/settings pages, bearer-token handling, token-aware refresh events, account/logout controls and role filtering are retained. New catalogue/scope/allocation pages require manager access. Starting/managing data exports and forecasts retains the older UI's admin/owner restriction.
- Dependency metadata retains MSAL and Vitest alongside the current forecasting UI dependencies. The Next.js configuration keeps standalone container output and separate development/production caches.
- Main's Docker, Compose, deployment documents and CI are retained. The CI additionally tests the current `backend-ai` workflow.

## Deployment (updated in migration Phase 1)

The `Dockerfile` and `docker-compose.yml` now build and run the current application, `backend-ai/api_server.py`
(see [MIGRATION_PLAN.md](MIGRATION_PLAN.md)). The older `preduit-app`/`preduit-engine` packages are no longer built or
deployed; they remain in the repository until Phase 5 removes them.

- Databases, Joolan exports and outputs live on the `preduit-backend-data` and `preduit-backend-output` volumes, mounted
  at `/app/backend-ai/data` and `/app/backend-ai/output`. Volumes from the old image (`preduit-data`, `/data/forecast.db`) are not read.
- Authentication and roles (worker, manager, admin/owner) are ported from `preduit-app` and are **off by default**. Set
  `FORECASTER_AUTH_ENABLED=true` and `FORECASTER_AUTH_SECRET` to enable them; the frontend login and role controls are then
  enforced by the backend. With authentication off the API stays local-only, so compose binds it to `127.0.0.1`.
- Not ported on purpose: `/forecast/accuracy` and `/forecast/backtest` (they evaluated the retired SARIMA engine, not the live
  forecaster), `/ingest/erp/status` and `/overrides/revert*` (no page uses them), and `/season-config` (replaced by `/seasons`).

Existing client databases, environment keys and local training outputs are not rewritten by resolving source conflicts. Keep credentials and client data out of new source commits. The existing main history may contain generated artifacts; new ignore rules do not retroactively remove already tracked files.

The upgraded engine passed calculation/workflow checks, but its measured forecast error remains unsuitable for an accuracy guarantee; see [engine verification](FORECAST_ENGINE_UPGRADE_PROGRESS.md).
