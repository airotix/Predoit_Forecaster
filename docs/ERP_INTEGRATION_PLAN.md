# Phase 3 — ERP Integration Plan (Joolan / Lisa API)

**ERP:** Joolan "Lisa" — third-party retail/B2B management software.
**API base:** `https://lisa.joolan.com/api/v2` (spec: `swagger.yaml`, OpenAPI 3.0, v2.0.0).
**Status:** Design/plan — not yet implemented. Awaiting credentials + a schema/data sample.

The goal: replace the mock ERP ingestion (`ingestion.py:load_mock_erp_dataframe`,
`/api/ingest/erp`) with a real Joolan connector that feeds the forecasting pipeline, and
use the same connector to fetch **real per-unit cost** (closing the Phase 2 cost placeholder).
CSV/XLSX upload is kept as a fallback.

---

## 1. How Joolan authentication works

Every request needs two query parameters:

- `enseigne` — the client's database/store name.
- `api-key` — an API key whose permissions are per-endpoint (column `api_<permission>`).

So calls look like:
`GET https://lisa.joolan.com/api/v2/<endpoint>.do?enseigne=<name>&api-key=<key>&...`

Permissions we will need enabled on the key: **`api_query`** (SQL read), **`api_stock`**
(stock image), and **`api_catalogue`** (product catalogue). `api_query` alone can cover
almost everything, but the purpose-built endpoints are simpler and safer.

> Security note: Joolan passes the key as a **query string** parameter. We must only ever
> call over HTTPS, keep the key in server-side env/secrets, and never log full request URLs
> or expose the key to the browser.

---

## 2. What the forecaster needs vs. what Joolan offers

The pipeline (`m1_data_preparation`) consumes a wide, line-level history table (~49 columns:
Client + product attributes + ordered/delivered/backorder quantities + price + stock +
supplier pipeline) and computes the core signal **`true_demand = LIV_qte + RELIQUAT_qte`**.

| Forecaster need | Joolan source (recommended) | Notes |
|---|---|---|
| **Historical sales / orders** (line level, per client, with qty ordered/delivered/backordered, price, date) | **`/query.do`** (read-only SQL) over the sales/B2B pieces tables; or **`/export-tickets.do`** per day | `query.do` is the best fit — one query can return exactly the pipeline's column schema. `export-tickets.do` is per-day (loop dates) and retail-oriented. |
| **Per-unit cost** (`Prix_Achat`) — for Phase 2 real cost | **`/query.do`** `SELECT Produit,Couleur,Taille,Prix_Achat …` | Cost is **not** exposed by `catalogue-web.do` (which only has `Prix_Vente`). `query.do` is the only read path to purchase cost. |
| **Product master** (Famille, Rayon, Marque, Saison, Matiere, Modele, Fournisseur, EAN, Prix_Vente) | **`/catalogue-web.do`** (`output-format=json`, incremental via `last-call`) or `query.do` | Enriches SKUs; `catalogue-web` supports incremental sync on `Last_Change`. |
| **Current stock** (`STOCK`, available inventory) | **`/image-full-stocks.do`** | Returns `En_Stock`, `Disponible`, `En_Reservation`, and — usefully — `Reliquat_Fournisseur` / `En_Livraison` (incoming supplier qty). |
| **Supplier pipeline** (`CDE_four*` incoming POs) | `image-full-stocks.do` (`Reliquat_Fournisseur`, `En_Livraison`) + `/query.do` on supplier orders | Feeds `pipeline_stock`. |
| **Clients** (name, family, city, country, sector) | **`/recherche-clients.do`** or `query.do` | For client KPIs / coverage. |

**Recommendation:** make **`/query.do`** the primary connector (it can reproduce the exact
pipeline schema in one or two queries, including cost), with **`/image-full-stocks.do`** for
the live stock snapshot and **`/catalogue-web.do`** for incremental product-master refresh.
Fall back to `/export-tickets.do` day-by-day only if `api_query` can't be granted.

---

## 3. Endpoints we will use

1. `POST /query.do` — body is a raw `SELECT`; returns `{result, data:[…]}`. **Primary** source
   for history + cost. Finalise the exact SQL once we have Joolan's table schema / a sample.
2. `GET /image-full-stocks.do` — full stock image (all SKUs × stores, incl. zeros). Live stock
   + incoming supplier qty.
3. `GET /catalogue-web.do?output-format=json&last-call=<ts>` — incremental product master.
4. `POST /recherche-clients.do` — client records (optional if `query.do` covers it).
5. *(fallback)* `GET /export-tickets.do?Date=YYYY-MM-DD` — daily sales, looped over the history
   window.

---

## 4. How we connect it (our side)

**New module `preduit_engine/erp_joolan.py`** — the real client that replaces
`load_mock_erp_dataframe()`:

- `JoolanClient(base_url, enseigne, api_key, magasins)` with `_get(endpoint, params)` /
  `_post(endpoint, body)` using `httpx` (already a dependency), retries + timeout, and a
  guard that never logs the key.
- `fetch_sales_history(since=None) -> DataFrame` — via `query.do`; normalises Joolan column
  names to the pipeline's expected French schema (`Référence`, `Couleur`, `Taille`, `Client`,
  `LIV_qte`, `RELIQUAT_qte`, `Prix`, `Saison`, …) so `m1` ingests it unchanged.
- `fetch_costs() -> DataFrame` — `query.do` `Produit,Couleur,Taille,Prix_Achat`.
- `fetch_stock() -> DataFrame` — `image-full-stocks.do` → `STOCK`, available, incoming.
- `fetch_catalogue(last_call=None)` / `fetch_clients()` as needed.

