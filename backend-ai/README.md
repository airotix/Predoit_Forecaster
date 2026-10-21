# Forecaster Python backend

## Current deployment: fresh Joolan API only

For a new machine, follow [QUICK_START.md](../QUICK_START.md) for installation, environment settings, first-run setup and moving saved data.

Use [RUN_FORECAST.md](../RUN_FORECAST.md). The default serving database is now
`data/joolan_live.db`; newly exported source versions go to `data/joolan_source.db`.
The API and public CLI forecast entry point exclude previous CSVs, workbooks
and legacy source selection. Setup discovers live fields, selects warehouses,
exports new COMMANDE history, validates it and activates a complete source version.
Export workers checkpoint complete pages and resume after quotas or interruption.

See [mapping and operations notes](../docs/FRESH_JOOLAN.md) for the field contract,
known limitations and live acceptance checks.

## Archived implementation notes: CSV + Joolan history

The following sections describe the earlier workflow retained for reference and
regression testing. Those import controls are disabled in the current deployment.

`data/history.db` is the persistent source database. It retains all normalized CSV rows (including repeated lines), compressed source payloads, newer Joolan raw lines with document types/quarantine status, and a separate confirmed customer-order view. The CSV is authoritative through its latest order date. Joolan rows on or before that date are not added to the forecast view; historical revisions require separate reconciliation.

Setup prefills **From order date** with the day after the CSV cutoff (February 27, 2026 for the supplied file), and **Through order date** with the browser's current local date. Direct sync applies these dates to header `Date` before download and retrieves only lines linked to compatible dated headers. End dates include the whole selected day. Date/type/enseigne scope is included in resume checkpoints; different ranges never share download cursors.

After syncing, click **Build CSV + Joolan database**. Raw newer records are saved even before a document type is confirmed. Confirm the type to prepare the customer-order view, then choose **Use combined history** and refresh forecasts. The database replaces refreshed Joolan date/type ranges rather than appending duplicates; older stored periods remain available. Missing date ranges block forecasting. Current partial months remain in source history and actuals but are excluded from monthly model training until coverage reaches month-end. Historical stock, prices and costs do not become current operational inputs; provide actual planning inputs until live inventory mapping is complete.

Endpoints: `POST /api/history/build`, `GET /api/history/summary`; Joolan sync accepts optional ISO `startDate` and `endDate`. The supplied CSV baseline has been imported locally: 479,932 rows from 2016-01-02 through 2026-02-26. The source database is separate from `forecast.db`, which serves published results.

## Daytona 73 discovery step

Setup now includes **Inspect historical CSV** and, under **Connect directly to Joolan**, **Discover tables and columns**. Historical inspection scans the configured base CSV in chunks and shows recorded dates, row counts and invalid dates. It does not train a model or establish complete monthly coverage.

Enter the verified Daytona 73 enseigne and a Queries-enabled API key, then discover the schema. The result can be searched and downloaded as `joolan-data-dictionary.json`. This reads `information_schema.COLUMNS` only; it does not read inventory values or modify Joolan. If metadata access is unavailable, request a table/column dictionary from Joolan. Keys remain in memory and are not included in the dictionary.

New endpoints: `GET /api/history/profile` and `POST /api/joolan/schema` with `apiKey` and `enseigne`. Stock and supplier-order mappings still need reconciliation against the actual schema. Legacy history and Joolan order snapshots remain separate until overlap and quantity definitions are verified.

Direct sync requests up to 10,000 rows per page by default to reduce query usage. Joolan may return fewer rows. An hourly quota rejection stops immediately rather than retrying more queries. The operator must wait for Joolan's quota reset and supply the key again; the app cannot reset that quota or determine the reset time from the observed error.

An explicitly entered document type now filters `Nature` in both `negoce_entetes` and `negoce_lignes` before probing, counting, capturing boundaries and retrieving pages. Blank still retrieves all types. Filter values are safely encoded as SQL hex literals. The customer's export lists `COMMANDE`, but confirm its business classification before activation. Resume checkpoints include the selected scope; older unfiltered checkpoints are not reused for a filtered download. Raw field availability was verified in the saved export, but live filtering still needs verification against Joolan.

Completed pages and their cursors are checkpointed under `data/joolan_sync/`, separately for each enseigne/document filter; API keys are never saved there. This local cache contains order data and is excluded from Git. Downloads with accessible primary keys can resume within 24 hours after checking bounded row counts. Uncheckpointed partial bytes are discarded. Changed counts invalidate the saved download; OFFSET-only downloads restart. Complete downloads are joined in disposable scratch space and serving snapshots are still published atomically. Successful downloads remove their page/checkpoint files. Records with unchanged counts may have changed while paused, so this remains a count-checked read rather than a transactional ERP snapshot.

The active product uses FastAPI, SQLite and the Next.js frontend. The older Node articles demo and the old M4/M5 forecasting scripts are retained for reference; the dashboard refresh now uses `forecasting.py`.

## Run locally

From `backend-ai`, run:

