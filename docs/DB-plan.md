You are working on a B2B wholesale forecasting system.

The project structure:
  backend-ai/          ← Python forecasting pipeline + FastAPI server
  frontend/            ← Next.js 14 dashboard
  .venv/               ← Python virtual environment

Current data flow:
  1. main.py runs pipeline modules m1 through m8
  2. m8_output.py writes CSV files to backend-ai/output/
  3. api_server.py reads those CSVs, caches them, serves JSON to frontend
  4. Frontend calls /api/articles, /api/filter-options, /api/customers, /api/customer-detail

Problem: Frontend is slow because api_server.py reads and filters large CSVs on every request.

Solution: Add SQLite database as serving layer. Pipeline populates DB after generating CSVs. api_server.py reads from DB instead of CSVs.

CRITICAL CONSTRAINTS:
- Do NOT change any frontend code. The API response shapes must stay IDENTICAL.
- Do NOT change the pipeline modules m1 through m7. Only m8 and main.py get small additions.
- CSVs are still generated (backup/export). DB is the new primary serving layer.
- The existing api_server.py endpoints and their response shapes are the CONTRACT. Match them exactly.
- Use SQLite (no external database server needed).
- All files go in backend-ai/ directory.

STEP 1:

Create a new file backend-ai/database.py

This module handles:
1. SQLite connection management with performance pragmas
2. Schema creation (all tables)
3. Index creation
4. Populating all tables from pipeline results

DATABASE FILE LOCATION: backend-ai/data/forecast.db

TABLES NEEDED (with exact columns):

TABLE: recommendations
- This is the MAIN table. It contains one row per reference × couleur × taille.
- Columns must include everything the /api/articles endpoint needs:
  - Product identity: reference, couleur, taille
  - Product metadata: designation, rayon, famille, theme, modele, matiere, fournisseur, saison, critere, season_type, product_status
  - Model info: model_type, confidence, span_months
  - Forecasts: forecast_conservative, forecast_base, forecast_optimistic
  - Current situation: confirmed_orders, confirmed_delivered, confirmed_clients, current_stock, pipeline_stock, available_inventory
  - Net to order: net_to_order_conservative, net_to_order_base, net_to_order_optimistic, probable_additional_base
  - KPIs: diffusion_rate, total_buying_clients, depth_per_client, reorder_rate, fill_rate, backorder_rate, size_share, size_had_stockout, total_true_demand
  - Financial: avg_price, expected_revenue_conservative, expected_revenue_base, expected_revenue_optimistic, estimated_cost_conservative, estimated_cost_base, estimated_cost_optimistic, estimated_margin_base, margin_rate_base
  - Explanation: explanation
  - UNIQUE constraint on (reference, couleur, taille)

TABLE: forecast_monthly
- For demand trend charts. One row per reference × couleur × taille × forecast_month.
- Columns: reference, couleur, taille, forecast_month (TEXT), forecast_conservative, forecast_base, forecast_optimistic, model_type

TABLE: historical_demand
- Size-level historical. One row per reference × couleur × taille × year_month.
- Columns: reference, couleur, taille, year_month (TEXT), true_demand, cde_qte, liv_qte, reliquat_qte, ann_qte, num_clients, prix

TABLE: historical_sku_color
- Aggregated without size (for trend charts). One row per reference × couleur × year_month.
- Columns: reference, couleur, year_month (TEXT), true_demand, num_clients, prix

TABLE: client_orders
- Client-level order data for /api/customers and /api/customer-detail.
- Aggregated at client × reference × couleur × critere grain.
- Columns: client_id, client_name, reference, couleur, taille, critere, season_type, season_year, date_commande, cde_qte, liv_qte, true_demand, prix, cde_net_ht

TABLE: clients
- Client summary. One row per client.
- Columns: client_id (PK), client_name, famille_client, cp, ville, pays, secteur, total_units, total_spend, num_skus, active_months, first_order, last_order

TABLE: filter_options
- Pre-computed filter dropdown values PER critere (season).
- The frontend calls /api/filter-options?season=Hiver(2023) and expects lists of suppliers, families, themes, models, customers available for that season.
- Columns: filter_type (supplier/family/theme/model/customer/season), filter_value, critere, item_count

TABLE: pipeline_metadata
- Key-value store for pipeline run info.
- Columns: key (PK), value, updated_at