**Wire into the existing ingestion path** (minimal disruption):

- `ingestion.py`: replace the mock with `erp_joolan.fetch_*`, then reuse the existing
  `dedupe_and_upsert` + `bump_import_metadata` + job tracking so the rest of the pipeline and
  the `/api/ingest/status` flow are unchanged.
- `/api/ingest/erp` (currently mock, admin-gated): call the real client; on success trigger
  (or offer to trigger) `/api/forecast/refresh`.
- Keep `/api/ingest/file` (CSV/XLSX upload) as the **fallback** import path.

**Cost → Phase 2:** feed `fetch_costs()` into `m1`/`m3`/`m7` so `estimated_cost_*` uses **real
`Prix_Achat`** when present; the configurable cost ratio remains the fallback when a SKU has no
cost. This closes the "per-item cost" gap left open in Phase 2 and makes the Season Setup cost
ratio a true fallback rather than the primary source.

**Config (new env vars, server-side only):**
```
FORECASTER_ERP_ENABLED=true
FORECASTER_ERP_BASE_URL=https://lisa.joolan.com/api/v2
FORECASTER_ERP_ENSEIGNE=<enseigne>
FORECASTER_ERP_API_KEY=<key>          # secret — Key Vault / env, never client-side
FORECASTER_ERP_MAGASINS=              # optional store filter, ';'-separated
FORECASTER_ERP_HISTORY_MONTHS=120     # how much history to pull
```

**Scheduling (optional):** a nightly scheduled task calling `/api/ingest/erp` then a forecast
refresh, so data stays current without manual imports.

---

## 5. Sequence

```
[scheduler or Setup page "ERP Sync"]
        │
        ▼
/api/ingest/erp ──► erp_joolan.fetch_sales_history()   (query.do)
                    erp_joolan.fetch_costs()            (query.do)
                    erp_joolan.fetch_stock()            (image-full-stocks.do)
        │
        ▼
 normalise → dedupe_and_upsert → data CSV / DB   (existing)
        │
        ▼
/api/forecast/refresh ──► m1…m8 pipeline ──► SQLite ──► dashboard
```

---

## 6. Open questions / inputs needed before building

1. **Credentials:** `enseigne` value and an `api-key` with `api_query`, `api_stock`,
   `api_catalogue` permissions (a sandbox/test enseigne if possible).
2. **History source:** is the demand history in **B2B pieces** (négoce: commandes/BL/factures)
   or **retail tickets**? This determines the `query.do` SQL (which tables) — a few sample rows
   or the table/column list for sales lines, products, and clients would let me finalise it.
3. **Cost definition:** confirm `Prix_Achat` (purchase price) is the cost basis you want for
   margins, and whether it's net of `Remise_Achat`.
4. **Store scope:** all stores or a subset (`Magasins`)?
5. **Sync cadence:** manual (button) only, or nightly automatic?

---

## 6b. Built now (dormant until credentials)

Implemented so the connection is ready to switch on with **zero code changes** — just env vars:

- [x] `preduit_engine/erp_joolan.py` — `JoolanClient` (httpx) with `test_connection`,
  `run_sql`, `fetch_sales_history(history_sql)`, `fetch_costs(cost_sql)`, `fetch_stock`,
  `fetch_catalogue`. Never logs the API key. No app-layer import (clean layering).
- [x] Config in `client_config.py`: `ERP_ENABLED`, `ERP_BASE_URL`, `ERP_ENSEIGNE`,
  `ERP_API_KEY`, `ERP_MAGASINS`, `ERP_HISTORY_SQL`, `ERP_COST_SQL`, + `erp_is_configured()`.
- [x] `/api/ingest/erp` uses the real connector when configured, else **falls back to the
  bundled sample data** (response `mode` = `erp` | `sample`). Manual button, unchanged flow.
- [x] `GET /api/ingest/erp/status` — tells the Setup page whether the ERP is connected.
- [x] Setup page: connection banner ("Connected to Joolan …" vs "not configured — sample
  data / upload fallback") and the sync result shows which mode ran.
- [x] `.env.example` ERP section documenting all the vars and the security caveat.

**The SQL is configuration, not code:** because we don't know Joolan's table/column names
yet, `FORECASTER_ERP_HISTORY_SQL` / `FORECASTER_ERP_COST_SQL` hold the queries. Set them
(aliasing columns to the pipeline's names) once we have schema + credentials, and the button
starts pulling live data. No redeploy of code required.

### To switch on later
1. Set `FORECASTER_ERP_ENABLED=true`, `FORECASTER_ERP_ENSEIGNE`, `FORECASTER_ERP_API_KEY`.
2. Write `FORECASTER_ERP_HISTORY_SQL` (and optionally `FORECASTER_ERP_COST_SQL`) using
   Joolan's real schema, aliasing output columns to the pipeline names.
3. Click "ERP Sync" (or schedule it). Confirm rows import, then run a forecast refresh.

## 7. Deliverables still remaining

- [ ] `preduit_engine/erp_joolan.py` client + normalisers, with unit tests against recorded
  sample responses.
- [ ] Real `/api/ingest/erp` wired to it; CSV upload kept as fallback.
- [ ] Real cost fed into `m1`/`m3`/`m7`; Season Setup cost ratio becomes the fallback.
- [ ] New ERP env vars documented in `.env.example`; key handled as a secret.
- [ ] Optional nightly sync scheduled task.
- [ ] Setup page: "ERP Sync" relabelled to reflect the real connection (and disabled when
  `FORECASTER_ERP_ENABLED=false`).