```powershell
python -m uvicorn api_server:app --host 127.0.0.1 --port 4000
```

From `frontend`, run `npm.cmd run dev`, then open `http://localhost:3000/setup`. Keep both terminals running. The frontend API URL defaults to `http://localhost:4000/api`; an override must include `/api`.

The active Python path needs pandas 2 or newer, NumPy, CatBoost, openpyxl, FastAPI, python-multipart and uvicorn. CatBoost can be disabled with `FORECASTER_DISABLE_CATBOOST=1`; validated baselines remain available. The older SARIMA/explanation scripts additionally use the statistical packages in requirements.txt. Tests need httpx.

Requests default to local-only access and trusted localhost browser origins. A shared deployment requires authenticated requests, HTTPS, an explicit origin policy and appropriate user permissions; the current browser UI is intended for local use. Do not expose this app publicly by changing only the bind address. `FORECASTER_API_TOKEN` enables the backend's shared-secret authorization check; it does not implement user roles.

### Where files live

All run-time files (`data/`, `output/`, the credentials `.env`) sit under one root, defined only in `paths.py`. By default that is the folder containing the code (`backend-ai/`), exactly as before. Set `FORECASTER_HOME` to keep them elsewhere, so moving or packaging the code never changes where saved Joolan data and credentials are found. `FORECASTER_DB_PATH` still overrides the serving database only. Background workers are started as `python -m automatic_worker` / `python -m fresh_worker` from the code folder and inherit the environment.

### Authentication and roles

Authentication is off by default (nothing changes). Set `FORECASTER_AUTH_ENABLED=true` and a strong `FORECASTER_AUTH_SECRET` to require sign-in: local email/password accounts (the first sign-up becomes owner; set `FORECASTER_AUTH_ALLOW_SIGNUP=false` afterwards) and optional Azure Entra SSO (`FORECASTER_AZURE_TENANT_ID`, `FORECASTER_AZURE_CLIENT_ID`). Roles: **worker** (dashboard, products, projection, status), **manager** (everything else read/write), **admin/owner** (Joolan exports, forecasts, ingestion, user management, backups). Routes not listed in `rbac.py` default to manager. With authentication on, bearer tokens replace the local-only rule; browser origins come from `FORECASTER_CORS_ORIGINS`. `FORECASTER_ALLOW_NON_LOCAL=1` is for containers behind a localhost-only port mapping and must not be combined with a public port while authentication is off.

Operators: `POST /api/admin/db/backup` copies the serving, Joolan source and history databases to `data/backups` (`FORECASTER_BACKUP_DIR`, `FORECASTER_BACKUP_KEEP`); `GET /api/admin/db/health` runs integrity checks.

## Joolan customer orders

1. In Setup, import the trade-document workbook or connect to Joolan's HTTPS Query API. The enseigne is `legend73`, not the MySQL username `joolan_legend73`. The API key needs Queries permission and stays in memory.
2. Review document types and confirm the exact Joolan `Nature` representing customer orders. The app does not guess it or mix invoices and credits into customer-order demand. A blank sync filter retrieves all types for inspection, but source activation requires confirmation.
3. Select **Use confirmed customer orders for forecasts**.
4. Import actual SKU inputs using the downloadable template: `Reference`, `Couleur`, `Taille`, `Selling_Price`, `Purchase_Cost`, `STOCK`, `CDE_four_qte`. The latter is incoming stock. Unknown fields remain unknown; enter zero only when the actual value is zero. Values must use the plan's currency and a consistent tax basis.
5. Save a planning season with dates after the latest historical month, budget, currency and target margin. Click Refresh forecasts. The run-status banner identifies the published source, history cutoff and forecast dates, and warns if inputs changed afterward.
6. Inspect customer order lines and quantities. Download a draft to review; an approved quantity CSV requires complete actual financial/inventory inputs and known cancellations. This downloads a file; it does not submit purchase orders to Joolan.

The trade sheet maps `Order_Number`, `Customer`, `Order_Date`, `Product`, `Ordered_Quantity`, `Delivered_Quantity`. Optional `Store`, `Colour`, `Size`, `Document_Type`, `Link_Status`, `Date_Status`, `Cancelled_Quantity` and `Line_Number` improve identity and quality checks. The direct connector preserves cancellation/line fields only when supplied by Joolan; their presence in your live schema has not been verified. The original six-field export cannot establish cancellation quantities. Do not mark missing cancellations as zero without confirming that with Joolan.

Imports retain repeated order/item lines, leading-zero identifiers, dates and fractional quantities. Missing links, invalid dates/quantities and inconsistent delivered/cancelled totals remain visible in quarantine and are excluded from forecasts. Workbooks marked INCOMPLETE and interrupted downloads preserve the prior snapshot. Snapshot loading stages rows before atomic replacement. Direct sync captures both tables' maximum primary keys before downloading and uses bounded keyset pagination when metadata exposes those keys. Later inserts above the bounds wait until the next sync. Changes to bounded counts trigger up to three complete download attempts. Tables without accessible keys retain strict OFFSET/count checks. These reads are not a transactional source snapshot: existing-row edits with unchanged counts can still affect results.

