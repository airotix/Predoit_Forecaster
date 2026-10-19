# Preduit — Client Handover Completion Plan

**Owner:** Zaki · **Created:** 2026-07-11 · **Status:** Phase 1 in progress

This is the master plan to take Preduit from its current state to a production-ready,
client-handover-ready product. Every item below is grounded in the actual codebase.
Work is organised into phases so nothing is left half-done. Check items off as they land.

---

## Role model (agreed)

Four roles, ranked by privilege:

| Role | Rank | Purpose | Can do |
|------|------|---------|--------|
| **Owner** | 3 (top) | Business owner | Everything (same access as Admin) |
| **Admin** | 3 (top) | System / IT admin | Everything: user mgmt, config, ingestion, pipeline runs |
| **Manager** | 2 | Merchandiser / buyer lead | View + overrides, locks, season config, budget, approvals |
| **Worker** | 1 (lowest) | Staff | **View only** — dashboards, products, projections. No writes. |

Owner and Admin share the top privilege level (level 3). Worker is strictly read-only:
it replaces the current `user` role and loses nothing it had, but is explicitly barred
from override/lock/config/ingestion endpoints (those already require `manager`+).

Azure Entra app roles map as: `Preduit.Owner→owner`, `Preduit.Admin→admin`,
`Preduit.Manager→manager`, `Preduit.Worker→worker` (legacy `Preduit.User→worker` kept
for migration).

---

## Phase 1 — Roles + Auth hardening (SECURITY BLOCKER)

Goal: replace the 3-role model with the 4-role model everywhere, and make the app
secure-by-default so it can never ship silently open.

**Backend**
- [ ] `rbac.py`: `ROLE_LEVEL = {worker:1, manager:2, admin:3, owner:3}`; `ENTRA_ROLE_MAP`
  adds Owner/Worker (+ legacy User→worker); `highest_role` default → `worker`.
- [ ] `auth.py`: `_dev_user()` accepts the four roles; docstring updated.
- [ ] `api_server.py`: every `require_role("user")` → `require_role("worker")` (9 call sites).
- [ ] `test_auth.py`: update to assert the 4-role hierarchy (owner==admin top, worker lowest).
- [ ] Production safety guard: on startup, if `AUTH_ENABLED=false` **and** the app is not
  in an explicit dev context, log a loud `WARNING` that the API is running unauthenticated.

**Frontend**
- [ ] `msalConfig.ts`: `PreduitRole = 'owner'|'admin'|'manager'|'worker'`; role map, rank,
  `routeMinRole`, `roleMeetsRequired` all updated; default fallback → `worker`.
- [ ] `AuthProvider.tsx`: default role state → `worker`.
- [ ] `middleware.ts`: `roleRank`/`minRoleForPath` updated for 4 roles; cookie default → `worker`.
- [ ] `Sidebar.tsx` / `TopNav.tsx`: `minRole` values keep `manager`; `user`→`worker`.

**Config / secrets**
- [ ] `.env.example`: add the missing auth block — `FORECASTER_AUTH_ENABLED`,
  `FORECASTER_AUTH_DEV_BYPASS`, `FORECASTER_AUTH_DEV_ROLE`, `FORECASTER_AZURE_TENANT_ID`,
  `FORECASTER_AZURE_CLIENT_ID`, `FORECASTER_AZURE_API_AUDIENCE`, `FORECASTER_BACKTEST_HOLDOUT_MONTHS`.
- [ ] Add `frontend/.env.local.example` documenting `NEXT_PUBLIC_API_URL`,
  `NEXT_PUBLIC_AUTH_ENABLED`, `NEXT_PUBLIC_AZURE_*`, `NEXT_PUBLIC_AUTH_DEV_ROLE`.

**Exit criteria:** all role references consistent; dev bypass still works locally; a
production `.env` (auth enabled) fully locks the API; no `user` role strings remain.

**Login / signup flow (DONE)**
- [x] Backend `users` table + CRUD (`database.py`); `local_auth.py` (PBKDF2 hashing +
  HS256 session JWTs, no new deps); `/api/auth/config|signup|login|me` endpoints;
  `get_current_user` now accepts both local and Azure tokens. First account created
  becomes `owner`; subsequent accounts default to `worker`.
- [x] Frontend `AuthProvider` reworked to support local password sessions, Azure SSO,
  and dev mode together; new `lib/api/auth.ts`; professional two-panel `login` page
  with Sign-in / Create-account tabs, validation, password toggle, SSO button, and a
  dev-mode banner.
- [x] Settings page (`/settings`) with a Profile tab and a role-gated User Management
  tab (admin/owner list users + change roles); navbar user menu simplified to Settings +
  Log out. Backend: `GET /api/auth/users`, `PUT /api/auth/users/role` (self-demotion blocked).
- [ ] Follow-ups: password reset flow; optional email verification; deactivate/remove
  accounts. (Tracked for a later phase.)