INDEXES needed on recommendations:
- reference, couleur, (reference + couleur), critere, season_type, famille, fournisseur, theme, modele, matiere, confidence, model_type, net_to_order_base DESC, forecast_base DESC

INDEXES on other tables:
- forecast_monthly: (reference, couleur), forecast_month
- historical_demand: (reference, couleur), (reference, couleur, taille), year_month
- historical_sku_color: (reference, couleur)
- client_orders: client_id, (reference, couleur), critere, client_name
- filter_options: filter_type, (filter_type, critere)

POPULATION FUNCTION: populate_database(pipeline_results)
- Takes the same results dict that main.py produces
- pipeline_results contains: data, profiles, kpis, sarima_output, catboost_output, size_output, recommendations
- Drops all tables, recreates schema, inserts all data, creates indexes, runs ANALYZE and VACUUM
- For recommendations table: merge product metadata from results["data"]["raw"] since the recommendations DataFrame may not have all columns (like Designation, Rayon, etc.)
- For client_orders: aggregate from results["data"]["raw"] grouped by Client, Nom, Reference, Couleur, Critere, season_type, season_year
- For filter_options: iterate over each unique Critere value in raw data, and for each, collect unique Fournisseur, Famille, Theme, Modele, Client values. For customers, use client Nom (name) as the filter_value, not client ID.
- For historical tables: use results["data"]["monthly_sku_color_size"] and results["data"]["monthly_sku_color"]
- Insert in chunks of 10000 for large tables
- Print progress and final DB size

HELPER FUNCTIONS:
- get_connection(db_path=None) → returns sqlite3 connection with WAL mode, 64MB cache, memory temp store
- _safe_val(val, target_type) → safely converts to int/float/str handling NaN/None

Connection settings:
  PRAGMA journal_mode=WAL
  PRAGMA synchronous=NORMAL
  PRAGMA cache_size=-64000
  PRAGMA temp_store=MEMORY
  PRAGMA mmap_size=268435456


STEP 2:

Replace the entire backend-ai/api_server.py file.

The new version must:
1. Use FastAPI (same as current)
2. Read from SQLite database (backend-ai/data/forecast.db) instead of CSV files
3. Serve the EXACT SAME endpoint paths and response shapes as the current version

The current api_server.py serves these endpoints:
- GET /health
- GET /api/articles
- GET /api/filter-options
- GET /api/customers
- GET /api/customer-detail

Here is exactly what each endpoint must return:

═══════════════════════════════════════
ENDPOINT: GET /health
═══════════════════════════════════════
Response: {"status": "ok", "recommendations_count": <int>}
Implementation: Query SELECT COUNT(*) FROM recommendations

═══════════════════════════════════════
ENDPOINT: GET /api/articles
═══════════════════════════════════════
Query parameters (all optional):
- season: string (e.g. "Hiver(2023)") → filters by recommendations.critere
- supplier: string → filters by recommendations.fournisseur
- family: string → filters by recommendations.famille
- theme: string → filters by recommendations.theme
- model: string → filters by recommendations.modele
- customer: string → filters by recommendations where reference is in client_orders for that customer name
- searchQuery: string → filters by reference LIKE or couleur LIKE or designation LIKE

Response: Array of ArticleData objects. Each ArticleData represents ONE reference (grouped across all its colors and sizes).

ArticleData shape:
{
  "id": "<reference>",
  "supplier": "<fournisseur>",
  "customer": "",
  "family": "<famille>",
  "theme": "<theme>",
  "model": "<modele>",
  "season": "<critere>",
  "price": <float>,
  "cost": <float>,
  "matrix": {
    "<color1>": {
      "<size1>": {"forecast": <int>, "stock": <int>, "orders": <int>, "forecastConservative": <int>, "forecastOptimistic": <int>, "netToOrder": <int>},
      "<size2>": {...},
      ...
    },
    "<color2>": {...},
    ...
  },
  "sizes": ["<size1>", "<size2>", ...],  // sorted in natural size order
  "colors": ["<color1>", "<color2>", ...],  // sorted alphabetically
  "demandTrend": [
    {"month": "<year_month>", "demand": <int>, "type": "historical"},
    {"month": "<year_month>", "demand": <int>, "type": "forecast"},
    ...
  ],
  "totalForecast": <int>,
  "totalStock": <int>,
  "totalOrders": <int>,
  "totalNetToOrder": <int>,
  "confidence": "<HIGH|MEDIUM|MEDIUM-LOW|LOW>",
  "modelType": "<SARIMA|SARIMA_S|SARIMA_M|CATBOOST>",
  "diffusionRate": <float>,
  "buyingClients": <int>,
  "depthPerClient": <float>,
  "reorderRate": <float>
}

