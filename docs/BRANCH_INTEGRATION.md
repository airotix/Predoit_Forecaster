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

## Deployment follow-up required

**The existing Dockerfile still starts `preduit_app.api_server`, which is the older packaged API. It does not provide the new fresh-Joolan/catalogue/budget/automatic endpoints. Do not deploy the merged frontend with that image as if it were the current application.** Port the current endpoint/data contracts into the secured packaged runtime and verify them together before a container rollout.

The local `backend-ai` API remains a local development/pilot service. Retaining frontend login/role controls does not add the packaged backend's JWT verification or user-management endpoints to it. Do not enable shared/public access or rely on frontend controls as backend authorization. This merge does not remove the packaged backend's security checks or claim a production authentication migration.

Existing client databases, environment keys and local training outputs are not rewritten by resolving source conflicts. Keep credentials and client data out of new source commits. The existing main history may contain generated artifacts; new ignore rules do not retroactively remove already tracked files.

The upgraded engine passed calculation/workflow checks, but its measured forecast error remains unsuitable for an accuracy guarantee; see [engine verification](FORECAST_ENGINE_UPGRADE_PROGRESS.md).