---

## Phase 2 — Financial model (BLOCKER: placeholder data)

The 50%-of-price cost was fake and drove every margin/budget/cost figure. Per client
decision: budget is entered in Season Setup (base case) and conservative/optimistic derive
from a configurable ± band; cost stays a configurable ratio (default 50%), labelled as an
estimate, until real cost data is available.

**Budget from Season Setup (DONE)**
- [x] `season_config` gains `budget_band_pct` (default 15) and `cost_ratio` (default 0.5),
  with a safe column migration for existing DBs; CRUD + create/update endpoints updated.
- [x] Season Setup page: "Seasonal Buying Budget" (base) + new "Budget Flexibility Band (±%)"
  with a live conservative/base/optimistic preview + "Estimated Cost Ratio %".
- [x] Backend helpers `_scenario_budget` / `_season_cost_ratio` derive per-scenario budgets
  (conservative = base−band%, optimistic = base+band%) and apply the cost ratio at serving
  time in `/api/dashboard`, `/api/budget`, `/api/validation`. `BUDGET_MULTIPLIER` is now only
  a fallback when no budget is set.
- [x] Cost & margin recomputed from revenue × cost ratio (consistent, per-season); budget
  page badges cost/margin as "est." and shows the active scenario.

**Cost model — remaining**
- [ ] Per-item cost on the Product KPIs page and articles list still read the pipeline's
  stored cost columns (default ratio); align them with the season cost ratio or re-run the
  pipeline when the ratio changes.
- [ ] When real per-product/supplier cost data is available: ingest it in `m1` and prefer it
  over the ratio in `m3`/`m7`; keep the ratio as fallback.
- [ ] Wire or remove the dead knobs `TARGET_MARGIN_RATE` and `SEASONAL_BUDGET`.

**Exit criteria:** budget is client-entered with derived scenarios (DONE); every estimated
figure is labelled (DONE for the main financial views); real cost flows end-to-end when supplied.

---

## Phase 3 — Data ingestion (BLOCKER: mock ERP)

- [ ] Decide with the client: real ERP connector vs. CSV/XLSX upload only.
- [ ] If ERP: implement a real client in `ingestion.py` replacing `load_mock_erp_dataframe()`
  (`ingestion.py:376-382`) and back `POST /api/ingest/erp` with it.
- [ ] If not: hide/disable the "ERP sync" button in the Setup page and label the flow
  "manual import" so nothing pretends to be live.
- [ ] Document the exact CSV column contract (see Phase 6 data-spec doc) and validate
  uploads against it with clear error messages.

**Exit criteria:** the ingestion path the client sees does exactly what it claims.

---

## Phase 4 — Deployment & configuration (DONE)

- [x] Backend `Dockerfile` (Python 3.12, installs engine+app, uvicorn, `/health` healthcheck,
  data on a `/data` volume) + root `.dockerignore`.
- [x] Frontend containerised: `output: 'standalone'` in `next.config.mjs`, multi-stage
  `frontend/Dockerfile` (non-root runtime), `frontend/.dockerignore`; package renamed from
  `temp_app` → `preduit-frontend`.
- [x] `docker-compose.yml` — full stack (backend + frontend + `preduit-data` volume) with one
  `docker compose up --build`.
- [x] `.env.production.example` — prod-safe defaults (`API_RELOAD=false`, real CORS, auth on).
- [x] Data-path decoupling: containers set `FORECASTER_DB_PATH`/`OUTPUT_DIR` to the volume, so
  they never depend on the legacy `backend-ai/` layout.
- [x] `docs/DEPLOYMENT.md` — local compose **and** Azure Container Apps runbook, secrets
  handling, health/upgrade/rollback.

**Remaining:** build the images once on a Docker host to confirm they compile (couldn't run
Docker in this environment), and provision the Azure Files share + Container Apps per the doc.

**Exit criteria:** a fresh environment can be stood up from the committed Dockerfiles + env
template with one documented sequence — met (pending a real build run).

---

## Phase 5 — Data / DB durability (DONE)

- [x] `preduit_engine/backup.py` — online-backup snapshots with retention, integrity check,
  and restore (copies current DB aside first). CLI (`python -m preduit_engine.backup …`) +
  admin API (`POST/GET /api/admin/db/backup(s)`). Cron/Job scheduling documented.
- [x] Schema versioning: `SCHEMA_VERSION` + `schema_meta` table recorded on startup; safe
  `ADD COLUMN`-if-missing migrations; `GET /api/admin/db/health` reports version + integrity.
- [x] `scripts/make_sample_data.py` — deterministic, anonymised 49-column sample history so a
  fresh install runs without the real file (generated, not committed raw).
- [x] `docs/DATA_DURABILITY.md` — backup/restore, migrations, seed data, and the SQLite
  single-writer limit + Postgres migration trigger.

