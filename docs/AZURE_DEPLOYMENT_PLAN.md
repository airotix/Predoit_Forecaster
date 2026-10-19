# Azure Deployment Plan

Deploy the Preduit forecasting system to Azure so clients can access the dashboard via a custom domain.

---

## Architecture Overview

```
Client Browser
     │
     ▼
┌─────────────────────────┐
│  Azure Static Web Apps   │  ← Next.js frontend (globally distributed CDN)
│  (Standard: $9/mo)       │
└────────────┬────────────┘
             │ HTTPS
             ▼
┌─────────────────────────┐
│  Azure Container Apps    │  ← FastAPI backend (preduit-app)
│  (Consumption plan)      │
│  + Mounted Azure Files   │  ← SQLite DB + CSV data
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Azure Blob Storage      │  ← Raw CSV uploads, pipeline outputs, backups
│  (Hot tier, LRS)         │
└─────────────────────────┘

┌─────────────────────────┐
│  Azure Container Apps    │  ← Pipeline job (runs on schedule or on-demand)
│  Job (triggered)         │
└─────────────────────────┘
```

---

## What You Need

| Component | Azure Service | Purpose |
|-----------|---------------|---------|
| Frontend hosting | Azure Static Web Apps (Standard) | Serve Next.js dashboard globally |
| Backend API | Azure Container Apps (Consumption) | Run FastAPI + SQLite |
| Pipeline execution | Azure Container Apps Job | Run m1–m8 on demand or schedule |
| File storage | Azure Blob Storage (Hot, LRS) | Store raw CSVs, outputs, DB backups |
| Persistent volume | Azure Files (Standard) | Mount SQLite DB into container |
| Custom domain + SSL | Included with Static Web Apps | Client-facing URL |
| Container registry | Azure Container Registry (Basic) | Store Docker images |
| Secrets/config | Azure Key Vault (optional) | API keys, DB paths |
| Monitoring | Azure Monitor / Log Analytics | Logs, alerts, performance |

---

## Considerations

### Database Strategy

Currently using SQLite on local disk. For Azure:

- **Option A (Recommended for start):** Keep SQLite on an Azure Files mount. Simple, no migration needed. Works well for single-instance API with <50 concurrent users.
- **Option B (Scale later):** Migrate to Azure Database for PostgreSQL Flexible Server if you need multi-instance API scaling, concurrent writes, or >100 users.

### Multi-Tenancy

If serving multiple clients:

- **Separate deployments:** Each client gets their own Container App + DB. Simpler isolation but more management.
- **Shared deployment:** Single API with per-client databases (SQLite per client on Azure Files). Lower cost, more complex code.

### Security

