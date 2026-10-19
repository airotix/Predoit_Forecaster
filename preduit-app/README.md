# preduit-app

Install **after** `preduit-engine` (editable installs from repo root are easiest):

```bash
pip install -e ./preduit-engine
pip install -e ./preduit-app
```

Run pipeline:

```bash
python -m preduit_app.main
```

Run API:

```bash
python -m uvicorn preduit_app.api_server:app --reload --host 0.0.0.0 --port 4000
```

Data and SQLite defaults still resolve to `backend-ai/data/` under the repository when using stock `client_config`.
