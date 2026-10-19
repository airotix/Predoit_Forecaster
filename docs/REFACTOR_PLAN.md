# Preduit / Forecaster — Package split refactor plan

This document inventories `backend-ai/` Python modules (16 files), maps cross-module imports, classifies `config.py` symbols for a **`preduit-engine`** vs **`preduit-app`** split, flags coupling risks, and records whether `backend-ai/src/` (TypeScript) and `main.py` are live or dead relative to the documented stack.

**Scope:** All `backend-ai/**/*.py` files were read. Ignored per instructions: `__pycache__/`, `node_modules/`, `catboost_info/`, `data/`, `output/` (content not enumerated).

---

## 1. Python modules inventoried

| File | Role |
|------|------|
| `config.py` | Env-backed settings + schema column constants |
| `database.py` | SQLite schema, indexes, `populate_database` |
| `ingestion.py` | Incremental ingest, merge with base CSV, upserts |
| `m1_data_preparation.py` … `m8_output.py` | Forecasting pipeline |
| `main.py` | CLI orchestrator: runs m1–m8 then DB populate |
| `api_server.py` | FastAPI HTTP API + ingest + async forecast job |
| `backtest.py` | Walk-forward backtest (imports legacy SARIMA helpers) |
| `check_setup.py` | Diagnostic script |
| `test_db.py` | DB smoke tests + imports API helpers |

---

## 2. Cross-module imports (project-local)

Listed as **`file:line`** → **`import`**. Stdlib and third-party imports are omitted.

### Explicit imports

```
backend-ai/database.py:11
  from config import DB_PATH as DB_FILE

backend-ai/ingestion.py:17-18
  from database import _safe_val, get_connection

backend-ai/ingestion.py:18-23
  from m1_data_preparation import (
      _standardize_columns,
      aggregate_monthly_sku_color,
      aggregate_monthly_sku_color_size,
      parse_and_prepare,
  )

backend-ai/ingestion.py:62
  from config import DATA_FILE_PATH   # inside merge_config_csv_with_append()

backend-ai/ingestion.py:376
  from config import DATA_FILE_PATH   # inside load_mock_erp_dataframe()

backend-ai/main.py:22
  from config import DATA_FILE_PATH

backend-ai/main.py:40
  from ingestion import merge_config_csv_with_append   # inside run_phase1()

backend-ai/main.py:93
  from m1_data_preparation import run_module1

backend-ai/main.py:99
  from m2_model_assignment import run_module2

backend-ai/main.py:105
  from m3_kpis import run_module3

backend-ai/main.py:111
  from m4_sarima import run_module4

backend-ai/main.py:117
  from m5_catboost import run_module5

backend-ai/main.py:130
  from m6_size_curves import run_module6

backend-ai/main.py:141
  from m7_recommendations import run_module7

backend-ai/main.py:155
  from m8_output import run_module8

backend-ai/main.py:167
  from database import populate_database

backend-ai/api_server.py:28
  import config

backend-ai/api_server.py:29
  from database import get_connection, _create_persistent_tables, ensure_pipeline_schema

backend-ai/api_server.py:30-40
  from ingestion import (
      append_to_ingest_csv,
      bump_import_metadata,
      dedupe_and_upsert,
      load_mock_erp_dataframe,
      new_job_id,
      normalize_dataframe,
      refresh_non_ml_aggregates,
      insert_job_running,
      update_job_complete,
  )

backend-ai/api_server.py:1331
  from main import run_phase1   # inside _run_forecast_pipeline_job()

backend-ai/backtest.py:19
  from config import *

backend-ai/backtest.py:24-27
  from m1_data_preparation import (
      parse_and_prepare, aggregate_monthly_sku_color,
      aggregate_monthly_sku_color_size
  )

backend-ai/backtest.py:28
  from m2_model_assignment import compute_history_profile, assign_models

backend-ai/backtest.py:29
  from m3_kpis import compute_sku_kpis, compute_size_kpis, compute_category_kpis

backend-ai/backtest.py:30
  from m4_sarima import build_complete_monthly_series, fit_sarima_single

backend-ai/backtest.py:31-34
  from m5_catboost import (
      build_catboost_features, determine_size_order,
      CATBOOST_AVAILABLE
  )

backend-ai/backtest.py:35-38
  from m6_size_curves import (
      compute_product_size_curves, correct_stockout_distortions,
      apply_business_rules
  )

backend-ai/backtest.py:1037
  from m1_data_preparation import load_data   # inside run_backtest()

backend-ai/backtest.py:1110
  from m1_data_preparation import load_data   # inside run_quick_backtest()

backend-ai/test_db.py:9
  from database import DB_FILE as DB_PATH

backend-ai/test_db.py:40
  from database import get_connection   # inside main()

backend-ai/test_db.py:69
  from api_server import _get_filtered_recommendations, _get_demand_trend_by_references, _rows_to_articles

backend-ai/check_setup.py:49
  import config   # inside try; uses config.DATA_FILE_PATH

backend-ai/m2_model_assignment.py:118
  from m1_data_preparation import run_module1   # __main__ only
```