- **Azure Entra ID authentication** is implemented in FastAPI + Next.js (see [Authentication](#authentication) below)
- Use Azure Key Vault for environment secrets (`FORECASTER_AZURE_*`, API keys)
- Enable HTTPS everywhere (free with Static Web Apps + Container Apps)
- Set up CORS to only allow your frontend domain
- Consider Azure Front Door if clients need geo-distributed access

---

## Authentication

Preduit uses **Azure Entra ID (OIDC)** with three app roles. Enterprise customers can federate their corporate IdP (SAML or OIDC) **into Entra**; the API only validates Entra-issued JWTs.

### App registration

1. In Azure Portal → **Microsoft Entra ID** → **App registrations** → **New registration**
   - Name: `Preduit`
   - Supported account types: single tenant (or multi-tenant for B2B)
   - Redirect URI (SPA): `http://localhost:3000` and production Static Web App URL

2. **Expose an API**
   - Application ID URI: `api://<client-id>` (or custom `api://preduit`)
   - Add scope: `access_as_user` (admin consent)

3. **App roles** (Application type, assign to users/groups):

| App role value | Display name | Product access |
|----------------|--------------|----------------|
| `Preduit.User` | User | Read-only: Dashboard, Products, Projections |
| `Preduit.Manager` | Manager | Read all pages; overrides, export, season config; **no** forecast refresh / ingest |
| `Preduit.Admin` | Admin | Full access including forecast refresh, ingest, backtest |

4. **Frontend platform**: add SPA redirect URIs; enable **Authorization Code Flow with PKCE**

5. Assign users to exactly one role under **Enterprise applications** → your app → **Users and groups**

### Environment variables

**Backend (Container App / `.env`):**

| Variable | Example | Purpose |
|----------|---------|---------|
| `FORECASTER_AUTH_ENABLED` | `true` | Enable JWT validation |
| `FORECASTER_AUTH_DEV_BYPASS` | `false` | Must be `false` in production |
| `FORECASTER_AUTH_DEV_ROLE` | `admin` | Dev-only role when bypass is on |
| `FORECASTER_AZURE_TENANT_ID` | `{tenant-guid}` | Entra tenant |
| `FORECASTER_AZURE_CLIENT_ID` | `{app-client-id}` | App registration client ID |
| `FORECASTER_AZURE_API_AUDIENCE` | `api://{client-id}` | Token audience |

**Frontend (Static Web App):**

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_AUTH_ENABLED` | `true` to enable MSAL login |
| `NEXT_PUBLIC_AZURE_CLIENT_ID` | SPA client ID |
| `NEXT_PUBLIC_AZURE_TENANT_ID` | Tenant ID |
| `NEXT_PUBLIC_AZURE_API_SCOPE` | `api://{client-id}/access_as_user` |

### Enterprise SSO (SAML)

For B2B procurement requirements:

1. Customer configures **SAML federation** or **OIDC federation** in their Entra tenant (or yours via B2B guest / External ID)
2. User signs in through corporate IdP → Entra issues access token with `Preduit.*` app role
3. Preduit API validates JWT via Entra JWKS — no SAML parsing in application code

Document per-customer federation steps in client onboarding checklist.

### Data Handling

- Raw CSV uploads go to Blob Storage (hot tier)
- Pipeline reads from Blob, writes SQLite to Azure Files
- API reads SQLite from the mounted volume
- Daily backups of SQLite to Blob Storage (cool tier)

### Pipeline Scheduling

- Use Container Apps Jobs with a CRON trigger for scheduled re-forecasts
- Or trigger via API endpoint (`POST /api/forecast/refresh`) for on-demand runs
- Pipeline needs ~4 GB RAM for CatBoost training on large datasets

---

## Cost Breakdown (Per Client, Monthly)

Estimated for a single client deployment with moderate usage (~5 users, ~10K requests/day).

| Service | Tier/Config | Monthly Cost |
|---------|-------------|--------------|
| **Static Web Apps** | Standard (1 app) | $9.00 |
| **Container Apps — API** | Consumption (0.5 vCPU, 1 GB RAM, always-on 1 replica) | ~$15.00 |
| **Container Apps — Pipeline Job** | Consumption (2 vCPU, 4 GB RAM, runs 10 min/day) | ~$2.00 |
| **Azure Files** | Standard, LRS (1 GB for SQLite) | ~$0.06 |
| **Blob Storage** | Hot, LRS (5 GB: CSVs + outputs) | ~$0.10 |
| **Container Registry** | Basic (1 registry, shared across clients) | $5.00 |
| **Custom Domain** | Included with Static Web Apps | $0.00 |
| **SSL Certificate** | Included (auto-managed) | $0.00 |
| **Log Analytics** | Free tier (5 GB/month ingestion) | $0.00 |
| **Azure DNS** | 1 hosted zone + queries | ~$0.50 |
| **Egress (data transfer)** | ~20 GB/month outbound | ~$1.70 |

### Total Per Client: ~$33/month

| Scenario | Estimated Monthly Cost |
|----------|----------------------|
| 1 client (light usage) | ~$33 |
| 1 client (heavy, 50 users) | ~$50 |
| 5 clients (shared registry + DNS) | ~$150 |
| 10 clients (shared infra) | ~$280 |

> Costs decrease per-client as you share Container Registry, DNS zone, and Log Analytics workspace across clients.

---

## Step-by-Step Deployment

### Step 1: Prerequisites

1. Create an Azure account (or use existing)
2. Install Azure CLI: `winget install Microsoft.AzureCLI`
3. Install Docker Desktop (for building container images)
4. Login: `az login`

### Step 2: Create Resource Group

```bash
az group create --name rg-preduit-prod --location westeurope
```

Pick a region close to your clients (westeurope, eastus, etc).

### Step 3: Create Azure Container Registry

```bash
az acr create \
  --resource-group rg-preduit-prod \
  --name preduitregistry \
  --sku Basic \
  --admin-enabled true
```

### Step 4: Create Dockerfile for Backend

Create `Dockerfile` at repo root:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY preduit-engine/ ./preduit-engine/
COPY preduit-app/ ./preduit-app/
COPY requirements-preduit.txt .
COPY backend-ai/data/raw/ ./backend-ai/data/raw/

RUN pip install --no-cache-dir -r requirements-preduit.txt

ENV FORECASTER_API_HOST=0.0.0.0
ENV FORECASTER_API_PORT=4000
ENV FORECASTER_DB_PATH=/data/forecast.db
ENV FORECASTER_DATA_FILE=/app/backend-ai/data/raw/THE_FINAL_10Y_cleaned.csv

EXPOSE 4000

CMD ["uvicorn", "preduit_app.api_server:app", "--host", "0.0.0.0", "--port", "4000"]
```

### Step 5: Build and Push Image

```bash
az acr login --name preduitregistry

docker build -t preduitregistry.azurecr.io/preduit-api:latest .
docker push preduitregistry.azurecr.io/preduit-api:latest
```

### Step 6: Create Azure Files Share (for SQLite DB)

```bash
az storage account create \
  --name preduitdata \
  --resource-group rg-preduit-prod \
  --location westeurope \
  --sku Standard_LRS

az storage share create \
  --name preduit-db \
  --account-name preduitdata \
  --quota 5
```

### Step 7: Create Container Apps Environment

```bash
az containerapp env create \
  --name preduit-env \
  --resource-group rg-preduit-prod \
  --location westeurope

# Add the Azure Files storage
az containerapp env storage set \
  --name preduit-env \
  --resource-group rg-preduit-prod \
  --storage-name preduit-dbstorage \
  --azure-file-account-name preduitdata \
  --azure-file-share-name preduit-db \
  --azure-file-account-key <YOUR_STORAGE_KEY> \
  --access-mode ReadWrite
```

### Step 8: Deploy the API Container App

```bash
az containerapp create \
  --name preduit-api \
  --resource-group rg-preduit-prod \
  --environment preduit-env \
  --image preduitregistry.azurecr.io/preduit-api:latest \
  --registry-server preduitregistry.azurecr.io \
  --registry-username preduitregistry \
  --registry-password <ACR_PASSWORD> \
  --target-port 4000 \
  --ingress external \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars \
    FORECASTER_DB_PATH=/data/forecast.db \
    FORECASTER_API_HOST=0.0.0.0 \
    FORECASTER_API_PORT=4000 \
    FORECASTER_CORS_ORIGINS=https://your-client-domain.com
```

Mount the Azure Files volume (via YAML or portal after creation).

### Step 9: Run Pipeline Job (Initial DB Population)

```bash
az containerapp job create \
  --name preduit-pipeline \
  --resource-group rg-preduit-prod \
  --environment preduit-env \
  --image preduitregistry.azurecr.io/preduit-api:latest \
  --registry-server preduitregistry.azurecr.io \
  --registry-username preduitregistry \
  --registry-password <ACR_PASSWORD> \
  --cpu 2 \
  --memory 4Gi \
  --trigger-type Manual \
  --replica-timeout 3600 \
  --env-vars \
    FORECASTER_DB_PATH=/data/forecast.db \
    FORECASTER_DATA_FILE=/app/backend-ai/data/raw/THE_FINAL_10Y_cleaned.csv \
  --command "python" "-m" "preduit_app.main"
```

Run it:

```bash
az containerapp job start --name preduit-pipeline --resource-group rg-preduit-prod
```

### Step 10: Deploy Frontend to Static Web Apps

```bash
cd frontend
npm run build
```

Create the Static Web App:

```bash
az staticwebapp create \
  --name preduit-dashboard \
  --resource-group rg-preduit-prod \
  --location westeurope \
  --sku Standard
```

Deploy via GitHub Actions (recommended) or Azure CLI:

```bash
az staticwebapp deploy \
  --name preduit-dashboard \
  --resource-group rg-preduit-prod \
  --app-location ./frontend \
  --output-location .next
```

Set the API URL environment variable in the Static Web App settings:

```
NEXT_PUBLIC_API_URL=https://preduit-api.<region>.azurecontainerapps.io/api
```

### Step 11: Configure Custom Domain

```bash
# Add custom domain to Static Web App
az staticwebapp hostname set \
  --name preduit-dashboard \
  --hostname app.yourclient.com

# Add custom domain to Container App (API)
az containerapp hostname add \
  --name preduit-api \
  --resource-group rg-preduit-prod \
  --hostname api.yourclient.com
```

Update DNS with your domain registrar (CNAME records).

### Step 12: Set Up Scheduled Pipeline Runs (Optional)

For daily re-forecasting, update the job trigger:

```bash
az containerapp job create \
  --name preduit-pipeline-scheduled \
  --resource-group rg-preduit-prod \
  --environment preduit-env \
  --image preduitregistry.azurecr.io/preduit-api:latest \
  --trigger-type Schedule \
  --cron-expression "0 2 * * *" \
  --cpu 2 \
  --memory 4Gi \
  --command "python" "-m" "preduit_app.main"
```

This runs the pipeline every day at 2 AM.

---

## Post-Deployment Checklist

- [ ] Verify frontend loads at custom domain
- [ ] Verify API responds at `/health`
- [ ] Run pipeline job and confirm DB population
- [ ] Test all dashboard pages with real data
- [ ] Set up Azure Monitor alerts (CPU > 80%, errors > 0)
- [ ] Enable daily SQLite backup to Blob Storage
- [ ] Configure CORS to only allow the client's domain
- [ ] Set up CI/CD pipeline (GitHub Actions or Azure DevOps)
- [ ] Document client onboarding process for additional clients

---

## Scaling Notes

| When you need to... | Action |
|---------------------|--------|
| Serve more concurrent users | Increase Container App `max-replicas` |
| Serve multiple clients | Deploy separate Container Apps per client or add multi-tenancy |
| Handle concurrent DB writes | Migrate from SQLite to PostgreSQL Flexible Server (~$13/mo for B1ms) |
| Reduce latency globally | Add Azure Front Door ($35/mo) |
| Add authentication | Integrate Azure Entra ID or add JWT auth to FastAPI |
| Run forecast accuracy backtest | `POST /api/forecast/backtest` (admin); results on Validation page via `GET /api/forecast/accuracy` |

### Backtest operations

- Trigger walk-forward backtest from **Season Setup** (admin) or `POST /api/forecast/backtest?holdoutMonths=6`
- Results persist in SQLite tables `backtest_runs`, `backtest_fold_metrics`, `backtest_breakdown`
- Metrics: **WMAPE**, **bias** (% over/under-forecast), **80% interval coverage** (conservative–optimistic band)
- CPU-intensive — runs as background job; tune `FORECASTER_BACKTEST_HOLDOUT_MONTHS` and optional `FORECASTER_BACKTEST_MAX_SKUS` for dev

---

## Cost Summary

| | Minimum (1 client) | Comfortable (1 client) | Multi-client (5) |
|--|---------------------|------------------------|-------------------|
| Compute | $17 | $25 | $100 |
| Storage | $1 | $2 | $8 |
| Networking | $2 | $5 | $15 |
| Frontend | $9 | $9 | $45 |
| Registry + misc | $6 | $6 | $6 |
| **Total** | **~$35/mo** | **~$47/mo** | **~$174/mo** |

> All prices are pay-as-you-go estimates (USD). Actual costs vary by region and usage. Use the [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/) for exact numbers.
