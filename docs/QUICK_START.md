# Quick Start

Get the forecasting pipeline and dashboard running locally.

---

## Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm (for the frontend)

---

## 1. Install Python Packages

From the repository root:

```bash
pip install -r requirements-preduit.txt
```

This installs both packages in editable mode:
- `preduit-engine` — ML pipeline library
- `preduit-app` — FastAPI service + client config

Alternatively, install them individually:

```bash
pip install -e ./preduit-engine
pip install -e ./preduit-app
```

---

## 2. Place Your Data File

The pipeline expects a CSV at:

```
backend-ai/data/raw/THE_FINAL_10Y_cleaned.csv
```

Override this path by setting `FORECASTER_DATA_FILE` in a `.env` file at the repo root.

---

## 3. Run the Forecasting Pipeline

```bash
python -m preduit_app.main
```

Or specify a custom data file:

```bash
python -m preduit_app.main --data path/to/your/file.csv
```

This runs modules m1 through m8 in sequence, exports CSV/Excel to `output/`, and populates the SQLite database at `backend-ai/data/forecast.db`.

---

## 4. Verify the Database

```bash
python -m preduit_app.test_db
```

Prints table row counts, query timings, and index verification.

---

## 5. Start the API Server

```bash
python -m uvicorn preduit_app.api_server:app --reload --host 0.0.0.0 --port 4000
```

The API will be available at `http://localhost:4000`. Key endpoints:

- `GET /health` — status check
- `GET /api/articles?season=...` — filtered forecast data
- `GET /api/filter-options?season=...` — dropdown values
- `GET /api/customers` — customer list
- `GET /api/customer-detail?customer=...` — customer order details

---

## 6. Start the Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:3000`. The frontend calls the API at `http://localhost:4000/api` by default.

To point it at a different backend, create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://your-host:4000/api
```

---

## Typical Workflow

```
Terminal 1 (API):     python -m uvicorn preduit_app.api_server:app --reload --port 4000
Terminal 2 (Frontend): cd frontend && npm run dev
```

After data changes, re-run the pipeline:

```bash
python -m preduit_app.main
```

The API reads directly from SQLite — no restart needed after a pipeline run.

---

## Environment Variables

Create a `.env` file at the repository root to override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `FORECASTER_DATA_FILE` | `backend-ai/data/raw/THE_FINAL_10Y_cleaned.csv` | Input CSV |
| `FORECASTER_DB_PATH` | `backend-ai/data/forecast.db` | SQLite DB location |
| `FORECASTER_API_PORT` | `4000` | API port |
| `FORECASTER_CORS_ORIGINS` | `http://localhost:3000` | Allowed origins |
| `FORECASTER_OUTPUT_DIR` | `output/` | CSV export directory |
| `FORECASTER_FORECAST_HORIZON_MONTHS` | `6` | Forecast horizon |
| `FORECASTER_DEFAULT_COST_RATIO` | `0.50` | Cost/price ratio |

---

## Troubleshooting

- **Frontend shows no data** — Make sure the API server is running on port 4000 and the database has been populated (`python -m preduit_app.main`).
- **Pipeline fails with "file not found"** — Verify your CSV is at the expected path or set `FORECASTER_DATA_FILE`.
- **Import errors** — Re-install packages: `pip install -e ./preduit-engine && pip install -e ./preduit-app`
- **Port conflict** — Change `FORECASTER_API_PORT` in `.env` and update `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to match.