### Star imports from `config` (implicit dependency on many symbols)

```
backend-ai/m1_data_preparation.py:16   from config import *
backend-ai/m2_model_assignment.py:12   from config import *
backend-ai/m3_kpis.py:13               from config import *
backend-ai/m4_sarima.py:21             from config import *
backend-ai/m5_catboost.py:15           from config import *
backend-ai/m6_size_curves.py:14          from config import *
backend-ai/m7_recommendations.py:13      from config import *
backend-ai/m8_output.py:14               from config import *
```

**Notes:**

- `api_server.py` uses **`import config`** (module) rather than star-import; references include `config.FORECAST_THREAD_POOL_SIZE`, `config.OUTPUT_DIR`, `config.BUDGET_MULTIPLIER`, `config.TARGET_MARGIN_DISPLAY`, `config.SSE_POLL_INTERVAL_SECONDS`, `config.API_HOST`, etc.
- Dependency DAG for local imports (excluding `backtest.py`’s broken `m4` imports): **`config` ← (`database`, `m1`…`m8`) ← `ingestion` ← (`main`, `api_server`); `database` ← (`main`, `ingestion`, `api_server`, `test_db`).**

---

## 3. `config.py` — constant-by-constant classification

Engine modules will continue using `from .config import *` after the refactor (**Choice A**). Migration to a typed `EngineSettings` injection pattern is deferred to a later refactor.

Legend: **ENGINE** = versioned ML/library defaults and algorithm parameters; **APP** = per-deployment paths, API, client schema/locale, artifacts; **AMBIGUOUS** = needs a product decision.