---

## Phase 6 — Testing (DONE, with follow-ups)

- [x] `pytest` + `pytest-asyncio` added as dev extras to both `pyproject.toml` files, with
  `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) so the async auth tests run.
- [x] Engine unit tests: `test_database.py` (users/season band+cost/schema/migration),
  `test_backup.py` (create/list/prune/restore), `test_erp_joolan.py` (guards + payload parsing).
- [x] App tests: `test_local_auth.py` (hashing + JWT roundtrip), `test_api.py` — FastAPI
  `TestClient` for `/health`, `/api/auth/config`, signup→login→duplicate, plus the Phase 2
  financial helpers. Skips gracefully if the ML stack isn't installed.
- [x] Frontend: Vitest set up (`vitest.config.ts`, `npm test`) with `msalConfig.test.ts`
  covering the 4-role hierarchy, Entra mapping (incl. legacy), and route gating.
- [x] CI: `.github/workflows/ci.yml` runs engine + app pytest and frontend lint/test/build.

**Follow-ups:** deeper API tests for `/api/recommendations` GET/PUT/lock and `/api/budget`
against a seeded DB; a full m1→m8 pipeline smoke test on the sample CSV; React component
tests (would add `@testing-library/react` + jsdom).

---

## Performance hardening (DONE)

Fixed slow/hanging Budget, Customers, Projection, and Recommendations pages. Root cause was
**not** missing indexes (those exist) but unbounded payloads, N+1 query loops, one O(n²)
computation, and unmemoised/uncapped rendering.

- [x] `/api/customers`: replaced 3-queries-per-client (≈3N) with 3 set-based aggregate
  queries; the O(V×N) similarity match is now bucketed by region.
- [x] `/api/recommendations`: replaced 2-queries-per-row with 2 bulk fetches (sizes +
  overrides) joined in memory.
- [x] `/api/customer-detail`: removed the per-row `designation` lookup (bulk map).
- [x] `/api/budget`: cached the full-table aggregates by scenario + pipeline-run + season
  signature (invalidates automatically on re-run / config change).
- [x] Frontend: memoised derived data (filters, region/typology buckets, reductions) on
  Customers / Recommendations / Projection; Projection no longer refetches on every
  keystroke (client-side filtering); long lists render a capped slice (150) with a
  "refine your search" hint.
- [ ] Follow-up: true list virtualization (`@tanstack/react-virtual`) to render the full
  list smoothly instead of a cap; optional server-side pagination if datasets grow very large.

## Phase 7 — Documentation for the client

- [ ] **Client onboarding checklist** (the Azure doc explicitly defers to one that doesn't
  exist): Entra app registration, app roles, user assignment, env vars, first pipeline run.
- [ ] **Data import spec**: the required CSV columns (currently only implicit in
  `client_config.py:64-110`), formats, encodings, and how `true_demand` is derived.
- [ ] **Operational runbook**: start/stop, backup/restore, "pipeline failed" recovery,
  log locations, how to re-run a forecast.
- [ ] Archive or rewrite stale docs: `docs/DB-plan.md` (old monolith, port 8000) and
  `backend-ai/README.md` (dead TypeScript stub).
- [ ] Update `PROJECT_OVERVIEW.md` and `QUICK_START.md` to reflect the 4-role model.

---

## Phase 8 — Cleanup & polish

- [ ] Rename frontend package from `temp_app` (`frontend/package.json:2`).
- [ ] Delete dead `frontend/src/lib/mockData.ts` (imported nowhere).
- [ ] Resolve the two duplicated API layers (`lib/api.ts` vs `lib/api/*.ts`) — keep one.
- [ ] Remove legacy `backend-ai/src/` Express stub + its committed `node_modules/`,
  stale `__pycache__/`, and `catboost_info/`; relocate `backend-ai/data/` if kept.
- [ ] Resolve the two config-duplication TODOs: `api_server.py:134` (SIZE_ORDER) and
  `m8_output.py:256` (hardcoded output filename → use `OUTPUT_MONTHLY_DETAIL_FILE`).
- [ ] De-duplicate `determine_size_order` (copied in `m5_catboost.py` and `m6_size_curves.py`).
- [ ] Replace deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` (Py3.12+ warnings).
- [ ] Verify customer typology / "AI-matched" fields are backed by real data, not UI copy.

---

## Suggested sequencing

1. **Phase 1** (roles + auth) — security blocker, done first. ← *in progress*
2. **Phase 2 & 3** (financials + ingestion) — the two data-integrity blockers, in parallel.
3. **Phase 4 & 5** (deploy + durability).
4. **Phase 6** (testing) — ideally alongside 2–5, not after.
5. **Phase 7 & 8** (docs + cleanup) — finish before sign-off.

Each phase has explicit exit criteria; a phase is "done" only when all its boxes are
ticked and its tests pass.
