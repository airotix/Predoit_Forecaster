"""
FastAPI bridge between the SQLite serving layer and the Next.js frontend.
Reads from backend-ai/data/forecast.db. Response shapes match frontend contracts exactly.
"""

import asyncio
import csv
import datetime
import io
import json
import sqlite3
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
import paths
from typing import Optional, List, Dict, Any

import pandas as pd
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fastapi import FastAPI, Query, Body, UploadFile, File, HTTPException
from pydantic import BaseModel, Field, SecretStr
from joolan import (ensure_joolan_schema, read_trade_workbook, is_trade_workbook, replace_snapshot,
                    snapshot_summary, snapshot_rows, select_forecast_source, selected_pipeline_path, fetch_trade_rows)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from database import get_connection, DB_FILE, _create_persistent_tables, ensure_pipeline_schema
from planning import final_rows,financial_summary,active_plan
from product_routes import install
import threading
_forecast_guard=threading.Lock()
_forecast_pending=False
_file_ingest_guard=threading.Lock()
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

_forecast_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="forecast")

BASE_DIR = paths.HOME
OUTPUT_PATH = BASE_DIR / "output"
RECO_PATH = OUTPUT_PATH / "recommendations.csv"
MONTHLY_PATH = OUTPUT_PATH / "forecast_monthly_detail.csv"

# Origins allowed for CORS (browser will send Origin: http://localhost:3000)
import access_settings
CORS_ORIGINS = set(access_settings.CORS_ORIGINS)


@asynccontextmanager
async def lifespan(application: FastAPI):
    conn = get_connection()
    try:
        _create_persistent_tables(conn)
        ensure_pipeline_schema(conn)
        ensure_joolan_schema(conn)
        from auth_routes import ensure_schema as ensure_auth_schema
        ensure_auth_schema(conn)
        if access_settings.ALLOW_NON_LOCAL and not access_settings.auth_is_active():
            __import__('logging').getLogger('preduit.access').warning(
                'FORECASTER_ALLOW_NON_LOCAL is set while authentication is off: any client that can reach '
                'this port is trusted. Publish the port to localhost only, or set FORECASTER_AUTH_ENABLED=true.')
        conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('source_policy','fresh_only')")
        conn.execute("INSERT OR IGNORE INTO joolan_state VALUES('forecast_source','fresh')")
        conn.execute("UPDATE import_jobs SET status='error',error_message='Server restarted before completion; retry the job.',finished_at=? WHERE status='running'",(datetime.datetime.now(datetime.timezone.utc).isoformat(),))
        conn.commit()
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_skus'").fetchone():
            from catalogue_status import sync_sources
            sync_sources(conn)
        db_path=conn.execute('PRAGMA database_list').fetchone()[2]
    finally:
        conn.close()
    from read_cache import ReadCache
    from fresh_joolan import SOURCE_DB
    cache=ReadCache([db_path,SOURCE_DB]) if db_path else None
    application.state.read_cache=cache
    try:yield
    finally:
        if cache:cache.close()


app = FastAPI(title="Forcaster Backend API", lifespan=lifespan)
from read_cache import CachedReadRoute
app.router.route_class=CachedReadRoute
from fresh_routes import install as install_fresh
install_fresh(app,lambda:get_connection())
install(app,lambda:get_connection())
from budget_routes import install as install_budget
install_budget(app,lambda:get_connection())
from purchase_orders import install as install_purchase_orders
install_purchase_orders(app,lambda:get_connection())
from catalogue import install as install_catalogue
install_catalogue(app,lambda:get_connection())
from seasonal_allocation import install as install_seasonal_allocation
install_seasonal_allocation(app,lambda:get_connection())
from operating_scope import install as install_operating_scope
install_operating_scope(app,lambda:get_connection())
from automatic_forecast import install as install_automatic
install_automatic(app,lambda:get_connection())
from auth_routes import install as install_auth
install_auth(app,lambda:get_connection())
from admin_routes import install as install_admin
install_admin(app,lambda:get_connection())


def _cors_headers(origin: Optional[str]) -> dict:
    o = origin if origin and origin in CORS_ORIGINS else "http://localhost:3000"
    return {
        "Access-Control-Allow-Origin": o,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Max-Age": "86400",
    }


class ForceCORSHeadersMiddleware(BaseHTTPMiddleware):
    """Ensure every response has CORS headers; handle OPTIONS preflight so browser allows cross-origin fetch."""

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            return Response(status_code=200, headers=_cors_headers(origin))
        response = await call_next(request)
        for k, v in _cors_headers(origin).items():
            response.headers[k] = v
        return response


