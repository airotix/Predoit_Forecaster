# Quick start — setup and run on another machine

This guide runs the current **Python FastAPI backend + Next.js frontend** locally. Data comes from fresh Joolan API exports. You do not need the old training CSV, the older Node backend demo, or a separate database server.

Commands below use **Windows PowerShell**, starting in the project root (`forecasterr`). Keep two terminals open while using the app.

After integrating with `main`, the older packaged backend and container files are also present. This guide runs the current local Joolan API; see [integration boundaries](docs/BRANCH_INTEGRATION.md) before using Docker or enabling authentication for a shared deployment.

## 1. Get the project and prerequisites

Install Git, 64-bit Python, and Node.js with npm. The current development machine runs **Python 3.14.4 and Node.js 24.14.1**; these are reference versions, not a frozen dependency lock.

Copy the current project folder, or clone the branch containing this layout:

```powershell
git clone --branch codex/publish-preduit --single-branch https://github.com/airotix/Preduit-forecaster.git forecasterr
cd forecasterr
python --version
node --version
npm.cmd --version
```

GitHub access is required if the repository is private. **A clone only includes pushed commits.** Before handing off this working copy, include its uncommitted/new source files too, or commit and push them. Do not transfer `.venv`, `node_modules`, `.next`, `.next-dev`, or credentials as part of a source-only handoff.

Internet access is needed for dependency installation and Joolan exports. Allow several GB of free space for data, SQLite journals, exports and model artifacts; a full export/training run can take many minutes and span Joolan quota windows.

## 2. Install once

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install "pandas>=2.0.0" "numpy>=1.23.0" "catboost>=1.2" "scikit-learn>=1.2.0" "openpyxl>=3.0.0" fastapi python-multipart "uvicorn[standard]"
New-Item -ItemType Directory -Force backend-ai/data | Out-Null
cd frontend
npm.cmd ci
cd ..
```

The Python command installs the active app's runtime dependencies. `backend-ai/requirements.txt` additionally includes statistical/explanation packages for older scripts; install that file if you need those scripts. Always install into this new virtual environment. The commands use its Python directly, so PowerShell activation permissions are not required.

Create the server configuration if it does not already exist:

```powershell
if (-not (Test-Path -LiteralPath backend-ai/.env)) { Copy-Item backend-ai/.env.example backend-ai/.env }
notepad backend-ai/.env
```

Enter your own authorized key and save:

```dotenv
JOOLAN_API_KEY=replace_me
JOOLAN_ENSEIGNE=legend73
```

Replace `replace_me` with the actual key. Joolan access needs `api_query` and `api_stock` permissions. Keep the key in **backend-ai/.env**, outside Git and frontend files. The backend reads this file itself; no dotenv installation is needed. An existing process-level `JOOLAN_API_KEY` takes precedence over the file.

No frontend configuration is needed for localhost. If explicitly overriding the API address, create `frontend/.env.local` with:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:4000/api
```

The `/api` suffix is required. Restart the frontend after changing its environment configuration.

## 3. Start the app — every time

**Terminal 1 — from the project root:**

```powershell
cd backend-ai
..\.venv\Scripts\python.exe -B -m uvicorn api_server:app --host 127.0.0.1 --port 4000
```

**Terminal 2 — from the project root:**

```powershell
cd frontend
npm.cmd run dev
```

