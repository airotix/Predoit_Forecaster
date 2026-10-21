# Architecture migration plan

Status: **proposed, no code changed yet.** Written 2026-10-21.

The goal is three clearly separated parts, **without changing what the running
application does today**:

| Part | Responsibility | Must not |
|---|---|---|
| `frontend/` | Next.js UI | Contain business rules; call anything except the HTTP API |
| `preduit-engine/` | Pure forecasting library: dataframes in, forecasts out | Read env, touch the database, know paths, import the backend |
| `backend/` (today `backend-ai/`) | FastAPI routers, services, repositories, auth, Joolan integration, persistence | Contain forecasting math |

`preduit-app/` is removed at the end. Its auth/RBAC is ported, not lost.

---

## 1. Where we are (validated against the code, 2026-10-21)

- **Two backends.** `backend-ai/` is the live application (README, `docs/BRANCH_INTEGRATION.md`). `preduit-app/` is
  an older API that `Dockerfile`, `docker-compose.yml` and CI build and ship.
- **The deployed image cannot serve the frontend.** The frontend calls `/purchase-orders`, `/catalogue`, `/budget/draft`,
  `/seasons`, `/joolan/fresh`, `/seasonal-allocation`, `/planning/inputs`, `/orders`, `/forecast-source`, automatic
  forecast routes. None exist in `preduit-app`.
- **The engine is not the live engine.** The forecast that runs is `backend-ai/forecasting.py` (seasonal baselines +
  CatBoost). `preduit-engine` holds the older SARIMA pipeline (`m4`/`m5`/`m6`), which the live path does not use.
  `m1`, `m2`, `m3`, `m7`, `database`, `ingestion` have diverged between the two copies; **`backend-ai` is the truth.**
- **Circular dependency.** `preduit_engine/config.py` imports `preduit_app.client_config`, which imports
  `preduit_engine._env`. The engine copies ~20 app settings onto itself.
- **No layering.** Both `api_server.py` files hold routes, business logic and raw SQL (~48 SQL statements each).
- **Auth gap.** Only `preduit-app` has JWT/RBAC/local users. `backend-ai` has a shared-secret token and no roles, while
  the frontend shows login and role controls.
- **Frontend.** `lib/api.ts` and `lib/api/` coexist; legacy and v2 contracts side by side; `mockData.ts` ships in the
  source tree; no generated API client.

## 2. Lessons from the earlier port

Source: `github.com/airotix/Preduit-forecaster`, branch `integrate/codex-into-engine` (commit `9502fad`, merged as
`4c9ea4e`, 2026-10-16). It moved `backend-ai` into `preduit-engine` and mounted the Joolan routes in `preduit-app`.
The reported symptom was that some values did not show. Compared against its pre-port source (`17e3c87`):

**What it did right (keep):**
- All routes survived; the frontend was unchanged; no schema columns were lost.
- Workers were launched with `python -m <package>.<worker>`, not a script path.
- Package-relative imports; one-off `check_*`/`verify_*` scripts moved to `tools/`; caches and `node_modules` removed
  from git; added `users`, `season_config`, `schema_meta` and backtest tables; backup support.

**What most likely caused missing values (avoid):**
1. **Default serving database changed.** Before: `database.py` read `data/joolan_live.db`. After: `config.DB_PATH`
   defaulted to `data/forecast.db`; nothing referenced `joolan_live.db` any more. The app read a database that did not
   hold the published Joolan results.
2. **Credentials file moved.** `server_credentials.py` read `backend-ai/.env`; after, repo-root `.env`. A saved
   `JOOLAN_API_KEY` stops being found.
3. **Data paths derived from the package location** (`DATA_DIR = LEGACY_BACKEND_DIR / "data"`). Fine with an editable
   install, wrong with `pip install` (Docker/CI), where it resolves inside `site-packages`.
4. **Fixed constants became env-driven** through the engine/app config overlay, so a stray `FORECASTER_*` variable can
   change behaviour, and defaults drifted without any test noticing.
5. **Domain code was moved into the engine** (budgeting, catalogue, Joolan), so the "engine" stopped being a forecasting
   library, and the engine/app boundary stayed blurred.
6. **Tests were dropped** ("tests of removed legacy budget helpers") and nothing compared behaviour before/after.
7. The port is from Oct 16; current code is Oct 19 and adds purchase orders, price review, supplier FX, catalogue
   status and read/derived caches. **Do not rebase onto the old port.**

