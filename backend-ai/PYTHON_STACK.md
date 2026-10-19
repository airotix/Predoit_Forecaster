# Python stack location

The ML pipeline and FastAPI service were split into installable packages:

| Package | Path | Import name |
|---------|------|-------------|
| **preduit-engine** | `../preduit-engine/` | `preduit_engine` |
| **preduit-app** | `../preduit-app/` | `preduit_app` |

Install from the repository root:

```bash
pip install -r requirements-preduit.txt
```

Run the pipeline:

```bash
python -m preduit_app.main
```

Run the API:

```bash
python -m uvicorn preduit_app.api_server:app --reload --host 0.0.0.0 --port 4000
```

Paths to CSV data and `forecast.db` default to **`backend-ai/data/`** via `preduit_app.client_config` (`LEGACY_BACKEND_DIR`).