Open [Setup](http://localhost:3000/setup). Check the backend at [Health](http://127.0.0.1:4000/health) (`status: "ok"`) or [API docs](http://127.0.0.1:4000/docs). Zero recommendations is normal before the first successful forecast.

These startup commands also apply after a reboot; do not reinstall dependencies each time. `Ctrl+C` stops each server. Background export/forecast workers can continue independently: let jobs finish before shutting down the machine or copying its database files. Use one backend process; omit `--reload` and multiple workers during long jobs.

## 4. First use on a clean machine

An empty database has no saved business scope, so the automatic workflow cannot start immediately. Bootstrap once:

1. Open [Manual Setup](http://localhost:3000/setup/manual). Enter the same authorized key in its password field and click **Check connection and discover fields**.
2. Select the four agreed brand codes: **DAYTONA73, D73, IRON AND RESIN, IRON&RESIN**. Select **CENTRAL** for normal supplying inventory. Keep **COMMANDE** as the customer-order type and use today's history end date so all earlier available history is included.
3. Click **Start fresh Joolan export**. Wait for validation, resolve any blockers, then click **Use this validated fresh export**. Completed download pages are retained if a quota or connection issue interrupts the export.
4. Open [Business Scope](http://localhost:3000/scope) and save the four brands. CENTRAL is **Primary supply**, DESTOCK_VD is **End-of-life / clearance**, and DEFECTUEUX is **Faulty**. Classify known customer consignment warehouses separately; do not pool their stock into CENTRAL.
5. Return to [Setup](http://localhost:3000/setup), choose **From month** and **Through month**, and click **Refresh data & forecast**. Choose the current or a future month, for a total of 1–24 months. This performs a new full export, reconciliation, validation and forecasting. The one-time bootstrap export establishes the scope; it does not replace this normal fresh-data workflow.
6. Wait for the job to complete, then open [Dashboard](http://localhost:3000/dashboard). Review source dates and data-quality notices. Catalogue prices, Budget Tracker settings and financial checks remain available separately.

After this initial setup, normally select the forecast months and click **Refresh data & forecast**. Saved scope and manual catalogue prices are retained. Buying budgets and unresolved financial inputs still need review; completing a forecast does not validate a purchase order.

[Seasonal Allocation](http://localhost:3000/allocation) filters the published monthly forecast by article codes such as H26, FW27, P27, CORE and RECONDUIT. These are article labels, not order dates. Missing forecasts remain unknown.

## 5. Move existing saved data instead of starting empty

Git excludes the client databases and exports. To retain catalogue prices, saved seasons, mappings and forecasts:

1. Wait for all jobs to finish. Stop the frontend, backend and any remaining project worker processes on the old machine before copying.
2. Transfer the **entire `backend-ai/data/` folder** securely to the same relative location on the new machine, before starting its backend. Retain SQLite `-wal`/`-shm` sidecars if present; do not copy just a live `.db` file while a process is writing to it.
3. Transfer `backend-ai/output/runs/` as well if you need historical model/forecast audit artifacts. Recreate `.env` separately with authorized credentials. Reinstall dependencies using step 2.
4. Start both servers, verify the saved scope and season, then refresh from Joolan before relying on current stock or forecasts.

`joolan_source.db` contains raw exports and automatic-job state. `joolan_live.db` contains serving results, catalogue prices and saved planning settings. Both are under `backend-ai/data/` by default. An old `FORECASTER_DB_PATH` process environment variable can select a different serving database; clear or deliberately update it on the new machine. Putting it in the Joolan `.env` file does not configure it.

## 6. Quick troubleshooting and checks

- **Backend cannot open the database:** create `backend-ai/data/`, check folder write permissions and any `FORECASTER_DB_PATH` override.
- **No server connection / request failed:** keep both terminals running, check `/health`, use frontend port **3000** and backend **4000**, and verify any API override includes `/api`. If Next.js chooses 3001 because 3000 is occupied, free 3000 and restart; the backend trusts the configured localhost:3000 origins.
- **Server connection is not configured:** check the key in `backend-ai/.env`, the enseigne and overriding process environment variables. Never put the key in a `NEXT_PUBLIC_*` variable.
- **Automatic setup asks for business scope:** finish the one-time Manual Setup export/activation, then save Business Scope.
- **Quota / export paused:** wait for the remote quota reset. Automatic jobs retain pages and retry quota pauses after one hour; use **Retry with server connection** after correcting permissions or configuration. Manual Setup requires key re-entry to resume.
- **No results or HTTP 409:** a clean machine needs an activated fresh export and successful forecast. After changing scope or source, publish matching results. Old CSVs are excluded from this workflow.
- **Price or stock missing:** inspect the source/mappings in Setup and Catalogue. Unknown values are not zero and can prevent financial validation.

Optional checks from the project root:

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
cd backend-ai
..\.venv\Scripts\python.exe -B -m unittest discover -s tests
cd ../frontend
npm.cmd run build
cd ..
```

For faster daily planning, run `npm.cmd run build` once after frontend changes, then `npm.cmd run start` from `frontend` instead of `run dev`; keep the same Python backend running. The start script prepares browser assets and runs the compiled standalone server. Subsequent starts only need `npm.cmd run start`. See [page-loading performance](docs/PERFORMANCE.md). This is a local run procedure, not a hosted production deployment.

Current forecast accuracy still requires a buyer-reviewed pilot; see [engine verification and limitations](docs/FORECAST_ENGINE_UPGRADE_PROGRESS.md). For shared hosting, authentication, HTTPS, backups and deployment configuration are separate work. See [automatic workflow details](docs/AUTOMATIC_FORECAST.md) and [engine contract](docs/FORECAST_ENGINE_V2.md).

On macOS/Linux, use `python3 -m venv .venv`, `.venv/bin/python` from the root (`../.venv/bin/python` inside `backend-ai`), and `npm` instead of `npm.cmd`. Replace the Windows folder-creation/copy/editor commands with their platform equivalents; use the same ports and workflow.