| Symbol | Label | Notes |
|--------|-------|-------|
| `BACKEND_DIR` | APP | Anchors repo-specific layout; engine should not assume this path exists. |
| `PROJECT_ROOT` | APP | Used for `.env` and resolving relative `FORECASTER_DATA_FILE`. |
| `load_dotenv(...)` (side effect) | APP | Deployment/environment bootstrap. |
| `_BASE_DIR` | APP | Derived from `BACKEND_DIR`; same as above. |
| `_env_str`, `_env_int`, `_env_float`, `_env_optional_float`, `_env_bool`, `_env_list` | ENGINE | Pure utilities with no client-specific or algorithm content. Place in `preduit_engine/_env.py` or as private helpers in `preduit_engine/config.py`. |
| `DB_PATH` | APP | Client SQLite location (`FORECASTER_DB_PATH`). |
| `API_HOST`, `API_PORT`, `API_RELOAD` | APP | FastAPI/uvicorn deployment. |
| `CORS_ORIGINS` | APP | Browser integration for this deployment. |
| `DATA_FILE_PATH`, `DATA_FILE_NAME` | APP | Primary input CSV for this client. |
| `DATA_SEPARATOR`, `DATA_ENCODING` | APP | File format for this client’s exports. |
| `COL_CLIENT` … `COL_CDE_FOUR_QTE` (source CSV schema) | APP | French / ERP-specific column naming for this client’s files. |
| `COL_TRUE_DEMAND`, `COL_YEAR_MONTH`, `COL_SEASON_TYPE`, `COL_SEASON_YEAR`, `COL_PRODUCT_STATUS`, `COL_MODEL_ASSIGNMENT` | ENGINE | Canonical **derived** field names created by the pipeline (internal contract); keep stable in the library unless versioning a breaking change. |
| `FORECAST_GRANULARITY` | ENGINE | Currently **unused** elsewhere in repo (only defined in `config.py`). |
| `SARIMA_SEASONAL_PERIOD` | ENGINE | Intended algorithm tuning; **not referenced** in `m4_sarima.py` today (`auto_arima` uses hardcoded `m=12` or `m=2`). |
| `SARIMA_MIN_MONTHS_SPAN` | ENGINE | Used in `m2_model_assignment.assign_models`. |
| `CATBOOST_MIN_MONTHS` | ENGINE | Used in `m2_model_assignment.assign_models`. |
| `FORECAST_HORIZON_MONTHS` | ENGINE | `m4_sarima`, `m5_catboost`. |
| `SARIMA_P_MAX`, `SARIMA_D_MAX`, `SARIMA_Q_MAX`, `SARIMA_SP_MAX`, `SARIMA_SD_MAX`, `SARIMA_SQ_MAX` | ENGINE | Defined for tuning but **not wired** into `m4_sarima.fit_sarima` (hardcoded `max_p`/`max_q`/… instead). Dead knobs until connected or removed. |
| `CATBOOST_ITERATIONS`, `CATBOOST_DEPTH`, `CATBOOST_LEARNING_RATE`, `CATBOOST_L2_REG`, `CATBOOST_EARLY_STOPPING` | ENGINE | `m5_catboost`. |
| `QUANTILE_CONSERVATIVE`, `QUANTILE_BASE`, `QUANTILE_OPTIMISTIC` | ENGINE | `m5_catboost`. |
| `MIN_UNITS_FOR_PRODUCT_SIZE_CURVE` | ENGINE | `m6_size_curves`. |
| `SIZE_MAX_SHARE_CAP` | ENGINE | `m6_size_curves.apply_business_rules`. |
| `SIZE_MIN_QTY` | ENGINE | **Unused** in pipeline modules (only in `config.py`). |
| `EXTREME_SIZE_DAMPENING_FACTOR` | ENGINE | **Unused** in pipeline modules (only in `config.py`). |
| `SIZE_ORDER_ALPHA`, `SIZE_ORDER_NUMERIC`, `SIZE_ORDER_PANTS` | ENGINE | Taxonomy / ordering for algorithms (`m5`, `m6`); apparel-specific — still library “constants” unless you internationalize size logic per vertical. |
| `DEFAULT_COST_RATIO` | APP | Per-client business policy. The configured value lives in `client_config.py` (or equivalent app overlay); engine functions that use it (`m3_kpis`, `m7_recommendations`) should accept it as a parameter. |
| `TARGET_MARGIN_RATE` | AMBIGUOUS | **Unused** outside definition; optional future KPI vs dead. |
| `SEASONAL_BUDGET` | AMBIGUOUS | **Unused** outside definition; dashboard uses `BUDGET_MULTIPLIER` instead. |
| `BUDGET_MULTIPLIER` | APP | Used in `api_server.py` for dashboard/budget UI (`FORECASTER_BUDGET_MULTIPLIER`). |
| `TARGET_MARGIN_DISPLAY` | APP | Display target in API responses (`FORECASTER_TARGET_MARGIN_DISPLAY`). |
| `ACTIVE_CLIENT_LOOKBACK_MONTHS` | APP | What counts as an “active customer” is a per-client business definition (`m3_kpis`). Configure in app / `client_config.py`; engine call sites should accept it as a parameter where practical. |
| `OUTPUT_DIR` | APP | Artifact directory for this deployment (CSV/Excel outputs). |
| `OUTPUT_RECOMMENDATIONS_FILE`, `OUTPUT_SUMMARY_FILE`, `OUTPUT_MODEL_PERFORMANCE_FILE`, `OUTPUT_MONTHLY_DETAIL_FILE` | APP | Filenames for outputs; `m8_output` partly hardcodes monthly detail name (see coupling). |
| `FORECAST_THREAD_POOL_SIZE` | APP | API thread pool (`api_server`). |
| `SSE_POLL_INTERVAL_SECONDS` | APP | SSE polling interval (`api_server`). |

---

## 4. Tight coupling and split risks

### Hardcoded / relative paths

- **`ingestion.py`** (`28:34`): `BASE_DIR / "data" / "raw" / "ingest_append.csv"` and `.pipeline_merged.csv` — tied to package directory layout, not to `DATA_FILE_PATH` parent.
- **`m8_output.py`** (`256`): monthly detail written as `"forecast_monthly_detail.csv"` while `config.OUTPUT_MONTHLY_DETAIL_FILE` defaults to the same string — **duplicated**; drift risk if config changes.
- **`api_server.py`** (`46:51`): resolves `OUTPUT_DIR` relative to `api_server.py` parent — correct for monolith, must stay explicit in **app** package.

### Global config instead of parameters

- **`m1`–`m8`** overwhelmingly use `from config import *` and default arguments like `filepath=DATA_FILE_PATH`, `output_dir=OUTPUT_DIR`. Splitting packages cleanly favors a **`PipelineSettings` / `EngineConfig`** object injected from **app** (paths, column map, thresholds) plus **engine defaults** for algorithm constants.
- **`database.py`** reads **`DB_PATH` at import time** (`11:13`) and creates the directory immediately — hard to use multiple DB paths or test isolation without refactoring to lazy/path-parameterized connections.

### Schema coupling