Building the response:
1. Query recommendations table with filters → get all matching rows
2. Group rows by reference
3. For each reference group:
   a. Build the color×size matrix from individual rows
   b. Collect all unique sizes and sort them (alpha sizes like XS,S,M,L,XL,XL2... first, then numeric)
   c. Collect all unique colors and sort alphabetically
   d. Sum forecast_base, current_stock, confirmed_orders, net_to_order_base across all rows for totals
   e. Price = avg_price from first row
   f. Cost = estimated_cost_base summed / total_nto (per-unit cost), or price * 0.5 as fallback
   g. Get demand trend by querying historical_sku_color (type="historical") + forecast_monthly (type="forecast") for this reference, aggregate by month
4. Return the array

For the demand trend:
- Query historical_sku_color WHERE reference IN (matched refs), GROUP BY reference, year_month → type="historical"
- Query forecast_monthly WHERE reference IN (matched refs), GROUP BY reference, forecast_month → type="forecast"
- Merge and sort by month

Size sorting function:
- Known alpha sizes: XXS=0, XS=1, S=2, M=3, L=4, XL=5, XL2/XXL=6, XL3/3XL=7, XL4/4XL=8, XL5=9, XL6=10, XL7=11, XL8=12, TU=99
- Try numeric sort for numeric sizes
- Unknown sizes sort last alphabetically

Customer filter implementation:
- When customer parameter is provided, find all references that customer has ordered by querying client_orders WHERE client_name = ? → get distinct references → add to WHERE clause

═══════════════════════════════════════
ENDPOINT: GET /api/filter-options
═══════════════════════════════════════
Query parameters:
- season: string (optional)

Response shape:
{
  "suppliers": ["<string>", ...],
  "families": ["<string>", ...],
  "themes": ["<string>", ...],
  "models": ["<string>", ...],
  "customers": ["<string>", ...],
  "seasons": ["<string>", ...]
}

Implementation:
- If season is provided: query filter_options WHERE critere = season, group by filter_type
- If no season: query all distinct filter_options, group by filter_type
- Map filter_type values: supplier→suppliers, family→families, theme→themes, model→models, customer→customers, season→seasons
- Always include all seasons regardless of filter

═══════════════════════════════════════
ENDPOINT: GET /api/customers
═══════════════════════════════════════
No parameters.

Response: Array of customer objects:
{
  "id": "<client_id>",
  "name": "<client_name>",
  "city": "<ville>",
  "country": "<pays>",
  "totalUnits": <int>,
  "totalSpend": <float>,
  "numSkus": <int>,
  "activeMonths": <int>,
  "seasons": ["<critere1>", "<critere2>", ...],
  "firstOrder": "<date>",
  "lastOrder": "<date>"
}

Implementation:
- Query clients table joined with client_orders for season list
- Seasons: SELECT DISTINCT critere FROM client_orders WHERE client_id = c.client_id
- Order by total_units DESC
- Only include clients with total_units > 0

═══════════════════════════════════════
ENDPOINT: GET /api/customer-detail
═══════════════════════════════════════
Query parameters:
- customer: string (required) — customer NAME
- season: string (optional) — filter by critere

Response:
{
  "customer": { <client info object> },
  "articles": [
    {
      "reference": "<string>",
      "couleur": "<string>",
      "season": "<critere>",
      "orderedQty": <int>,
      "deliveredQty": <int>,
      "trueDemand": <int>,
      "avgPrice": <float>,
      "totalValue": <float>,
      "lastOrderDate": "<date string>"
    },
    ...
  ],
  "totalArticles": <int>
}

Implementation:
- Query client_orders WHERE client_name = customer (and optionally critere = season)
- Group by reference, couleur, critere
- Sum quantities, avg price, max date
- Also query clients table for customer summary info
- Match by client_name OR client_id

═══════════════════════════════════════

TECHNICAL REQUIREMENTS:
- Use FastAPI with CORSMiddleware (allow all origins)
- Use uvicorn to run on port 8000
- Each query function opens its own connection and closes it (thread-safe)
- No caching layer needed — SQLite with indexes is fast enough
- Import get_connection and DB_FILE from database.py
- Run with: python api_server.py

STEP 3:

Modify backend-ai/main.py to add database population after module 8.