Joolan demand is ordered quantity minus known cancellations. If cancellations are missing it is explicitly gross ordered demand, and approved exports are blocked. Delivered units are separate. The undelivered balance is ordered minus delivered minus known cancellations, across all recorded orders; it is not allocated to the planning season because the six-field source lacks delivery dates. Stock, prices and costs are never inferred from those six fields.

## Forecast and purchase calculations

Every product/color/size series uses a monthly calendar and common cutoff. Missing months are treated as zero, so complete source coverage must be verified. Sparse/new series are retained. Training uses prior observations only, advances lag features recursively and limits training rows before allocation.

Per-series past-only validation compares seasonal-naive, recent mean, seasonal blend, intermittent TSB, zero demand and optional pooled CatBoost. CatBoost is used only where it wins that validation. Production horizons come from the saved planning dates (up to 24 months, at most 36 months beyond the data cutoff). Conservative/optimistic values use empirical validation residuals; they are not calibrated prediction intervals or fixed 85%/115% multipliers. Historical KPIs are descriptive, not evidence of customer visits or clustering.

`purchase quantity = max(forecast demand - available stock - incoming stock, 0)` when inventory is known. Manual edits replace that quantity and are saved per size, scenario and plan. Locks and reset actions are enforced by the backend. Unknown inventory leaves the proposed purchase quantity unknown rather than assuming zero stock. Purchase cost uses actual unit cost times final purchase quantity; turnover uses demand times actual selling price. Demand margin accounts for unit costs for all forecast units, including existing inventory. The selected plan supplies the budget and margin target. This is a planning calculation, not full tax, cash-flow or service-level optimization.

Forecast publication replaces all serving tables in one SQLite transaction. Failed publication preserves the prior run and persistent edits/locks. Outputs are versioned under `output/runs/<run-id>/`, including model selection and lineage. The default database is `data/forecast.db`; `FORECASTER_DB_PATH` can override it explicitly. Old generated forecasts are not automatically overwritten by importing data; refresh is required.

Legacy incremental imports normalize names, retain order-line identities and rebuild actuals from the complete deduplicated base plus imports. Re-uploading the same snapshot does not add its quantities twice. Failed imports roll back actuals and restore the append file. Invalid legacy dates or numeric quantities are rejected rather than silently becoming zero or disappearing. ISO dates keep year-month-day order; other supported legacy dates use French day-month-year interpretation.

## Verification and measured limits

Run `python -B -m unittest discover -s tests` from backend-ai. Tests use temporary databases and mocked Joolan responses. Run `npm.cmd run build` from frontend for compilation, type checking and linting.

The final isolated benchmark sampled 900 previously unused product variants from the existing legacy monthly database, using three six-month rolling tests ending February 2025, August 2025 and February 2026. The current engine reduced absolute error by 21.3% versus seasonal-naive forecasting, but weighted percentage error remained 142.9%, versus 181.5% for seasonal-naive and 100% for predicting zero everywhere. Thus the engine beat that seasonal baseline but did not beat the zero baseline overall. It is not established as accurate enough for autonomous purchasing. High band coverage on sparse data does not prove calibrated uncertainty. Live Joolan accuracy, new products appearing after a test cutoff, stockout-censored demand, delivery lead times and customer-level forecasts were not validated.

To improve further, first confirm complete customer-order coverage, cancellation fields, live stock/costs and original business seasons; then evaluate on a future, untouched Joolan period and review errors by product family and activity level. Do not tune against the same held-out period and report it as independent validation.

Key endpoints: `/api/joolan/summary`, `/api/joolan/orders`, `/api/joolan/file`, `/api/joolan/sync`, `/api/joolan/order-type`, `/api/joolan/forecast-source`, `/api/planning/inputs`, `/api/seasons`, `/api/orders`, `/api/pipeline/lineage`, `/api/forecast/refresh`, `/api/forecast/job`, `/api/ingest/status/{jobId}`, `/api/export?scenario=base&purpose=draft`.

## Older Node demo reference

The following belonged to the older Node stub. Use the Python/Joolan quick start above for the current application.

# Forcaster Backend API

Backend for the Forcaster forecast dashboard. Serves article data and filter options.

## Setup

```bash
npm install
```

## Run

```bash
npm run dev   # Development (tsx watch)
npm run build # Build for production
npm start     # Run built app
```

## Endpoints

| Method | Path | Query Params | Description |
|--------|------|--------------|-------------|
| GET | `/api/articles` | `season` (required), `supplier`, `family`, `theme`, `model`, `customer`, `searchQuery` | Returns filtered articles |
| GET | `/api/filter-options` | `season` (required) | Returns filter dropdown options for a season |

Valid seasons: `SS2024`, `FW2024`, `SS2025`, `FW2025`

## Environment

- `PORT` - Server port (default: 4000)

## Frontend

The frontend expects the API at `http://localhost:4000` by default. Override with `NEXT_PUBLIC_API_URL` in the frontend `.env.local`.