- **`database.py`** embeds French/display column names in merge logic (e.g. `"Designation"`, `"Reference"` in `_insert_recommendations`) while DB columns are English/lowercase — assumes pipeline output column casing matches current ERP convention.
- **`ingestion.merge_config_csv_with_append`** dedupes on fixed names `Client`, `Reference`, `Couleur`, … — must stay aligned with **APP** column mapping layer after refactor.

### Duplicated domain logic

- **`api_server.SIZE_ORDER`** (`119:121`) partially overlaps **`config.SIZE_ORDER_ALPHA`** / ordering rules in **`m5`/`m6`** — risk of inconsistent sort orders between API and ML outputs.

### Circular / layered import hazards

- No import-time cycle among `config` → `database` → `ingestion` → `m1`.
- **`api_server`** → **`main`** (`1331`) is **lazy** (inside job runner), which avoids cycles but couples HTTP layer to a script module named `main`; preferable entry: **`preduit_app.pipeline.run_full`** or callable exported from **engine**.

### Stale or broken code paths

- **`backtest.py`** imports **`build_complete_monthly_series`** and **`fit_sarima_single`** from **`m4_sarima`** (`30`), but **`m4_sarima.py` does not define these symbols** (repository-wide grep only hits `backtest.py`). **Backtest is currently inconsistent with the live pipeline** and will fail on import or first fold unless restored or deleted.
- **`backtest._run_catboost_fold`** expects feature columns (e.g. `demand_lag_12`, `is_off_season`) that **`m5_catboost.build_catboost_features` does not produce** — second signal that **backtest predates current `m5`**.

---

## 5. `backend-ai/src/` (TypeScript Express) and `main.py` — real vs dead?

### `main.py`

- **Real, active path.** Documented in its module docstring (`python main.py`, optional `--data`).
- **Imported at runtime** by FastAPI: `api_server.py` (`1331`) calls `run_phase1()` for `/api/forecast/refresh`.
- **`check_setup.py`** treats `main.py` as required for a healthy setup.

### `backend-ai/src/` Express stub

- **`package.json`** scripts run **`tsx watch src/index.ts`** / compiled **`dist/index.js`** — the npm workflow targets Express.
- **`backend-ai/README.md`** describes **only** the Express API (`npm run dev`, endpoints `/api/articles`, `/api/filter-options`).
- The **implemented production-style API in this repo is `api_server.py` (FastAPI)** with a much larger route surface (dashboard, budget, ingest, SSE, etc.).
- **Nothing in the Python codebase imports `src/`** (Python cannot); grep shows **no references** from frontend docs in this analysis beyond the backend README.

**Conclusion:** The **TypeScript Express app is a legacy / parallel stub** relative to the **FastAPI + SQLite** stack implied by `api_server.py`, `database.py`, and `test_db.py`. Treat **`src/` as dead for the Python refactor** unless you explicitly revive it; align documentation with **FastAPI** as the real HTTP layer.

---

## 6. Suggested next steps (no code changes in this pass)

1. Split settings across **`preduit-engine`** vs **`preduit-app`** per Section 3; engine modules keep **`from .config import *`** for the first refactor (**Choice A** — Section 3). Typed **`EngineSettings`** injection remains a later refactor.
2. Move **`database.py`** schema + DDL to **engine** (versioned migrations recommended); inject **`db_path`** from **app**.
3. Delete **`backtest.py`** before the split (**Section 7**); do not migrate it.
4. Consolidate **`SIZE_ORDER`** logic in one place (engine or shared constant module consumed by app for API sorting).
5. Update **`backend-ai/README.md`** to describe **FastAPI** (`uvicorn api_server:app`) or relocate TS stub under `legacy/` with a clear label.

---

## 7. Pre-refactor cleanup decisions

- **`backtest.py`** is broken (it imports symbols that do not exist in the current `m4`/`m5`). **Delete it before the refactor** — do not migrate it to either package. A new backtest harness will be built post-launch.
- **`check_setup.py`** and **`test_db.py`**: keep under **`preduit-app/`**; do not migrate to the engine. They validate app-level concerns (environment, DB populated from a full run, API response shapes).
- **Known duplication bugs — leave as-is during the refactor**; fix post-refactor and track with **TODO comments only** (no behavioral changes in this phase):
  - **`m8_output.py:256`** — hardcodes a filename that duplicates `config.OUTPUT_MONTHLY_DETAIL_FILE`.
  - **`api_server.py:119`** — `SIZE_ORDER` duplicates `config.SIZE_ORDER_ALPHA` (and related ordering intent).

---

*Generated from a read-only audit of `backend-ai/*.py` — no application code was modified.*