Find the section where run_module8 is called (around line 140-150). 
After that call and BEFORE the completion timing/print, add:

    # ══════════════════════════════════════════════
    # DATABASE POPULATION
    # ══════════════════════════════════════════════
    from database import populate_database
    populate_database({
        "data": data,
        "profiles": profiles,
        "kpis": kpis,
        "sarima_output": sarima_output,
        "catboost_output": catboost_output,
        "size_output": size_output,
        "recommendations": reco_output,
    })

Do NOT change anything else in main.py.
The database population should happen after CSV export (m8) so CSVs are still generated as backup.

STEP 4:
|
The only new dependency needed is FastAPI + uvicorn (if not already installed).

Add to requirements.txt if not present:
  fastapi>=0.100.0
  uvicorn>=0.23.0

SQLite is built into Python — no additional package needed.
flask and flask-cors can be REMOVED from requirements.txt if present (we're using FastAPI).

STEP 5:

Create a test script backend-ai/test_db.py that verifies the database is correctly populated and the API returns correct data.

The script should:

1. Check that forecast.db exists at backend-ai/data/forecast.db
2. Print the file size
3. Connect and print row counts for all tables
4. Run a sample /api/articles-style query and verify the response shape
5. Run a sample /api/filter-options-style query
6. Run a sample /api/customers-style query
7. Print timing for each query
8. Check that all critical indexes exist

Example output:
  Database: backend-ai/data/forecast.db (45.2 MB)
  
  Table row counts:
    recommendations:    37,074
    forecast_monthly:   222,444
    historical_demand:  206,941
    historical_sku_color: 58,548
    client_orders:      125,000
    clients:            1,696
    filter_options:     2,340
    pipeline_metadata:  9
  
  Query tests:
    Articles query (season=Hiver(2023)): 342 articles in 45ms
    Filter options (season=Hiver(2023)): 5 categories in 3ms
    Customers list: 1,696 customers in 12ms
    Customer detail: 45 articles in 5ms
  
  Index verification: 15/15 indexes present ✓

Make it runnable with: python test_db.py


STEP 6:

DO NOT modify any frontend files.

But verify that the frontend's API calls in frontend/src/lib/api.ts match the endpoints we've built:

The frontend calls:
1. fetchArticles(season, filters) → GET /api/articles?season=...&supplier=...&family=...&theme=...&model=...&customer=...&searchQuery=...
2. fetchFilterOptions(season) → GET /api/filter-options?season=...
3. fetchCustomers() → GET /api/customers
4. fetchCustomerDetail(customer, season) → GET /api/customer-detail?customer=...&season=...

Verify that:
- The port in frontend/src/lib/api.ts matches our server port (8000)
- If the frontend uses a different port (e.g., 3001), update the API_BASE in api_server.py's CORS settings but still allow all origins
- The response shapes we return match exactly what the frontend TypeScript types expect

If the frontend API_BASE points to a different port, note it but do NOT change the frontend. Instead, make sure api_server.py runs on the port the frontend expects, OR document that the user needs to update the port.



1. Create backend-ai/database.py (Step 1)
2. Replace backend-ai/api_server.py (Step 2)  
3. Update backend-ai/main.py — add 6 lines after m8 (Step 3)
4. Update backend-ai/requirements.txt (Step 4)
5. Create backend-ai/test_db.py (Step 5)
6. Verify frontend compatibility (Step 6)

Then the user runs:
  pip install fastapi uvicorn
  python main.py          ← runs pipeline + populates DB
  python test_db.py       ← verifies DB
  python api_server.py    ← starts API server


  NEW FILES:
  backend-ai/database.py      ← SQLite schema + population
  backend-ai/test_db.py       ← Database verification script

REPLACED FILES:
  backend-ai/api_server.py    ← New version reading from SQLite

MODIFIED FILES:
  backend-ai/main.py          ← Add ~6 lines after m8 for DB population
  backend-ai/requirements.txt ← Add fastapi, uvicorn if missing

NOT TOUCHED:
  backend-ai/config.py
  backend-ai/m1_data_preparation.py
  backend-ai/m2_model_assignment.py
  backend-ai/m3_kpis.py
  backend-ai/m4_sarima.py
  backend-ai/m5_catboost.py
  backend-ai/m6_size_curves.py
  backend-ai/m7_recommendations.py
  backend-ai/m8_output.py
  backend-ai/backtest.py
  frontend/*                   ← NOTHING in frontend changes