> These findings come from static comparison only. They are the leading hypotheses, not a confirmed diagnosis.

**Rules derived from this:**
- Defaults are part of the contract: DB filename, `.env` location, data directory must be asserted by tests.
- Move code and change code in separate commits. Moves must be pure.
- Never move a file and change its path anchoring in the same step.
- The engine takes arguments; it never reads env, config files or the database.

## 3. Invariants (must hold after every phase)

- All current API URLs and JSON shapes are unchanged until the frontend is deliberately migrated (Phase 5).
- The same files are read and written: `data/joolan_live.db`, `data/joolan_source.db`, `data/history.db`,
  `data/joolan_sync/`, `data/raw/`, and the credentials `.env` (location unchanged).
- Forecast numbers are unchanged for identical inputs (the forecast code is moved, never edited, in Phase 3).
- Background workers still start and survive on Windows (`CREATE_NO_WINDOW`) and Linux.
- Authentication stays **off by default**; enabling it is an explicit flag.

## 4. Phases

Every phase ends with: baseline tests green, golden master identical, route contract green. One PR per step; no
phase starts until the previous one is merged.

### Phase 0 — Lock the baseline (no production code changes)
1. Create a venv; install `backend-ai/requirements.txt`; run `python -B -m unittest discover -s tests` (89 tests) on a
   machine that has the real `data/`. Record the result in this file. (In a clean checkout without pandas, 35 of 89
   error on import; that is an environment problem, not a baseline.)
2. **Golden master:** with a fixed, committed small dataset, run the pipeline once and store the outputs
   (recommendations, key API responses: dashboard, products, projections, budget, catalogue, purchase orders,
   seasons). Add a test that re-runs and diffs.
3. **Route contract test:** generate the list of every endpoint the frontend calls (from `frontend/src/lib/api*`) and
   assert the backend registers each one with the same method. Also assert the frontend-visible response keys for the
   main endpoints.
4. **Defaults test:** assert default DB path ends in `data/joolan_live.db`, the credentials `.env` path, and the
   `data/` directory, with and without env overrides.
5. Add this suite to CI.

### Phase 1 — One deployable backend (no file moves)
1. Point `Dockerfile`, `docker-compose.yml`, CI at `backend-ai/api_server.py`. Fix the volume so `data/` maps to the
   same layout the app expects.
2. Port `auth.py`, `rbac.py`, `local_auth.py` and `/api/auth/*` as new modules mounted via the existing `install(app)`
   pattern, behind `FORECASTER_AUTH_ENABLED` (default off = current behaviour).
3. Port missing endpoints from `preduit-app`: `forecast/accuracy`, `forecast/backtest(+status)`, `admin/db/*` (backup),
   `overrides/revert(-all)`, `season-config` if still used by the frontend (check first; `/seasons` may supersede it).
4. Exit: Docker image serves the full frontend; contract test passes against the container.

### Phase 2 — Make paths explicit (before moving anything)
1. Add one `paths` module resolving `DATA_DIR`, `DB_FILE`, `HISTORY_DB`, `SOURCE_DB`, `ENV_FILE`, `OUTPUT_DIR` with
   today's exact defaults and today's env overrides.
2. Replace every `Path(__file__)` anchor (`api_server`, `database`, `ingestion`, `history_store`, `fresh_joolan`,
   `server_credentials`, `config`, `main`) with it. Pure refactor; defaults test must stay green.
3. Launch workers with `python -m <package>.<worker>` instead of `Path(__file__).with_name(...)`; verify on Windows.
4. Replace file-name based code hashes (`main.py` lineage, `backtest.py` engine hash) with a package-version or
   content hash that does not depend on file location. Record that existing lineage values will change once.

### Phase 3 — Extract the engine (code moves, no edits)
1. Create the engine from the live code: `forecasting.py`, `article_forecast.py`, `forecast_calibration.py`,
   `season_projection.py`, `launch_forecast.py`, and the live `m1`/`m2`/`m3`/`m7` copies. Public API: pure functions
   taking dataframes + a parameter object, returning dataframes/dicts.
2. Remove `config`/env/`database`/path access from these modules by passing parameters in. Where a function currently
   reads config, add an explicit argument and have the backend supply the old value.
3. Leave thin shims at the old import locations so the rest of `backend-ai` and the tests are untouched.
4. Decide (owner decision) whether SARIMA `m4`/`m5`/`m6` are retired. They are not used by the live path; remove only
   after confirming no caller and no test depends on them.
