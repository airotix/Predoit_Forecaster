# Preduit — Deployment Guide

> **Integration notice:** this guide targets the older packaged backend. The merged fresh-Joolan frontend has additional API contracts that the existing Docker image does not yet implement. Use the root [QUICK_START.md](../QUICK_START.md) for the current local app; see [BRANCH_INTEGRATION.md](BRANCH_INTEGRATION.md) before a container rollout.

Covers both supported targets:

- **Local / self-hosted (VM):** Docker Compose — one command brings up the full stack.
- **Production cloud:** Azure Container Apps — same images, pushed to a registry.

Both use the same two container images (`Dockerfile` for the backend, `frontend/Dockerfile`
for the frontend), so what you test locally is what you ship.

---

## 1. Prerequisites

- Docker 24+ and the Docker Compose plugin (`docker compose`).
- For Azure: Azure CLI (`az`), an Azure Container Registry (ACR), and an Entra app
  registration (see `docs/AZURE_DEPLOYMENT_PLAN.md`).
- A source data CSV if you intend to run the forecasting pipeline (otherwise the app serves
  whatever is already in the DB volume).

---

## 2. Local / self-hosted (Docker Compose)

```bash
# from the repo root
cp .env.production.example .env      # then edit .env (see §4)
docker compose up --build
```

- Frontend → http://localhost:3000
- Backend  → http://localhost:4000  (health: http://localhost:4000/health)

Data, the SQLite DB, and pipeline outputs persist on the `preduit-data` volume across
restarts. To load a source CSV, copy it into the volume and point `FORECASTER_DATA_FILE` at
it, or import via the app (ERP Sync / file upload).

Useful commands:

```bash
docker compose logs -f backend         # tail backend logs
docker compose exec backend sh         # shell into the backend
docker compose down                    # stop (keeps the volume)
docker compose down -v                 # stop AND delete data volume
```

> **Dev vs prod:** for a quick local demo you can leave `FORECASTER_AUTH_ENABLED=false`
> (the backend logs a loud SECURITY WARNING). For anything shared, set the auth values in §4.

---

## 3. Production (Azure Container Apps)

Build, tag, and push both images to ACR, then create/patch two Container Apps.

```bash
# 1. Build + push (from repo root)
az acr login --name <registry>
docker build -t <registry>.azurecr.io/preduit-backend:1.0.0 .
docker build -t <registry>.azurecr.io/preduit-frontend:1.0.0 \
  --build-arg NEXT_PUBLIC_API_URL=https://api.your-domain.com/api \
  --build-arg NEXT_PUBLIC_AUTH_ENABLED=true \
  --build-arg NEXT_PUBLIC_AZURE_CLIENT_ID=<spa-client-id> \
  --build-arg NEXT_PUBLIC_AZURE_TENANT_ID=<tenant-id> \
  --build-arg NEXT_PUBLIC_AZURE_API_SCOPE=api://<api-client-id>/access_as_user \
  ./frontend
docker push <registry>.azurecr.io/preduit-backend:1.0.0
docker push <registry>.azurecr.io/preduit-frontend:1.0.0
```

- **Backend** Container App: expose port 4000, mount an Azure Files share at `/data` (so the
  SQLite DB persists), and set the `FORECASTER_*` values from §4 as **secrets** (never plain
  env). Set the ingress allowed origin / `FORECASTER_CORS_ORIGINS` to the frontend URL.
- **Frontend** Container App: expose port 3000. Its `NEXT_PUBLIC_*` values are already baked
  into the image at build time (above), so no runtime secrets are needed there.

See `docs/AZURE_DEPLOYMENT_PLAN.md` for Entra app-role setup, custom domains, and scaling.

> **Note on the frontend build args:** because `NEXT_PUBLIC_*` are compiled into the bundle,
> a change to the API URL or Azure client IDs requires a **rebuild** of the frontend image,
> not just an env change.

---

## 4. Configuration & secrets

Full reference: `.env.example` (all tunables) and `.env.production.example` (prod-safe subset).
The must-set-for-production values:

| Variable | Why |
|---|---|
| `FORECASTER_API_RELOAD=false` | No auto-reload in prod. |
| `FORECASTER_CORS_ORIGINS` | Exact frontend origin(s). |
| `FORECASTER_AUTH_ENABLED=true` + `FORECASTER_AUTH_DEV_BYPASS=false` | Locks the API (otherwise every request is a synthetic admin). |
| `FORECASTER_AZURE_TENANT_ID` / `_CLIENT_ID` / `_API_AUDIENCE` | Entra SSO validation. |
| `FORECASTER_AUTH_SECRET` | Signs local email/password sessions. Use a strong random value. |
| `FORECASTER_DB_PATH=/data/forecast.db` | Persist the DB on the mounted volume. |
| `NEXT_PUBLIC_*` (frontend build args) | Baked into the frontend image at build time. |

**Secret handling:** never commit `.env`; never expose secrets to the browser (only
`NEXT_PUBLIC_*` reach the client, and none of those are secrets). On Azure, store backend
secrets as Container App secrets or in Key Vault. The Joolan API key in particular is sent as
a query parameter — keep it server-side and HTTPS-only.

---

## 5. Health, upgrades, rollback

- **Health:** the backend image has a `HEALTHCHECK` hitting `/health`; Container Apps should
  use the same path for its probe.
- **Upgrade:** build a new image tag, push, and point the Container App / compose at it.
- **Rollback:** redeploy the previous image tag (images are immutable per version).
- **DB migrations:** the persistent tables self-migrate on startup (safe `ADD COLUMN`), and
  pipeline tables are rebuilt on each forecast run — no manual migration step.

---

## 6. Data-path decoupling (note)

The code still defaults data paths to the legacy `backend-ai/` folder when env vars are
unset. In both container targets we override this with `FORECASTER_DB_PATH=/data/forecast.db`
and `FORECASTER_OUTPUT_DIR=/data/output` (and `FORECASTER_DATA_FILE` when running the
pipeline). So containers never depend on the `backend-ai/` layout — the volume is the source
of truth.