# Add CORS middleware last so it runs outermost and can add headers to every response
app.add_middleware(ForceCORSHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(ValueError)
def input_error_handler(request,exc):
    return JSONResponse(status_code=409,content={'detail':str(exc)})

@app.exception_handler(Exception)
def unhandled_exception_handler(request, exc):
    """Ensure error responses still get CORS headers by returning JSONResponse."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# Size sort: alpha sizes first, then numeric, then unknown
SIZE_ORDER = {"XXS": 0, "XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "XL2": 6, "XXL": 6, "XL3": 7, "3XL": 7,
              "XL4": 8, "4XL": 8, "XL5": 9, "XL6": 10, "XL7": 11, "XL8": 12, "TU": 99}


def _size_sort_key(s: str) -> tuple:
    s = str(s).strip().upper()
    if s in SIZE_ORDER:
        return (0, SIZE_ORDER[s])
    try:
        return (1, float(s))
    except (ValueError, TypeError):
        return (2, s)


def _sort_sizes(sizes: List[str]) -> List[str]:
    return sorted(sizes, key=_size_sort_key)


def _normalize_confidence(val: Optional[str]) -> str:
    """Normalize confidence values from DB (may be uppercase or hyphenated) to 'high'|'medium'|'low'."""
    if not val:
        return "medium"
    v = str(val).strip().lower()
    if v in ("high",):
        return "high"
    if v in ("low",):
        return "low"
    return "medium"


def _get_filtered_recommendations(
    season: Optional[str],
    supplier: Optional[str],
    family: Optional[str],
    theme: Optional[str],
    model: Optional[str],
    customer: Optional[str],
    search_query: Optional[str],
) -> List[Dict[str, Any]]:
    """Return list of recommendation rows from DB with filters applied."""
    conn = get_connection()
    try:
        conditions = []
        params = []
        if season and str(season).strip() and str(season) != "All":
            conditions.append("saison = ?")
            params.append(season)
        if supplier and supplier != "All":
            conditions.append("fournisseur = ?")
            params.append(supplier)
        if family and family != "All":
            conditions.append("famille = ?")
            params.append(family)
        if theme and theme != "All":
            conditions.append("theme = ?")
            params.append(theme)
        if model and model != "All":
            conditions.append("modele = ?")
            params.append(model)
        if customer and customer != "All":
            # Customer filter: references that this customer has ordered
            sub = conn.execute(
                "SELECT DISTINCT reference FROM client_orders WHERE client_name = ? OR client_id = ?",
                (customer, customer),
            ).fetchall()
            refs = [r[0] for r in sub]
            if not refs:
                return []
            placeholders = ",".join("?" * len(refs))
            conditions.append(f"reference IN ({placeholders})")
            params.extend(refs)
        if search_query and str(search_query).strip():
            q = f"%{str(search_query).strip().lower()}%"
            conditions.append("(LOWER(reference) LIKE ? OR LOWER(fournisseur) LIKE ? OR LOWER(client) LIKE ?)")
            params.extend([q, q, q])

        # Hide Saison "L" articles from default browsing; allow them in search results
        if not search_query or not str(search_query).strip():
            conditions.append("(saison IS NULL OR UPPER(TRIM(saison)) != 'L')")

        where = " AND ".join(conditions) if conditions else "1=1"
        cursor = conn.execute(
            f"SELECT reference, couleur, taille, saison, fournisseur, famille, theme, modele, client, "
            f"forecast_base, current_stock, confirmed_orders, avg_price, estimated_cost_base "
            f"FROM recommendations WHERE {where}",
            params,
        )
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return rows
    finally:
        conn.close()


def _get_demand_trend_by_references(conn, references: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """For each reference, get demand trend as [{ date, value }] from forecast_monthly."""
    if not references:
        return {}
    placeholders = ",".join("?" * len(references))
    cursor = conn.execute(
        f"SELECT reference, forecast_month, SUM(forecast_base) AS total "
        f"FROM forecast_monthly WHERE reference IN ({placeholders}) GROUP BY reference, forecast_month ORDER BY reference, forecast_month",
        references,
    )
    by_ref: Dict[str, List[Dict[str, Any]]] = {}
    for row in cursor.fetchall():
        ref, fm, total = row[0], row[1], row[2] or 0
        if ref not in by_ref:
            by_ref[ref] = []
        by_ref[ref].append({"date": str(fm), "value": float(total)})
    return by_ref


def _rows_to_articles(rows: List[Dict], demand_trend_by_ref: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
    """Convert recommendation rows (grouped by reference) into ArticleData[] shape."""
    if not rows:
        return []

    # Group by reference
    by_ref: Dict[str, List[Dict]] = {}
    for r in rows:
        ref = r.get("reference", "")
        if ref not in by_ref:
            by_ref[ref] = []
        by_ref[ref].append(r)

    articles = []
    for ref, grp in by_ref.items():
        sizes = _sort_sizes(list({str(r.get("taille", "")) for r in grp if r.get("taille")}))
        colors = sorted({str(r.get("couleur", "")) for r in grp if r.get("couleur")})

        matrix: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for r in grp:
            color = str(r.get("couleur", ""))
            size = str(r.get("taille", ""))
            if not color or not size:
                continue
            matrix.setdefault(color, {})[size] = {
                "forecast": int(r.get("forecast_base") or 0),
                "stock": int(r.get("current_stock") or 0),
                "orders": int(r.get("confirmed_orders") or 0),
            }

        demand_trend = demand_trend_by_ref.get(ref, [])

        avg_price = float(grp[0].get("avg_price") or 0.0)
        total_fcst = sum(int(r.get("forecast_base") or 0) for r in grp)
        total_cost = sum(float(r.get("estimated_cost_base") or 0) for r in grp)
        unit_cost = total_cost / total_fcst if total_fcst > 0 else 0.0

        def first_non_null(col: str) -> str:
            for r in grp:
                v = r.get(col)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return "â€”"

        articles.append({
            "id": str(ref),
            "season": first_non_null("saison"),
            "supplier": first_non_null("fournisseur"),
            "customer": first_non_null("client"),
            "family": first_non_null("famille"),
            "theme": first_non_null("theme"),
            "model": first_non_null("modele"),
            "sizes": sizes,
            "colors": colors,
            "matrix": matrix,
            "demandTrend": demand_trend,
            "price": avg_price,
            "cost": unit_cost,
        })
    return articles


@app.get("/api/articles")
def get_articles(
    season: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    family: Optional[str] = Query(None),
    theme: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    customer: Optional[str] = Query(None),
    searchQuery: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    rows = _get_filtered_recommendations(
        season=season,
        supplier=supplier,
        family=family,
        theme=theme,
        model=model,
        customer=customer,
        search_query=searchQuery,
    )
    if not rows:
        return []
    refs = list({r["reference"] for r in rows})
    conn = get_connection()
    try:
        demand_trend_by_ref = _get_demand_trend_by_references(conn, refs)
    finally:
        conn.close()
    return _rows_to_articles(rows, demand_trend_by_ref)


@app.get("/api/filter-options")
def get_filter_options(
    season: Optional[str] = Query(None),
) -> Dict[str, List[str]]:
    conn = get_connection()
    try:
        # Seasons: always All + all distinct saison from recommendations
        cursor = conn.execute("SELECT DISTINCT saison FROM recommendations WHERE saison IS NOT NULL AND saison != '' ORDER BY saison")
        seasons_list = ["All"] + [r[0] for r in cursor.fetchall()]

        if season and str(season).strip() and str(season) != "All":
            cursor = conn.execute(
                "SELECT filter_type, filter_value FROM filter_options WHERE saison = ?",
                (season,),
            )
        else:
            cursor = conn.execute("SELECT filter_type, filter_value FROM filter_options")

        by_type: Dict[str, List[str]] = {
            "supplier": ["All"],
            "family": ["All"],
            "theme": ["All"],
            "model": ["All"],
            "customer": ["All"],
        }
        seen = {k: {"All"} for k in by_type}
        for row in cursor.fetchall():
            ft, fv = row[0], row[1]
            if ft == "season":
                continue
            if ft not in by_type:
                continue
            if fv and fv not in seen[ft]:
                seen[ft].add(fv)
                by_type[ft].append(fv)

        for k in by_type:
            by_type[k].sort(key=lambda x: (0 if x == "All" else 1, x))

        return {
            "seasons": seasons_list,
            "suppliers": by_type["supplier"],
            "families": by_type["family"],
            "themes": by_type["theme"],
            "models": by_type["model"],
            "customers": by_type["customer"],
        }
    finally:
        conn.close()


@app.get("/api/customers")
def get_customers() -> Dict[str, Any]:
    conn=get_connection()
    try:
        from customer_coverage import report
        return report(conn)
    finally:conn.close()


@app.get("/api/customer-detail")
def get_customer_detail(
    customer: str = Query(...),
    season: Optional[str] = Query("All"),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        where="(co.client_id=? OR co.client_name=?)";params=[customer,customer]
        if season and season!='All':
            where+=" AND (co.season_type || '(' || CAST(CAST(co.season_year AS INTEGER) AS TEXT) || ')')=?";params.append(season)
        cursor=conn.execute(f"""SELECT co.reference,co.couleur,co.taille,
            MAX(co.season_type) AS saison,MAX(r.fournisseur) AS fournisseur,MAX(r.famille) AS famille,
            MAX(r.theme) AS theme,MAX(r.modele) AS modele,co.client_id AS client,
            0 AS forecast_base,NULL AS current_stock,SUM(MAX(co.cde_qte-co.liv_qte,0)) AS confirmed_orders,
            AVG(co.prix) AS avg_price,NULL AS estimated_cost_base,SUM(co.cde_qte) AS ordered_units
            FROM client_orders co LEFT JOIN recommendations r ON co.reference=r.reference AND co.couleur=r.couleur AND co.taille=r.taille
            WHERE {where} GROUP BY co.reference,co.couleur,co.taille,co.client_id""",params)
        rows=[dict(zip([d[0] for d in cursor.description],row)) for row in cursor]
        customer_seasons=[row[0] for row in conn.execute("SELECT DISTINCT season_type || '(' || CAST(CAST(season_year AS INTEGER) AS TEXT) || ')' FROM client_orders WHERE client_id=? OR client_name=?",(customer,customer))]
        articles=_rows_to_articles(rows,{})
        return dict(customer=customer,season=season,seasonsAvailable=customer_seasons,
                    totalOrders=sum(row['ordered_units'] or 0 for row in rows),articles=articles,
                    notice='Recorded customer quantities; no customer-specific future forecast. Individual dated orders are available from /api/orders.')
    finally:conn.close()


@app.get("/health")
def healthcheck() -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM recommendations")
        count = cursor.fetchone()[0]
    except Exception:
        count = 0
    finally:
        conn.close()
    return {
        "status": "ok",
        "recommendations_count": count,
        "recommendations_exists": RECO_PATH.exists(),
        "monthly_detail_exists": MONTHLY_PATH.exists(),
    }


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard() -> Dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT reference || '|' || couleur) AS total_skus,
                COALESCE(SUM(forecast_base), 0) AS total_forecast_units,
                COALESCE(SUM(confirmed_orders), 0) AS total_confirmed,
                COALESCE(SUM(estimated_cost_base), 0) AS total_purchase_cost,
                COALESCE(SUM(expected_revenue_base), 0) AS expected_turnover,
                COALESCE(SUM(estimated_margin_base), 0) AS gross_margin,
                COUNT(DISTINCT client) AS total_clients
            FROM recommendations
        """).fetchone()

        total_skus = row[0] or 0
        total_forecast = row[1] or 0
        total_confirmed = row[2] or 0
        total_purchase_cost = row[3] or 0
        expected_turnover = row[4] or 0
        gross_margin = row[5] or 0
        total_clients = conn.execute('SELECT COUNT(*) FROM clients').fetchone()[0]

        risk_row = conn.execute(
            "SELECT COUNT(DISTINCT reference || '|' || couleur) FROM recommendations WHERE LOWER(confidence) = 'low'"
        ).fetchone()
        risk_count = risk_row[0] if risk_row else 0

        coverage_row = conn.execute("""
            SELECT COUNT(*) FROM clients WHERE last_order >= date(
                (SELECT MAX(last_order) FROM clients), '-6 months')
        """).fetchone()
        visited_clients = coverage_row[0] if coverage_row else 0
        coverage = round(visited_clients / total_clients * 100, 1) if total_clients > 0 else 0

        margin_pct = round(gross_margin / expected_turnover * 100, 1) if expected_turnover > 0 else 0

        # Pipeline metadata
        meta_row = conn.execute(
            "SELECT value FROM pipeline_metadata WHERE key = 'last_run'"
        ).fetchone()
        last_run = meta_row[0] if meta_row else None

        # Confidence distribution
        conf_rows = conn.execute("""
            WITH grouped AS (
              SELECT reference,couleur,
                CASE WHEN SUM(CASE WHEN LOWER(COALESCE(confidence,'LOW')) NOT IN ('high','medium') THEN 1 ELSE 0 END)>0 THEN 'LOW'
                  WHEN SUM(CASE WHEN LOWER(confidence)='medium' THEN 1 ELSE 0 END)>0 THEN 'MEDIUM' ELSE 'HIGH' END AS confidence
              FROM recommendations GROUP BY reference,couleur)
            SELECT confidence,COUNT(*) FROM grouped GROUP BY confidence
        """).fetchall()
        confidence_dist = {_normalize_confidence(r[0]): r[1] for r in conf_rows if r[0]}

        finances=financial_summary(conn,'base')
        total_purchase_cost=finances['totalPurchaseCost'] or 0
        expected_turnover=finances['expectedTurnover'] or 0
        gross_margin=finances['grossMargin'] or 0
        margin_pct=finances['grossMarginPercent'] or 0
        season_budget=finances['seasonBudget']
        budget_percentage=finances['budgetUsage'] or 0

        currency=(active_plan(conn) or {}).get("currency","EUR")
        kpis = [
            {"label": "Total Forecast Units", "value": f"{total_forecast:,}", "subLabel": f"{total_skus} SKUs", "trend": "neutral", "trendValue": 0},
            {"label": "Undelivered Order Balance", "value": f"{total_confirmed:,}", "subLabel": "Across recorded customer orders", "trend": "neutral", "trendValue": 0},
            {"label": "Budget Usage", "value": f"{round(budget_percentage)}%", "subLabel": f"{currency} {total_purchase_cost:,.0f} / {season_budget:,.0f}", "trend": "neutral", "trendValue": round(budget_percentage, 1)},
            {"label": "Gross Margin", "value": f"{margin_pct}%", "subLabel": f"{currency} {gross_margin:,.0f}", "trend": "up" if margin_pct >= 40 else "down", "trendValue": margin_pct},
            {"label": "Customer Activity", "value": f"{coverage}%", "subLabel": f"{visited_clients} / {total_clients} ordered in the latest 6 data months", "trend": "neutral", "trendValue": 0},
            {"label": "Risk Items", "value": str(risk_count), "subLabel": "Low-confidence SKUs", "trend": "down" if risk_count > 10 else "up", "trendValue": risk_count},
        ]

        financial_summary_data = {
            "budgetUsed": total_purchase_cost,
            "budgetTotal": season_budget,
            "margin": margin_pct,
            "targetMargin": finances["targetMargin"] or 0,
            "coverage": coverage,
            "totalPurchaseCost": total_purchase_cost,
            "expectedTurnover": expected_turnover,
        }

        return {
            "kpis": kpis,
            "financialSummary": financial_summary_data,
            "confidenceDistribution": confidence_dist,
            "lastPipelineRun": last_run,
            "totalSKUs": total_skus,
            "financialComplete": finances["financialComplete"],
            "missingInputRows": finances["missingInputRows"],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PRODUCTS
# ---------------------------------------------------------------------------

@app.get("/api/products")
def get_products(
    season: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        conditions = []
        params: list = []
        if season and season != "All":
            conditions.append("saison = ?")
            params.append(season)
        if category and category != "All":
            conditions.append("famille = ?")
            params.append(category)
        if status and status != "All":
            conditions.append("product_status = ?")
            params.append(status)
        if search and search.strip():
            q = f"%{search.strip().lower()}%"
            conditions.append("(LOWER(reference) LIKE ? OR LOWER(designation) LIKE ? OR LOWER(famille) LIKE ?)")
            params.extend([q, q, q])

        where = " AND ".join(conditions) if conditions else "1=1"

        cursor = conn.execute(f"""
            SELECT
                reference, couleur,
                MAX(saison) AS saison,
                MAX(famille) AS famille,
                MAX(designation) AS designation,
                MAX(product_status) AS product_status,
                MAX(model_type) AS model_type,
                CASE WHEN SUM(CASE WHEN LOWER(COALESCE(confidence,'LOW')) NOT IN ('high','medium') THEN 1 ELSE 0 END)>0 THEN 'LOW' WHEN SUM(CASE WHEN LOWER(confidence)='medium' THEN 1 ELSE 0 END)>0 THEN 'MEDIUM' ELSE 'HIGH' END AS confidence,
                MAX(diffusion_rate) AS diffusion_rate,
                MAX(depth_per_client) AS depth_per_client,
                MAX(reorder_rate) AS reorder_rate,
                MAX(total_buying_clients) AS total_buying_clients,
                COALESCE(SUM(forecast_base), 0) AS forecast_units,
                MAX(avg_price) AS avg_price,
                GROUP_CONCAT(DISTINCT taille) AS sizes_csv
            FROM recommendations
            WHERE {where}
            GROUP BY reference, couleur
            ORDER BY SUM(forecast_base) DESC
        """, params)

        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        products = []
        for r in rows:
            sizes_raw = (r.get("sizes_csv") or "").split(",")
            sizes = _sort_sizes([s.strip() for s in sizes_raw if s.strip()])
            size_breakdown = {}
            for s in sizes:
                size_breakdown[s] = 0

            products.append({
                "skuId": f"{r['reference']}|{r['couleur']}",
                "name": r.get("designation") or r["reference"],
                "category": r.get("famille") or "Unknown",
                "status": r.get("product_status") or "core",
                "season": r.get("saison") or "",
                "diffusionRate": round(float(r.get("diffusion_rate") or 0), 4),
                "depthPerCustomer": round(float(r.get("depth_per_client") or 0), 2),
                "reorderRate": round(float(r.get("reorder_rate") or 0), 4),
                "forecastUnits": round(float(r.get("forecast_units") or 0), 4),
                "buyingCustomers": int(r.get("total_buying_clients") or 0),
                "sizeBreakdown": size_breakdown,
                "aiConfidence": _normalize_confidence(r.get("confidence")),
            })

        from product_kpis import attach_history
        from article_activity import attach
        return attach(conn,attach_history(conn,products),lambda row:row['skuId'].split('|',1)[0])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PROJECTIONS
# ---------------------------------------------------------------------------

@app.get("/api/projections")
def get_projections(
    season: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        columns={r[1] for r in conn.execute('PRAGMA table_info(recommendations)')}
        booked='COALESCE(season_booked,confirmed_orders)' if 'season_booked' in columns else 'confirmed_orders'
        season_basis='season_bookings' if 'season_booked' in columns and conn.execute('SELECT 1 FROM recommendations WHERE season_booked IS NOT NULL LIMIT 1').fetchone() else 'legacy_open_balances'
        conditions = []
        params: list = []
        if season and season != "All":
            conditions.append("saison = ?")
            params.append(season)
        if search and search.strip():
            q = f"%{search.strip().lower()}%"
            conditions.append("(LOWER(reference) LIKE ? OR LOWER(designation) LIKE ?)")
            params.extend([q, q])

        where = " AND ".join(conditions) if conditions else "1=1"

        cursor = conn.execute(f"""
            SELECT
                reference,
                MAX(famille) AS category,
                MAX(designation) AS designation,
                CASE WHEN SUM(CASE WHEN LOWER(COALESCE(confidence,'LOW')) NOT IN ('high','medium') THEN 1 ELSE 0 END)>0 THEN 'LOW' WHEN SUM(CASE WHEN LOWER(confidence)='medium' THEN 1 ELSE 0 END)>0 THEN 'MEDIUM' ELSE 'HIGH' END AS confidence,
                COALESCE(SUM({booked}), 0) AS confirmed,
                COALESCE(SUM(probable_additional_base), 0) AS probable_reorders,
                COALESCE(SUM(forecast_base) - SUM({booked}) - SUM(probable_additional_base), 0) AS non_visited_projection,
                COALESCE(SUM(forecast_conservative), 0) AS total_conservative,
                COALESCE(SUM(forecast_base), 0) AS total_base,
                COALESCE(SUM(forecast_optimistic), 0) AS total_optimistic,
                MAX(diffusion_rate) AS diffusion_rate,
                MAX(depth_per_client) AS depth_per_client,
                MAX(total_buying_clients) AS customer_count,
                MAX(reorder_rate) AS reorder_rate
            FROM recommendations
            WHERE {where}
            GROUP BY reference
            ORDER BY SUM(forecast_base) DESC
        """, params)

        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        projections = []
        for r in rows:
            confirmed = round(float(r.get("confirmed") or 0), 4)
            reorders = round(float(r.get("probable_reorders") or 0), 4)
            non_visited = max(0, round(float(r.get("non_visited_projection") or 0), 4))
            total_base = round(float(r.get("total_base") or 0), 4)
            total_conservative = round(float(r.get("total_conservative") or 0), 4)
            total_optimistic = round(float(r.get("total_optimistic") or 0), 4)

            conf_level = _normalize_confidence(r.get("confidence"))
            dr = float(r.get("diffusion_rate") or 0)
            dpc = float(r.get("depth_per_client") or 0)
            cc = int(r.get("customer_count") or 0)
            rr = float(r.get("reorder_rate") or 0)

            projections.append({
                "projectionBasis": season_basis,
                "skuId": f"SKU-{r['reference']}",
                "skuName": r.get("designation") or r["reference"],
                "category": r.get("category") or "Unknown",
                "scenarios": {
                    name: {"confirmed": min(confirmed, total), "probableReorders": max(total-confirmed,0), "nonVisitedProjection": 0, "total": total}
                    for name,total in [('conservative',total_conservative),('base',total_base),('optimistic',total_optimistic)]
                },
                "confidence": conf_level,
                "explainability": {
                    "confirmedOrders": {"units": confirmed, "customerCount": cc},
                    "probableReorders": {"units": reorders, "reorderRate": round(rr, 3), "likelyCustomers": 0},
                    "nonVisitedDemand": {"units": non_visited, "matchedCustomers": 0, "clusterProfile": "Not modeled"},
                    "keySignals": {"diffusionRate": round(dr, 4), "depthPerCustomer": round(dpc, 2), "customerCluster": "Not modeled", "scenarioMultiplier": 1.0},
                },
            })

        from article_activity import attach
        return attach(conn,projections,lambda row:row['skuId'].removeprefix('SKU-'))
    finally:
        conn.close()


@app.get("/api/projections/{reference}/detail")
def get_projection_detail(reference: str, scenario: str=Query('base')) -> Dict[str, Any]:
    from projection_detail import detail
    conn = get_connection()
    try: return detail(conn, reference, scenario)
    finally: conn.close()

# ---------------------------------------------------------------------------
# BUDGET
# ---------------------------------------------------------------------------

@app.get("/api/budget")
def get_budget(scenario: str=Query('base')):
    conn=get_connection()
    try:
        if __import__("purchase_draft").enabled(conn):
            from budgeting import build_report
            try:return build_report(conn,scenario)
            except ValueError as e:raise HTTPException(409,str(e)) from None
        summary=financial_summary(conn,scenario)
        rows=final_rows(conn,scenario)
        categories=[]
        for name in sorted({r['famille'] or 'Other' for r in rows}):
            selected=[r for r in rows if (r['famille'] or 'Other')==name]
            cost=sum(r['purchase_cost'] or 0 for r in selected)
            revenue=sum(r['turnover'] or 0 for r in selected)
            cogs=sum(r['demand_forecast']*float(r.get('unit_purchase_cost') or 0) for r in selected)
            budget=summary['seasonBudget']
            categories.append(dict(category=name,purchaseCost=cost,budgetPercent=cost/budget*100 if budget else 0,
                marginPercent=(revenue-cogs)/revenue*100 if revenue else 0,
                status='over_budget' if budget and cost>budget else 'on_target',skus=[]))
        complete=summary['financialComplete']
        # Legacy frontend numeric cards remain zero until supplied, but the whole
        # financial section is hidden by its explicit completeness flag.
        numeric={k:(0 if v is None else v) for k,v in summary.items()}
        return dict(summary=numeric,categories=categories if complete else [],financialComplete=complete,missingInputRows=summary['missingInputRows'])
    finally:conn.close()


@app.get("/api/recommendations")
def get_recommendations(
    season: Optional[str] = Query(None),
    scenario: Optional[str] = Query("base"),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        if scenario not in ('base','conservative','optimistic'):raise HTTPException(400,'Unknown scenario.')
        conditions = []
        params: list = []
        if season and season != "All":
            conditions.append("r.saison = ?")
            params.append(season)
        if category and category != "All":
            conditions.append("r.famille = ?")
            params.append(category)
        if search and search.strip():
            q = f"%{search.strip().lower()}%"
            conditions.append("(LOWER(r.reference) LIKE ? OR LOWER(r.designation) LIKE ?)")
            params.extend([q, q])

        where = " AND ".join(conditions) if conditions else "1=1"

        cursor = conn.execute(f"""
            SELECT
                r.reference, r.couleur,
                MAX(r.designation) AS designation,
                MAX(r.famille) AS famille,
                CASE WHEN SUM(CASE WHEN LOWER(COALESCE(r.confidence,'LOW')) NOT IN ('high','medium') THEN 1 ELSE 0 END)>0 THEN 'LOW' WHEN SUM(CASE WHEN LOWER(r.confidence)='medium' THEN 1 ELSE 0 END)>0 THEN 'MEDIUM' ELSE 'HIGH' END AS confidence,
                COALESCE(SUM(r.forecast_conservative), 0) AS fc,
                COALESCE(SUM(r.forecast_base), 0) AS fb,
                COALESCE(SUM(r.forecast_optimistic), 0) AS fo,
                COALESCE(SUM(r.confirmed_orders), 0) AS confirmed,
                COALESCE(SUM(r.estimated_cost_base), 0) AS cost,
                COALESCE(SUM(r.expected_revenue_base), 0) AS revenue,
                COALESCE(SUM(r.estimated_margin_base), 0) AS margin,
                MAX(r.diffusion_rate) AS dr,
                MAX(r.depth_per_client) AS dpc,
                MAX(r.total_buying_clients) AS bc,
                MAX(r.reorder_rate) AS rr,
                MAX(r.margin_rate_base) AS mr
            FROM recommendations r
            WHERE {where}
            GROUP BY r.reference, r.couleur
            ORDER BY SUM(r.forecast_base) DESC
        """, params)

        columns = [d[0] for d in cursor.description]
        grouped_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        locks = {}
        try:
            lock_cursor = conn.execute("SELECT reference, couleur, locked FROM sku_locks")
            for lr in lock_cursor.fetchall():
                locks[(lr[0], lr[1])] = bool(lr[2])
        except Exception:
            pass

        draft_meta={}
        if __import__("purchase_draft").enabled(conn):
            from purchase_draft import read as read_draft
            draft_meta=read_draft(conn,scenario or "base")
        from catalogue import price_map
        saved_prices=price_map(conn,(active_plan(conn) or {}).get('currency','EUR'))
        purchase_rows=final_rows(conn,scenario or 'base',_saved_prices=saved_prices)
        purchase_map={(r['reference'],r['couleur'],r['taille']):r for r in purchase_rows}
        scenarios_rows={sc:purchase_rows if sc==scenario else final_rows(conn,sc,_saved_prices=saved_prices) for sc in ('conservative','base','optimistic')}
        purchase_groups=defaultdict(list)
        for row in purchase_rows:purchase_groups[(row['reference'],row['couleur'])].append(row)
        scenario_totals={}
        for sc,rows in scenarios_rows.items():
            values=defaultdict(float)
            for row in rows:
                key=(row['reference'],row['couleur'])
                if row['final_quantity'] is None:values[key]=None
                elif values[key] is not None:values[key]+=row['final_quantity']
            scenario_totals[sc]=values
        history_map=defaultdict(dict)
        for ref,color,size,quantity in conn.execute('SELECT reference,couleur,taille,SUM(true_demand) FROM historical_demand GROUP BY reference,couleur,taille'):
            if quantity is not None:history_map[(ref,color)][size]=float(quantity)
        plan=active_plan(conn)
        results = []
        for g in grouped_rows:
            ref, coul = g["reference"], g["couleur"]
            sku_key = f"{ref}|{coul}"

            item_rows=purchase_groups[(ref,coul)]
            size_rows=[(row['taille'],) for row in sorted(item_rows,key=lambda row:row['taille'])]
            override_map={row['taille']:row['manual_override'] for row in item_rows if row['manual_override'] is not None}

            from recommendation_view import size_breakdown as describe_sizes
            size_breakdown = describe_sizes(item_rows,_size_sort_key)
            is_locked = locks.get((ref, coul), False)
            has_override = bool(override_map)

            if is_locked:
                rec_status = "locked"
            elif has_override:
                rec_status = "adjusted"
            else:
                rec_status = "pending"

            if status and status != "All" and rec_status != status:
                continue

            fb = int(g.get("fb") or 0)
            fc = int(g.get("fc") or 0)
            fo = int(g.get("fo") or 0)
            confirmed = int(g.get("confirmed") or 0)
            cost_val = float(g.get("cost") or 0)
            revenue_val = float(g.get("revenue") or 0)
            margin_val = float(g.get("margin") or 0)
            margin_pct = round(margin_val / revenue_val * 100, 1) if revenue_val > 0 else 0
            cost_val=sum(r['purchase_cost'] or 0 for r in item_rows)
            revenue_val=sum(r['turnover'] or 0 for r in item_rows)
            cogs=sum((r['cost_of_sales'] or 0) if 'cost_of_sales' in r else r['demand_forecast']*float(r.get('unit_purchase_cost') or 0) for r in item_rows)
            margin_pct=(revenue_val-cogs)/revenue_val*100 if revenue_val else 0
            budget=float(plan['budget']) if plan else 0
            budget_impact=cost_val/budget*100 if budget else 0

            totals={sc:round(sum(r['forecast_'+sc] or 0 for r in item_rows),4) for sc in scenario_totals}
            purchase_totals={sc:values[(ref,coul)] for sc,values in scenario_totals.items()}
            historical_sizes=history_map[(ref,coul)]
            margin_val=revenue_val-cogs
            results.append({
                "skuId": f"{ref}|{coul}",
                "skuName": f"{g.get('designation') or ref} â€” {coul}",
                "category": g.get("famille") or "Unknown",
                "status": rec_status,
                "locked": is_locked,
                "draftVersion": draft_meta.get("version"),
                "forecastRun": draft_meta.get("forecastRun"),
                "scenarios": {sc:{"confirmed":0,"probableReorders":totals[sc],"nonVisitedProjection":0,"total":totals[sc]} for sc in totals},
                "currentScenarioTotal": totals[scenario or 'base'],
                "purchaseTotals":purchase_totals,
                "historicalSizes":historical_sizes,
                "sizeBreakdown": size_breakdown,
                "confidence": _normalize_confidence(g.get("confidence")),
                "explainability": {
                    "confirmedOrders": {"units": confirmed, "customerCount": int(g.get("bc") or 0)},
                    "probableReorders": {"units": 0, "reorderRate": round(float(g.get("rr") or 0), 3), "likelyCustomers": 0},
                    "nonVisitedDemand": {"units": 0, "matchedCustomers": 0, "clusterProfile": "Not modeled"},
                    "keySignals": {"diffusionRate": round(float(g.get("dr") or 0), 4), "depthPerCustomer": round(float(g.get("dpc") or 0), 2), "customerCluster": "Not modeled", "scenarioMultiplier": 1.0},
                },
                "financialImpact": {
                    "complete": all(not r["decision_required"] or (r["final_quantity"] is not None and r["inventory_known"] and r["cost_known"] and r["price_known"]) for r in item_rows),
                    "purchaseCost": round(cost_val, 2),
                    "expectedTurnover": round(revenue_val, 2),
                    "grossMargin": round(margin_val, 2),
                    "marginPercent": margin_pct,
                    "budgetImpactPercent": budget_impact,
                },
            })

        from article_activity import attach
        return attach(conn,results,lambda row:row['skuId'].split('|',1)[0])
    finally:
        conn.close()


@app.put("/api/recommendations/{reference}/{couleur}")
def update_recommendation(
    reference: str,
    couleur: str,
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        size_breakdown = body.get("sizeBreakdown", [])
        reason = body.get("reason", "")
        notes = body.get("notes", "")
        chosen_scenario=body.get('scenario','base')
        if chosen_scenario not in ('conservative','base','optimistic'):raise HTTPException(400,'Unknown scenario.')
        from recommendation_view import validate_edits
        try:
            scoped=[r for r in final_rows(conn,chosen_scenario) if r['reference']==reference and r['couleur']==couleur]
            validated=validate_edits(scoped,body)
        except ValueError as e:raise HTTPException(400,str(e)) from None
        plan=active_plan(conn)
        plan_id=plan['id'] if plan else ''
        user = "authenticated" if __import__("os").environ.get("FORECASTER_API_TOKEN") else "local"
        locked=conn.execute("SELECT locked FROM sku_locks WHERE reference=? AND couleur=?",(reference,couleur)).fetchone()
        if locked and locked[0]:raise HTTPException(409,"Unlock this recommendation before editing it.")

        if __import__("purchase_draft").enabled(conn):
            import budgeting,purchase_draft
            from catalogue import sync
            sync(conn)
            try:
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    report=budgeting.build_report(conn,chosen_scenario,sync_catalogue=False)
                    result=purchase_draft.recommendation_edit(conn,report,reference,couleur,validated,reason,
                        body.get('draftVersion'),body.get('forecastRun'))
                return dict(status='ok',draftVersion=result['draft']['version'])
            except ValueError as e:raise HTTPException(409,str(e)) from None

        for taille,override_qty in validated:
            if not __import__("math").isfinite(override_qty) or override_qty<0:raise HTTPException(400,"Quantity must be finite and nonnegative.")
            if not conn.execute("SELECT 1 FROM recommendations WHERE reference=? AND couleur=? AND taille=?",(reference,couleur,taille)).fetchone():raise HTTPException(404,"Unknown product size.")
            conn.execute(
                "INSERT INTO user_overrides (reference, couleur, taille, override_qty, reason, notes, user, created_at, updated_at,scenario,plan_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?)",
                (reference, couleur, taille, override_qty, reason, notes, user, now, now,chosen_scenario,plan_id),
            )

        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, previous_value, new_value, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, user, "override", "recommendation", f"{reference}|{couleur}", reference, "", json.dumps(size_breakdown), notes),
        )
        conn.commit()
        return {"status": "ok", "reference": reference, "couleur": couleur, "overridesApplied": len(size_breakdown)}
    finally:
        conn.close()


@app.post("/api/recommendations/{reference}/{couleur}/lock")
def lock_recommendation(reference: str, couleur: str, body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user = "authenticated" if __import__("os").environ.get("FORECASTER_API_TOKEN") else "local"
        locked=conn.execute("SELECT locked FROM sku_locks WHERE reference=? AND couleur=?",(reference,couleur)).fetchone()
        if not conn.execute('SELECT 1 FROM recommendations WHERE reference=? AND couleur=?',(reference,couleur)).fetchone():raise HTTPException(404,'Unknown product.')
        if locked and locked[0]:return {'status':'locked','reference':reference,'couleur':couleur}
        conn.execute(
            "INSERT OR REPLACE INTO sku_locks (reference, couleur, locked, locked_by, locked_at) VALUES (?, ?, 1, ?, ?)",
            (reference, couleur, user, now),
        )
        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, user, "lock", "recommendation", f"{reference}|{couleur}", reference, "Locked"),
        )
        conn.commit()
        return {"status": "locked", "reference": reference, "couleur": couleur}
    finally:
        conn.close()


@app.post("/api/recommendations/{reference}/{couleur}/unlock")
def unlock_recommendation(reference: str, couleur: str, body: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    conn = get_connection()
    try:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user = "authenticated" if __import__("os").environ.get("FORECASTER_API_TOKEN") else "local"
        conn.execute(
            "INSERT OR REPLACE INTO sku_locks (reference, couleur, locked, locked_by, locked_at) VALUES (?, ?, 0, ?, ?)",
            (reference, couleur, user, now),
        )
        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, user, "unlock", "recommendation", f"{reference}|{couleur}", reference, "Unlocked"),
        )
        conn.commit()
        return {"status": "unlocked", "reference": reference, "couleur": couleur}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# VALIDATION & AUDIT
# ---------------------------------------------------------------------------

@app.get("/api/validation")
def get_validation(scenario: str=Query('base')):
    if scenario not in ('conservative','base','optimistic'):raise HTTPException(400,'Unknown scenario.')
    conn=get_connection()
    try:
        values={};complete=True;scenario_rows={}
        for sc in ('conservative','base','optimistic'):
            rows=final_rows(conn,sc);scenario_rows[sc]=rows
            summary=financial_summary(conn,sc,rows=rows)
            complete=complete and summary['financialComplete']
            values[sc]=dict(totalUnits=sum(r['final_quantity'] for r in rows) if all(r['final_quantity'] is not None for r in rows) else None,
                purchaseCost=summary['totalPurchaseCost'],budgetUsage=summary['budgetUsage'],
                grossMargin=summary['grossMarginPercent'],
                skusAtRisk=len({(r['reference'],r['couleur']) for r in rows if str(r['confidence']).lower()=='low'}))
        rows=scenario_rows[scenario]
        overrides=[dict(skuId=r['reference']+'|'+r['couleur']+'|'+r['taille'],skuName=r['reference'],aiRecommended=r['recommended_quantity'] or 0,userOverride=r['manual_override'],reasonTag='Manual adjustment',notes='') for r in rows if r['manual_override'] is not None]
        state=dict(conn.execute('SELECT key,value FROM joolan_state'))
        fresh_only=state.get('source_policy')=='fresh_only'
        return dict(scenarioMetrics=values,overrides=overrides,financialComplete=complete,skuCount=len(rows),
            approvalAvailable=complete and not fresh_only,
            approvalNotice='Approved purchase export is not enabled for this Joolan deployment. Review the forecast draft and financial plan; supplier orders must be created separately.' if fresh_only else 'Complete the financial and inventory inputs before requesting an approved export.')
    finally:conn.close()


@app.get("/api/audit")
def get_audit(
    limit: int = Query(50),
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT id, timestamp, user, action, entity_type, entity_id, entity_name,
                   previous_value, new_value, details
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return rows
    finally:
        conn.close()


@app.get("/api/export")
@app.post("/api/export")
def export_recommendations(format: str=Query('csv'),scenario: str=Query('base'),season_id: str=Query(None),purpose: str=Query('draft')):
    conn=get_connection()
    try:
        if format not in ('csv','json'):raise HTTPException(400,'Supported formats are CSV and JSON.')
        if purpose not in ('draft','approved'):raise HTTPException(400,'Unknown export purpose.')
        if purpose=='approved' and __import__('purchase_draft').enabled(conn):
            raise HTTPException(409,'Approved purchase export is not enabled for this Joolan deployment. Use the forecast draft and local financial review; create supplier orders separately.')
        try:rows=final_rows(conn,scenario,season_id)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        if not rows:raise HTTPException(409,'No forecasts have been published.')
        lineage=json.loads(dict(conn.execute('SELECT key,value FROM pipeline_metadata')).get('lineage','{}'))
        if purpose=='approved' and lineage:
            from planning import inputs_fingerprint,input_rows
            state=snapshot_summary(conn)
            meta=dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
            inputs_changed=lineage.get('inputsHash')!=inputs_fingerprint(input_rows(conn))
            source_changed=lineage.get('source') in ('joolan','legacy','combined') and state['forecastSource']!=lineage['source']
            history_changed=(lineage.get('source') in ('joolan','combined') and state.get('importedAt')!=lineage.get('sourceImportedAt')) or meta.get('last_import','')>lineage.get('createdAt','')
            if lineage.get('source') == 'combined':
                from history_store import connection as history_connection, revision
                history_conn = history_connection()
                try:
                    history_changed = history_changed or lineage.get('combinedHistory', {}).get('historyRevision') != revision(history_conn)
                finally:
                    history_conn.close()
            if inputs_changed or source_changed or history_changed:
                raise HTTPException(409,'Selected inputs or history changed. Refresh forecasts before downloading approved quantities.')
        if purpose=='approved' and lineage.get('cancellationsComplete') is False:
            raise HTTPException(409,'Customer-order cancellations are unknown. Supply Cancelled_Quantity on the order lines or export a forecast draft.')
        if purpose=='approved' and not all(not r['decision_required'] or (r['inventory_known'] and r['cost_known'] and r['price_known']) for r in rows):
            raise HTTPException(409,'Approval requires actual stock, incoming quantities, selling prices and purchase costs for every item. You can download a quantity forecast draft.')
        columns=['reference','couleur','taille','scenario','demand_forecast','recommended_quantity','manual_override','final_quantity','purchase_cost','turnover','financial_note']
        data=[{k:r.get(k) for k in columns} for r in rows]
        conn.execute('INSERT INTO audit_log(timestamp,user,action,entity_type,entity_id,details) VALUES(?,?,?,?,?,?)',
            (datetime.datetime.now(datetime.timezone.utc).isoformat(),'local','file_export','recommendations',season_id or 'current',json.dumps(dict(scenario=scenario,purpose=purpose))))
        conn.commit()
        if format=='json':return data
        output=io.StringIO();writer=csv.DictWriter(output,fieldnames=columns);writer.writeheader();writer.writerows(data)
        return StreamingResponse(iter(['\ufeff'+output.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename=recommendations_{scenario}_{purpose}.csv'})
    finally:conn.close()


# ---------------------------------------------------------------------------
# INGEST & FORECAST JOBS
# ---------------------------------------------------------------------------


def _run_forecast_pipeline_job(job_id: str) -> None:
    conn = get_connection()
    try:
        from main import run_phase1

        state=dict(conn.execute('SELECT key,value FROM joolan_state'))
        if state.get('source_policy')=='fresh_only':
            run_phase1()
        else:
            source_path = selected_pipeline_path(conn, BASE_DIR / "data" / "raw" / ".joolan_pipeline.csv")
            run_phase1(data_path=source_path)
        update_job_complete(conn, job_id, 0, 0, 0, None)
    except Exception as ex:
        update_job_complete(conn, job_id, 0, 0, 0, f"{type(ex).__name__}: {ex}\n{traceback.format_exc()}")
    finally:
        conn.commit()
        conn.close()
        global _forecast_pending
        with _forecast_guard:_forecast_pending=False


@app.post("/api/ingest/file")
async def ingest_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not _file_ingest_guard.acquire(blocking=False):raise HTTPException(409,'Another file import is running.')
    job_id = new_job_id()
    conn = None
    append_path=None;backup_path=None;append_existed=False
    try:
        conn = get_connection()
        insert_job_running(conn, job_id, "file")
        conn.commit()

        raw = await file.read()
        name = (file.filename or "").lower()
        buf = io.BytesIO(raw)
        if name.endswith('.xlsx') and is_trade_workbook(raw):
            snapshot = replace_snapshot(conn, read_trade_workbook(raw), 'workbook')
            update_job_complete(conn, job_id, snapshot['rowsAdded'], snapshot['rowsUpdated'], snapshot['rowsSkipped'])
            conn.commit()
            return dict(jobId=job_id,status='complete',rowsAdded=snapshot['rowsAdded'],
                        rowsUpdated=snapshot['rowsUpdated'],rowsSkipped=snapshot['rowsSkipped'],snapshot=snapshot,source='joolan')
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(buf,dtype=str)
        else:
            df = pd.read_csv(buf, low_memory=False,dtype=str)

        df_std, df_parsed = normalize_dataframe(df)
        if df_parsed.empty:
            raise ValueError("No rows left after parsing (check dates and required columns).")

        # Rebuild actuals from the complete deduplicated source, not only the upload.
        from ingestion import _ingest_append_path
        import shutil
        append_path=_ingest_append_path();append_existed=append_path.exists()
        if append_existed:
            backup_path=append_path.with_name('.ingest-backup-'+job_id+'.csv')
            shutil.copyfile(append_path,backup_path)
        append_to_ingest_csv(df_std)
        from ingestion import merge_config_csv_with_append
        merged=merge_config_csv_with_append()
        if merged:
            _,df_parsed=normalize_dataframe(pd.read_csv(merged,dtype=str))
        conn.execute('DELETE FROM client_orders')
        conn.execute('DELETE FROM historical_demand')
        conn.execute('DELETE FROM historical_sku_color')
        conn.execute('DELETE FROM clients')
        stats = dedupe_and_upsert(conn, df_parsed)
        from database import _insert_order_ledger
        _insert_order_ledger(conn,df_parsed)
        refresh_non_ml_aggregates(conn)
        from database import _insert_clients
        from m1_data_preparation import build_client_table
        _insert_clients(conn,build_client_table(df_parsed)[0])
        bump_import_metadata(conn)

        update_job_complete(
            conn,
            job_id,
            stats["added"],
            stats["updated"],
            stats["skipped"],
            None,
        )
        conn.commit()

        return {
            "jobId": job_id,
            "status": "complete",
            "rowsAdded": stats["added"],
            "rowsUpdated": stats["updated"],
            "rowsSkipped": stats["skipped"],
            "byTable": stats.get("by_table", {}),
        }
    except Exception as ex:
        if append_path is not None:
            if backup_path is not None and backup_path.exists():
                import os
                os.replace(backup_path,append_path)
            elif not append_existed:append_path.unlink(missing_ok=True)
        if conn:
            conn.rollback()
            try:
                update_job_complete(conn, job_id, 0, 0, 0, str(ex))
                conn.commit()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    finally:
        if backup_path is not None:backup_path.unlink(missing_ok=True)
        if conn:
            conn.close()
        _file_ingest_guard.release()


class JoolanSyncRequest(BaseModel):
    apiKey: SecretStr
    enseigne: str = Field(default='legend73', min_length=1, max_length=100)
    documentType: str = Field(default='', max_length=100)
    batchSize: int = Field(default=10000, ge=1, le=10000)
    startDate: datetime.date | None = None
    endDate: datetime.date | None = None


class ForecastSourceRequest(BaseModel):
    source: str


class SchemaDiscoveryRequest(BaseModel):
    apiKey: SecretStr
    enseigne: str = Field(min_length=1, max_length=100)


@app.post('/api/joolan/schema')
def inspect_joolan_schema(body: SchemaDiscoveryRequest):
    from discovery import discover_schema
    key = body.apiKey.get_secret_value().strip()
    enseigne = body.enseigne.strip()
    if not key or not enseigne:
        raise HTTPException(400, 'Enter the Joolan enseigne and API key.')
    try:
        return discover_schema(key, enseigne)
    except ValueError as error:
        raise HTTPException(400, str(error).replace(key, '[hidden]')) from None


@app.get('/api/history/profile')
def inspect_historical_csv():
    from discovery import historical_profile
    try:
        return historical_profile()
    except (ValueError, OSError) as error:
        raise HTTPException(400, str(error)) from None


@app.get('/api/history/summary')
def combined_history_summary():
    from history_store import connection, summary
    conn = connection()
    try:
        return summary(conn)
    finally:
        conn.close()


@app.post('/api/history/build')
def build_combined_history():
    from history_store import build
    conn = get_connection()
    try:
        return build(source=conn)
    finally:
        conn.close()


@app.get('/api/history/quarantine')
def history_quarantine(offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500)):
    import zlib
    from history_store import connection
    conn=connection()
    try:
        total=conn.execute('SELECT COUNT(*) FROM history_rows WHERE usable=0').fetchone()[0]
        rows=[dict(source=source,lineKey=key,issues=json.loads(issues),record=json.loads(zlib.decompress(payload)))
              for source,key,issues,payload in conn.execute('SELECT source,line_key,issues,payload FROM history_rows WHERE usable=0 ORDER BY order_date,line_key LIMIT ? OFFSET ?',(limit,offset))]
        return dict(total=total,rows=rows)
    finally:
        conn.close()


_joolan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='joolan')


@app.get('/api/joolan/summary')
def get_joolan_summary():
    conn=get_connection()
    try:
        return snapshot_summary(conn)
    finally:
        conn.close()


@app.get('/api/joolan/orders')
def get_joolan_orders(offset: int = Query(0,ge=0), limit: int = Query(25,ge=1,le=500)):
    conn=get_connection()
    try:
        return dict(rows=snapshot_rows(conn,offset,limit),summary=snapshot_summary(conn))
    finally:
        conn.close()


@app.post('/api/joolan/forecast-source')
def set_joolan_forecast_source(body: ForecastSourceRequest):
    conn=get_connection()
    try:
        return select_forecast_source(conn,body.source)
    except ValueError as error:
        raise HTTPException(status_code=400,detail=str(error)) from None
    finally:
        conn.close()


@app.post('/api/joolan/file')
def import_joolan_file(file: UploadFile = File(...)):
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(status_code=400,detail='Select the Joolan Trade Documents .xlsx workbook.')
    conn=get_connection()
    job_id=new_job_id()
    try:
        insert_job_running(conn,job_id,'joolan-file');conn.commit()
        raw=file.file.read()
        result=replace_snapshot(conn,read_trade_workbook(raw),'workbook')
        update_job_complete(conn,job_id,result['rowsAdded'],result['rowsUpdated'],result['rowsSkipped']);conn.commit()
        return dict(jobId=job_id,status='complete',snapshot=result)
    except Exception as error:
        conn.rollback()
        message=str(error) if isinstance(error,ValueError) else 'Cannot read or save the Joolan workbook. Check its format and available disk space.'
        update_job_complete(conn,job_id,0,0,0,message);conn.commit()
        raise HTTPException(status_code=400,detail=message) from None
    finally:
        conn.close()
        file.file.close()


def _run_joolan_sync(job_id,key,enseigne,document_type,batch,start_date='',end_date=''):
    conn=get_connection()
    try:
        result=replace_snapshot(conn,fetch_trade_rows(key,enseigne,document_type,batch,checkpoint_dir=BASE_DIR/'data'/'joolan_sync',start_date=start_date,end_date=end_date),'query-api',
            scope=dict(enseigne=enseigne,documentType=document_type.strip().upper(),startDate=start_date,endDate=end_date))
        update_job_complete(conn,job_id,result['rowsAdded'],result['rowsUpdated'],result['rowsSkipped'])
    except Exception as error:
        conn.rollback()
        message=str(error).replace(key,'[hidden]') if isinstance(error,ValueError) else 'Joolan sync failed; previous snapshot preserved. Check connectivity and disk space.'
        update_job_complete(conn,job_id,0,0,0,message)
    finally:
        conn.commit();conn.close()


@app.post('/api/joolan/sync')
def sync_joolan(body: JoolanSyncRequest):
    key=body.apiKey.get_secret_value().strip()
    if not key:
        raise HTTPException(status_code=400,detail='Enter the Joolan API key.')
    if body.startDate and body.endDate and body.endDate < body.startDate:
        raise HTTPException(400, 'End date must follow the start date.')
    if body.endDate and body.endDate > datetime.datetime.now(datetime.timezone.utc).date():
        raise HTTPException(400, 'An import end date cannot be in the future.')
    conn=None;job_id=new_job_id()
    try:
        conn=get_connection()
        insert_job_running(conn,job_id,'joolan-api');conn.commit()
    finally:
        conn.close()
    _joolan_executor.submit(_run_joolan_sync,job_id,key,body.enseigne,body.documentType,body.batchSize,
                           body.startDate.isoformat() if body.startDate else '',body.endDate.isoformat() if body.endDate else '')
    return dict(jobId=job_id,status='running')


@app.post("/api/ingest/erp")
def ingest_erp_mock() -> Dict[str, Any]:
    raise HTTPException(status_code=400,detail='Use the Joolan connector or upload a historical file. The demo ERP importer is disabled.')


@app.get("/api/ingest/status/{job_id}")
def get_ingest_status(job_id: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT job_id, job_type, status, rows_added, rows_updated, rows_skipped, error_message, started_at, finished_at
            FROM import_jobs WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "jobId": row[0],
            "jobType": row[1],
            "status": row[2],
            "rowsAdded": row[3],
            "rowsUpdated": row[4],
            "rowsSkipped": row[5],
            "errorMessage": row[6],
            "startedAt": row[7],
            "finishedAt": row[8],
        }
    finally:
        conn.close()


@app.post("/api/forecast/refresh")
def trigger_forecast_refresh() -> Dict[str, Any]:
    global _forecast_pending
    with _forecast_guard:
        if _forecast_pending:raise HTTPException(409,'A forecast refresh is already running.')
        _forecast_pending=True
    conn=get_connection();job_id=new_job_id()
    try:
        from workflow import readiness
        check = readiness(conn)
        if not check['ready']:
            raise HTTPException(409, ' '.join(check['blockers']))
        insert_job_running(conn,job_id,'forecast');conn.commit()
        _forecast_executor.submit(_run_forecast_pipeline_job,job_id)
        return dict(jobId=job_id,status='running')
    except Exception:
        with _forecast_guard:_forecast_pending=False
        raise
    finally:
        if conn:conn.close()


@app.get('/api/forecast/readiness')
def forecast_readiness():
    from workflow import readiness
    conn = get_connection()
    try:
        return readiness(conn)
    finally:
        conn.close()


@app.get("/api/forecast/job")
def get_forecast_job() -> Dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT job_id, status, rows_added, error_message, started_at, finished_at
            FROM import_jobs WHERE job_type = 'forecast'
            ORDER BY started_at DESC LIMIT 1
            """
        ).fetchone()
        meta = conn.execute("SELECT value FROM pipeline_metadata WHERE key = 'last_run'").fetchone()
        last_run = meta[0] if meta else None
        if not row:
            return {
                "jobId": None,
                "status": "idle",
                "lastRun": last_run,
                "errorMessage": None,
                "startedAt": None,
                "finishedAt": None,
            }
        return {
            "jobId": row[0],
            "status": row[1],
            "lastRun": last_run,
            "errorMessage": row[3],
            "startedAt": row[4],
            "finishedAt": row[5],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PIPELINE STATUS & REAL-TIME (SSE)
# ---------------------------------------------------------------------------

@app.get("/api/pipeline/status")
def get_pipeline_status() -> Dict[str, Any]:
    conn = get_connection()
    try:
        meta_row = conn.execute("SELECT value FROM pipeline_metadata WHERE key = 'last_run'").fetchone()
        count_row = conn.execute("SELECT COUNT(*), COUNT(DISTINCT reference || '|' || couleur) FROM recommendations").fetchone()
        return {
            "lastRun": meta_row[0] if meta_row else None,
            "status": "ready" if meta_row else "not_run",
            "totalRecommendations": count_row[0] if count_row else 0,
            "totalSKUs": count_row[1] if count_row else 0,
        }
    except Exception:
        return {"lastRun": None, "status": "error", "totalRecommendations": 0, "totalSKUs": 0}
    finally:
        conn.close()


_last_known_fingerprint: Optional[str] = None


@app.get("/api/events")
async def sse_events():
    """Notify publication and catalogue price/status changes across open pages."""
    global _last_known_fingerprint

    async def event_generator():
        last_known_fingerprint = None
        yield "data: connected\n\n"

        while True:
            try:
                conn = get_connection()
                try:
                    rows = conn.execute(
                        "SELECT key, value FROM pipeline_metadata WHERE key IN ('last_run', 'last_import') ORDER BY key"
                    ).fetchall()
                    catalogue_rows=conn.execute("SELECT key,value FROM planning_state WHERE key IN ('catalogue_status_source','catalogue_status_updated','catalogue_prices_updated','order_price_import') ORDER BY key").fetchall()
                    fp = json.dumps([rows,catalogue_rows])
                finally:
                    conn.close()

                if fp != last_known_fingerprint:
                    last_known_fingerprint = fp
                    payload: Dict[str, Any] = {"lastRun": None, "lastImport": None,"catalogueRevision":json.dumps(catalogue_rows)}
                    for k, v in rows:
                        if k == "last_run":
                            payload["lastRun"] = v
                        elif k == "last_import":
                            payload["lastImport"] = v
                    yield f"event: data-refreshed\ndata: {json.dumps(payload)}\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception:
                yield ": heartbeat\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=4000, reload=True)