5. Golden master must be byte-identical. Any difference blocks the phase.

### Phase 4 — Layer the backend, one domain per PR
Order (smallest first): budget → price review → catalogue → purchase orders → seasons/planning → products/customers →
Joolan/fresh/automatic.
For each domain: pydantic models in `models/`, SQL in a repository, logic in a service, a thin router. URLs and JSON
unchanged. `api_server.py` shrinks until it only builds the app and mounts routers.

### Phase 5 — Delete and tidy
- Delete `preduit-app/`, `backend-ai/src` (dead Node stub), duplicate `m1`–`m8`, shims, and move `check_*`/`verify_*`
  scripts to `tools/`.
- Rename `backend-ai/` → `backend/` (only now; paths module makes this safe).
- Frontend: merge `lib/api.ts` into `lib/api/`, remove `mockData.ts` from production code, generate the API client
  from the FastAPI OpenAPI spec.
- Rewrite `PROJECT_OVERVIEW.md`; it currently contradicts the README.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Silent default drift (DB, `.env`, data dir) | Phase 0 defaults test, run in CI |
| Forecast numbers change | Golden master; Phase 3 moves code without edits |
| Workers fail silently (stdout/stderr are discarded) | Start-up test per worker; log worker stderr to a file |
| Auth turned on changes who can call what | Flag defaults off; enable deliberately with frontend roles aligned |
| Windows-only process flags regress | Test worker launch on Windows, not only Linux CI |
| Lineage/audit hashes change when files move | Phase 2 location-independent hash; document the one-time change |
| Real data needed for a meaningful golden master | Use a committed small dataset for CI, plus a local-only check against real data |

## 6. Open decisions for the owner

1. Is the SARIMA pipeline (`m4`/`m5`/`m6`) dead, or kept as a selectable method?
2. Is `/api/season-config` (from `preduit-app`) still needed, or fully replaced by `/api/seasons`?
3. Should the engine ever run as a separate service? Plan assumes a library imported in-process; the interface in
   Phase 3 (pure functions + parameter object) keeps a later service split cheap.
4. Which deployment target is authoritative (local Windows pilot vs Docker/Azure)? It decides how strictly Phase 1
   auth needs to land first.

5. Should worker stderr be logged to a file (needs key-redaction rules)?

## 7. Phase status

| Phase | Status |
|---|---|
| 0 Baseline | **done locally, not yet committed or run in CI** (see 7.1) |
| 1 One backend | **done locally, not yet committed; image build-tested locally, CI not yet run** (see 7.2) |
| 2 Explicit paths | **done locally, not yet committed** (see 7.3) |
| 3 Engine extraction | not started |
| 4 Layering | not started |
| 5 Delete and tidy | not started |

### 7.1 Phase 0 record (2026-10-21)

**Baseline** (Windows, Python 3.13.10, pandas 3.0.6, numpy 2.5.4, catboost 1.2.10, fastapi 0.156.8; venv at `.venv/`,
not committed): `python -B -m unittest discover -s tests` in `backend-ai/` ran **361 tests, all OK** before any change.
(An earlier "89 tests" figure was only the importable subset in an environment without pandas.)

**Added** (all under `backend-ai/tests/`, 10 tests; suite is now **371 tests, all OK**):

| File | Locks |
|---|---|
| `test_phase0_contract.py` + `fixtures/phase0_routes.json` | The exact 89 API routes (method + path) |
| same + `fixtures/phase0_frontend_unserved.json` | The 35 frontend calls the live backend does **not** serve today (see below). The list may only shrink. |
| `test_phase0_defaults.py` | Default `data/joolan_live.db`, `data/history.db`, `data/joolan_source.db`, credentials `.env`, `output/`; `FORECASTER_DB_PATH` override; stray `FORECASTER_*` vars do not move data. Each case runs in a fresh interpreter. |
| `test_phase0_golden.py` + `fixtures/phase0_golden_api.json` | Real pipeline on a deterministic synthetic history (768 rows), then 11 API endpoints: pipeline status, filter-options, dashboard, products, projections, recommendations, articles, customers, validation, budget, export. Only `lastRun`/`lastPipelineRun` are scrubbed. |
| same + `fixtures/phase0_golden_catboost.json` | CatBoost forecast values; pinned per platform and library versions, skipped (not failed) elsewhere |
| `phase0_support.py` | Shared helpers and the synthetic dataset |

Regenerate snapshots only for intentional changes: `UPDATE_PHASE0_SNAPSHOTS=1` (see each file's docstring).

**Verified the tests detect the earlier-port bug classes** by temporarily mutating the code (all reverted): default DB
changed to `forecast.db` (2 failures), credentials `.env` moved (1), a route renamed (3), forecast math changed (8).

**Frontend calls the live backend does not serve (35, from `phase0_frontend_unserved.json`)**: the old
`/seasons/{id}/...` contract (customers, products, recommendations, projection, dashboard, validation, import/export,
audit; 28 calls), `/auth/*` (config, users, role; 3), `/forecast/accuracy` (1), `/forecast/backtest(+status)` (2),
`/ingest/erp/status` (1). Auth, accuracy and backtest are Phase 1 work; whether the `/seasons/{id}/...` calls are live or
dead frontend code must be decided (open decision 2).

**Not covered / known limits**
- Golden master serves through the archived (non fresh-only) policy, as `test_reliability` does, because startup
  re-asserts `fresh_only`. The fresh-Joolan serving gate is covered by `test_fresh_joolan`. The real production path
  (live Joolan export, real catalogue/prices) needs a local check against real `data/`, which is **not done**.
- CatBoost is disabled in the API golden master (deterministic) and pinned per platform in its own test. The
  fixtures were recorded on Windows; **Linux CI has not been run**, so cross-platform floating-point stability of the
  API snapshot (rounded to 4 decimals) is unverified. If CI differs, investigate before regenerating.
- Not yet covered: purchase orders, catalogue and Joolan fresh-export endpoints at response level (they are covered
  by their existing unit tests, not by the snapshot). Add per-domain snapshots at the start of each Phase 4 PR.
- Worker start-up (Windows `CREATE_NO_WINDOW`) is not tested yet; Phase 2 adds it.

### 7.2 Phase 1 record (2026-10-21)

**Result:** `backend-ai` is now the single deployable backend. Suite: **392 tests, all OK** (371 + 21 new in
`tests/test_phase1_auth.py`). Phase 0 golden master and defaults tests were unchanged; only the two route snapshots were
regenerated, and only for the intended routes (+9 routes, -3 unserved frontend calls).

**Added** (flat modules in `backend-ai/`, no existing file moved):

| Module | Purpose |
|---|---|
| `access_settings.py` | Env settings: auth, roles, `FORECASTER_CORS_ORIGINS`, `FORECASTER_ALLOW_NON_LOCAL`, backup retention |
| `rbac.py` | Roles (owner = admin > manager > worker) and the route policy; unlisted routes default to **manager** |
| `auth.py`, `local_auth.py`, `users_store.py` | Token validation (local HS256 sessions, Azure Entra RS256), PBKDF2 passwords, `users` table in the serving DB (survives forecast publishes: tested) |
| `auth_routes.py` | `/api/auth/{config,signup,login,me,users,users/role}` and the `authorize()` gate |
| `db_backup.py`, `admin_routes.py` | `/api/admin/db/{health,backups,backup}`: online backups of the serving, source and history databases |
| `requirements-runtime.txt` | Packages the live path imports (suite passes with only these); `requirements.txt` is now the superset |

**Edited:** `product_routes.py` (the existing access-control middleware now calls the gate; origins come from env, default
unchanged), `api_server.py` (origins from settings, users table at startup, route installs, warning for the risky flag
combination). Deployment: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.production.example`, CI (new
`docker` job), `BRANCH_INTEGRATION.md`, `backend-ai/README.md`.

**Behaviour with defaults (auth off) is unchanged:** local-only access, no tokens, same origins. Verified with the
Phase 0 locks and by running uvicorn from a copy of `backend-ai` in a fresh venv built from `requirements-runtime.txt`
only (health, auth config/me, backup, `data/joolan_live.db` created). With auth on, verified over real HTTP: 401 without a
token, owner sign-up, role-gated routes, tampered token rejected.

**Decisions made**
- `FORECASTER_AUTH_ENABLED=true` alone turns authentication on (preduit-app also required `AUTH_DEV_BYPASS=false`, which
  left a deployment open if forgotten). The bypass defaults to on only while auth is off.
- **Not ported, deliberately:** `/forecast/accuracy` and `/forecast/backtest*` (they run the retired SARIMA engine, so
  they would report accuracy for a model the app does not use; no page calls them), `/ingest/erp/status` and
  `/overrides/revert*` (no page calls them), `/season-config` (replaced by `/seasons`). They stay listed in
  `phase0_frontend_unserved.json` until the dead client code is removed (Phase 5) or a live-engine accuracy endpoint is built
  from `backtest.py`.
- Read-only status views are worker-level (`/pipeline/*`, `/joolan/summary`, `/forecast/job`, `/events`, `/audit`,
  `/seasons`, `/articles`) because the app shell shows them to every role; preduit-app made some of these manager-only.

**Open / not verified**
- **Docker image: built and run locally** (Docker 29.8.2, `docker build` succeeded). Verified in containers: `/health` and the
  container healthcheck report healthy; with `FORECASTER_ALLOW_NON_LOCAL=1` and auth off the API serves a host browser and logs
  the warning; without it the host request gets 403; with auth on `/health` is public, `/api/dashboard` returns 401 without a
  token and the owner token works; `data/` on a named volume keeps its backup after the container is recreated; `docker compose config`
  validates. **Not done:** `docker compose up` of the full stack (the frontend image was not built), and the new CI `docker` job has not run on GitHub.
- The 28 `/seasons/{id}/...` frontend calls are still unserved (open decision 2).
- Azure Entra SSO validation was ported verbatim but not exercised (needs a tenant).
- The app still fails at start-up if `backend-ai/data/` does not exist (unchanged; the Dockerfile and quick-start create it).
- Frontend roles (`msalConfig.ts`) and backend `rbac.py` are two copies of the same policy; keep them in sync until the
  OpenAPI client lands (Phase 5).

### 7.3 Phase 2 record (2026-10-21)

**Result:** one module, `paths.py`, is the only place that looks at `__file__`. Suite: **403 tests, all OK** (392 + 11 in
`tests/test_phase2_paths.py`). The Phase 0 golden master and defaults locks passed unchanged, so behaviour with default settings is the same.

| Change | Detail |
|---|---|
| `paths.py` | `CODE_DIR` (where modules live), `HOME` (root of `data/`, `output/`, `.env`), `LIVE_DB`, `SOURCE_DB`, `HISTORY_DB`, `RAW_DIR`, `SYNC_DIR`, `OUTPUT_DIR`, `ENV_FILE`. Default `HOME` = the code folder (unchanged). New optional `FORECASTER_HOME` relocates all of it. `FORECASTER_DB_PATH` still overrides the serving DB only. |
| Anchors replaced | `database`, `history_store`, `fresh_joolan`, `server_credentials`, `ingestion`, `api_server`, `config`, `main` now take their root from `paths`. Their module-level names (`BASE_DIR`, `DB_FILE`, `DEFAULT_PATH`, `SOURCE_DB`, `ENV_FILE`) are kept so nothing else changes. A test fails if any live module reintroduces `__file__`. |
| Workers | `automatic_forecast` and `fresh_routes` start `python -B -u -m automatic_worker|fresh_worker <id>` with `cwd=paths.CODE_DIR`; no script path. Tested in a relocated copy of the code, as a real detached launch, and inside the Docker image. |
| Code hashes | New `code_fingerprint.py` finds sources by module name. `lineage.codeHash` and the backtest `engineHash/engineFiles` keep the same algorithm and keys; they depend on file contents only (a copy of the code elsewhere produces the same hash). They still change whenever the hashed source changes, including this phase's edits to `main.py` and `backtest.py`. |
| Tests touched | The four places that patched `main.__file__` to redirect output now patch `main.BASE_DIR` (same effect, no `__file__`). |

**Verified:** relocation (code copied to a new folder: data follows the copy by default, follows `FORECASTER_HOME` when set; code location
independent); workers import and run from the copy and write only to the data home; a real `fresh_routes.launch` starts a detached child on
Windows; the rebuilt Docker image serves `/health` and both workers start by module name inside it. Mutation checks (anchor reintroduced,
`FORECASTER_HOME` ignored, script-path launch restored) are all caught.

**Deliberately not done**
- **Worker stderr is still discarded.** Logging it would help diagnose silent failures, but tracebacks in the export worker may sit next to the
  Joolan key (it arrives on stdin); this needs a redaction decision first (open decision 5).
- The `/data/...` and `data/raw/...` sub-paths are still written as literals relative to each module's root (kept so existing tests can patch
  `BASE_DIR`). Only the root is centralised; Phase 4 can move the layout into repositories.
- Legacy scripts (`check_*`, `verify_*`, `audit_*`, `build_*`, `repair_*`, `test_db.py`) still use their own `__file__` paths.
