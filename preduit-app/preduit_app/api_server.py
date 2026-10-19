"""
FastAPI bridge between the SQLite serving layer and the Next.js frontend.
Reads from `backend-ai/data/forecast.db` by default (see `preduit_app.client_config`).
"""

import asyncio
import csv
import datetime
import io
import json
import logging
import re
import sqlite3
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fastapi import Depends, FastAPI, Query, Body, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from preduit_app import client_config as config
from preduit_app.auth import AuthUser
from preduit_app.rbac import require_role
from preduit_engine.database import (
    get_connection,
    _create_persistent_tables,
    ensure_pipeline_schema,
    create_season_config,
    get_active_season_config,
    update_season_config,
    list_season_configs,
    get_latest_backtest,
    insert_backtest_job_running,
    complete_backtest_job,
    get_backtest_job,
    count_users,
    create_user,
    get_user_by_email,
    touch_user_login,
    list_users,
    update_user_role,
    get_schema_version,
    check_integrity,
    SCHEMA_VERSION,
)
from preduit_engine.backup import create_backup, list_backups
from preduit_engine.ingestion import (
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

SERVICE_ROOT = config.LEGACY_BACKEND_DIR
_OUTPUT_DIR = Path(config.OUTPUT_DIR)
if not _OUTPUT_DIR.is_absolute():
    _OUTPUT_DIR = SERVICE_ROOT / _OUTPUT_DIR
RECO_PATH = _OUTPUT_DIR / config.OUTPUT_RECOMMENDATIONS_FILE
MONTHLY_PATH = _OUTPUT_DIR / config.OUTPUT_MONTHLY_DETAIL_FILE

_forecast_executor = ThreadPoolExecutor(
    max_workers=config.FORECAST_THREAD_POOL_SIZE, thread_name_prefix="forecast"
)

# Origins allowed for CORS (browser will send Origin: http://localhost:3000)
CORS_ORIGINS_LIST = list(config.CORS_ORIGINS)
CORS_ORIGINS = set(CORS_ORIGINS_LIST)
DEFAULT_CORS_ORIGIN = CORS_ORIGINS_LIST[0] if CORS_ORIGINS_LIST else ""


@asynccontextmanager
async def lifespan(application: FastAPI):
    # Security safety guard: never let the API come up silently unauthenticated
    # without a loud, visible warning in the logs.
    from preduit_app.auth import auth_is_active

    if not auth_is_active():
        _logger = logging.getLogger("preduit.security")
        _logger.warning(
            "=" * 78
            + "\nSECURITY WARNING: authentication is INACTIVE "
            f"(AUTH_ENABLED={config.AUTH_ENABLED}, AUTH_DEV_BYPASS={config.AUTH_DEV_BYPASS}).\n"
            f"Every request is granted a synthetic '{config.AUTH_DEV_ROLE}' user. "
            "This is for local development ONLY.\n"
            "Before client handover set FORECASTER_AUTH_ENABLED=true and "
            "FORECASTER_AUTH_DEV_BYPASS=false.\n"
            + "=" * 78
        )

    conn = get_connection()
    try:
        _create_persistent_tables(conn)
        ensure_pipeline_schema(conn)
        conn.commit()
    finally:
        conn.close()
    yield


app = FastAPI(title="Forcaster Backend API", lifespan=lifespan)


def _cors_headers(origin: Optional[str]) -> dict:
    o = origin if origin and origin in CORS_ORIGINS else DEFAULT_CORS_ORIGIN
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


@app.exception_handler(Exception)
def unhandled_exception_handler(request, exc):
    """Ensure error responses still get CORS headers by returning JSONResponse."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


# Size sort: alpha sizes first, then numeric, then unknown
# TODO: Derive sort keys from preduit_engine.config.SIZE_ORDER_ALPHA (duplication — fix post-refactor).
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
            return "—"

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


# ============================================================================
# AUTHENTICATION — local email/password + Azure SSO status
# ============================================================================

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LEN = 8


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


def _public_user(user: dict) -> Dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name") or "",
        "role": user["role"],
        "status": user.get("status") or "active",
    }


@app.get("/api/auth/config")
def auth_config() -> Dict[str, Any]:
    """Public: tells the frontend which auth methods are available."""
    from preduit_app.auth import auth_is_active

    return {
        "authEnabled": config.AUTH_ENABLED,
        "authActive": auth_is_active(),
        "ssoEnabled": config.SSO_ENABLED,
        "passwordEnabled": True,
        "signupAllowed": config.AUTH_ALLOW_SIGNUP,
        "devMode": not auth_is_active(),
        "devRole": config.AUTH_DEV_ROLE,
        "roles": ["owner", "admin", "manager", "worker"],
    }


@app.post("/api/auth/signup")
def auth_signup(payload: SignupRequest) -> Dict[str, Any]:
    """Register a new local account. The first account created becomes owner;
    every subsequent account defaults to the view-only worker role."""
    from preduit_app.local_auth import hash_password, issue_token

    if not config.AUTH_ALLOW_SIGNUP:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Self sign-up is disabled. Ask an administrator to create your account.")

    email = (payload.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Please enter a valid email address.")
    if len(payload.password or "") < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Password must be at least {_MIN_PASSWORD_LEN} characters.")

    conn = get_connection()
    try:
        if get_user_by_email(conn, email) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        role = "owner" if count_users(conn) == 0 else "worker"
        user = create_user(
            conn,
            email=email,
            name=payload.name or email.split("@")[0],
            password_hash=hash_password(payload.password),
            role=role,
            status="active",
            now=now,
        )
    finally:
        conn.close()

    token = issue_token(user)
    return {"token": token, "user": _public_user(user), "expiresInHours": config.AUTH_TOKEN_TTL_HOURS}


@app.post("/api/auth/login")
def auth_login(payload: LoginRequest) -> Dict[str, Any]:
    """Authenticate a local account and return a session token."""
    from preduit_app.local_auth import issue_token, verify_password

    email = (payload.email or "").strip().lower()
    conn = get_connection()
    try:
        user = get_user_by_email(conn, email)
        if user is None or not verify_password(payload.password or "", user["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")
        if (user.get("status") or "active") != "active":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not active. Contact an administrator.")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        touch_user_login(conn, email, now)
    finally:
        conn.close()

    token = issue_token(user)
    return {"token": token, "user": _public_user(user), "expiresInHours": config.AUTH_TOKEN_TTL_HOURS}


@app.get("/api/auth/me")
def auth_me(user: AuthUser = Depends(require_role("worker"))) -> Dict[str, Any]:
    """Return the currently authenticated user."""
    return {
        "id": user.sub,
        "email": user.email,
        "name": user.display_name,
        "role": user.primary_role,
        "roles": list(user.roles),
    }


class RoleUpdateRequest(BaseModel):
    email: str
    role: str


@app.get("/api/auth/users")
def auth_list_users(user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
    """List local accounts (admin/owner only). SSO-only users are not listed here."""
    conn = get_connection()
    try:
        return {"users": list_users(conn)}
    finally:
        conn.close()


@app.put("/api/auth/users/role")
def auth_update_user_role(
    payload: RoleUpdateRequest,
    user: AuthUser = Depends(require_role("admin")),
) -> Dict[str, Any]:
    """Change a local account's role (admin/owner only)."""
    if payload.role not in ("worker", "manager", "admin", "owner"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role.")

    target_email = (payload.email or "").strip().lower()
    if target_email and target_email == (user.email or "").strip().lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role.")

    conn = get_connection()
    try:
        if get_user_by_email(conn, target_email) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        updated = update_user_role(conn, target_email, payload.role, now)
    finally:
        conn.close()
    return {"user": _public_user(updated)}


@app.get("/api/articles")
def get_articles(
    user: AuthUser = Depends(require_role("manager")),
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
    user: AuthUser = Depends(require_role("worker")),
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


# ---------------------------------------------------------------------------
# CUSTOMER helpers
# ---------------------------------------------------------------------------

_TYPOLOGY_KEY_ACCOUNT_THRESHOLD = 50000  # total_spend >= this => key_account
_TYPOLOGY_CHAIN_THRESHOLD = 15000        # total_spend >= this => chain

def _derive_typology(total_spend: float) -> str:
    if total_spend >= _TYPOLOGY_KEY_ACCOUNT_THRESHOLD:
        return "key_account"
    if total_spend >= _TYPOLOGY_CHAIN_THRESHOLD:
        return "chain"
    return "independent"


def _normalize_region(pays: str, secteur: str) -> str:
    pays_lower = (pays or "").strip().lower()
    if not pays_lower or pays_lower == "france":
        s = (secteur or "").strip()
        return s if s else "France"
    return (pays or "").strip()


def _compute_latest_season(conn) -> Optional[str]:
    row = conn.execute(
        "SELECT season_year, season_type FROM client_orders "
        "WHERE season_year IS NOT NULL ORDER BY season_year DESC, date_commande DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return f"{row[1] or ''}|{int(row[0]) if row[0] else ''}"


def _is_visited(client_id: str, latest_season_key: Optional[str], conn) -> bool:
    if not latest_season_key:
        return False
    parts = latest_season_key.split("|")
    stype, syear = parts[0], parts[1] if len(parts) > 1 else ""
    conditions = ["client_id = ?"]
    params: list = [client_id]
    if syear:
        conditions.append("CAST(season_year AS INTEGER) = ?")
        params.append(int(syear))
    if stype:
        conditions.append("season_type = ?")
        params.append(stype)
    row = conn.execute(
        f"SELECT 1 FROM client_orders WHERE {' AND '.join(conditions)} AND cde_qte > 0 LIMIT 1",
        params,
    ).fetchone()
    return row is not None


def _get_customer_categories(client_id: str, conn, limit: int = 4) -> List[str]:
    rows = conn.execute(
        "SELECT co.reference, r.famille FROM client_orders co "
        "LEFT JOIN recommendations r ON co.reference = r.reference AND co.couleur = r.couleur "
        "WHERE co.client_id = ? AND r.famille IS NOT NULL AND r.famille != '' "
        "GROUP BY r.famille ORDER BY SUM(co.cde_qte) DESC LIMIT ?",
        (client_id, limit),
    ).fetchall()
    return [r[1] for r in rows if r[1]]


def _compute_reorder_frequency(active_months: int, total_months: int) -> int:
    if total_months <= 0 or active_months <= 0:
        return 1
    ratio = active_months / total_months
    if ratio >= 0.6:
        return 4
    if ratio >= 0.35:
        return 3
    if ratio >= 0.15:
        return 2
    return 1


def _compute_similarity(c1: dict, c2: dict) -> float:
    score = 0.0
    if c1.get("region") == c2.get("region"):
        score += 0.3
    if c1.get("typology") == c2.get("typology"):
        score += 0.25
    cats1 = set(c1.get("categories") or [])
    cats2 = set(c2.get("categories") or [])
    if cats1 and cats2:
        overlap = len(cats1 & cats2) / max(len(cats1 | cats2), 1)
        score += 0.25 * overlap
    basket1 = c1.get("avgBasket", 0)
    basket2 = c2.get("avgBasket", 0)
    if basket1 and basket2:
        diff = abs(basket1 - basket2) / max(basket1, basket2, 1)
        score += 0.2 * (1 - diff)
    return round(min(score, 1.0), 3)


def _assign_matches(customers: List[dict]) -> List[dict]:
    visited = [c for c in customers if c["status"] == "visited"]
    if not visited:
        return customers
    # Bucket visited customers by region so each unvisited customer is only compared
    # against same-region candidates (region is the dominant similarity signal). This
    # turns an O(V x N) all-pairs scan into roughly O(N x avg-region-size).
    visited_by_region: Dict[str, List[dict]] = defaultdict(list)
    for v in visited:
        visited_by_region[v.get("region")].append(v)
    for c in customers:
        if c["status"] == "not_visited":
            best_match = None
            best_score = 0.0
            for v in visited_by_region.get(c.get("region"), []):
                s = _compute_similarity(c, v)
                if s > best_score:
                    best_score = s
                    best_match = v
            if best_match and best_score > 0.3:
                c["matchedTo"] = best_match["name"]
                c["similarityScore"] = best_score
                if best_score >= 0.7:
                    c["matchConfidence"] = "high"
                elif best_score >= 0.5:
                    c["matchConfidence"] = "medium"
                else:
                    c["matchConfidence"] = "low"
    return customers


@app.get("/api/customers")
def get_customers(user: AuthUser = Depends(require_role("manager"))) -> Dict[str, Any]:
    conn = get_connection()
    try:
        clients_rows = conn.execute(
            "SELECT client_id, client_name, famille_client, cp, ville, pays, secteur, "
            "total_units, total_spend, num_skus, active_months, first_order, last_order "
            "FROM clients"
        ).fetchall()

        if not clients_rows:
            return {"customers": [], "regions": [], "latestSeason": None}

        latest_season_key = _compute_latest_season(conn)

        total_months_row = conn.execute(
            "SELECT MIN(date_commande), MAX(date_commande) FROM client_orders"
        ).fetchone()
        if total_months_row and total_months_row[0] and total_months_row[1]:
            from datetime import datetime as _dt
            try:
                d1 = _dt.strptime(total_months_row[0][:10], "%Y-%m-%d")
                d2 = _dt.strptime(total_months_row[1][:10], "%Y-%m-%d")
                total_months = max((d2.year - d1.year) * 12 + d2.month - d1.month, 1)
            except Exception:
                total_months = 60
        else:
            total_months = 60

        # ── Set-based aggregates (replaces the previous 3-queries-per-client N+1) ──
        spend_map: Dict[str, tuple] = {}
        for r in conn.execute(
            "SELECT client_id, SUM(COALESCE(cde_net_ht, 0)), SUM(prix * cde_qte), "
            "COUNT(DISTINCT date_commande || reference || couleur) "
            "FROM client_orders GROUP BY client_id"
        ).fetchall():
            spend_map[str(r[0])] = (float(r[1] or 0), float(r[2] or 0), int(r[3] or 0))

        cat_accum: Dict[str, list] = defaultdict(list)
        for r in conn.execute(
            "SELECT co.client_id, r.famille, SUM(co.cde_qte) AS q FROM client_orders co "
            "LEFT JOIN recommendations r ON co.reference = r.reference AND co.couleur = r.couleur "
            "WHERE r.famille IS NOT NULL AND r.famille != '' "
            "GROUP BY co.client_id, r.famille"
        ).fetchall():
            cat_accum[str(r[0])].append((r[1], float(r[2] or 0)))
        cat_top = {
            cid: [f for f, _ in sorted(v, key=lambda x: x[1], reverse=True)[:4]]
            for cid, v in cat_accum.items()
        }

        visited_ids: set = set()
        if latest_season_key:
            _parts = latest_season_key.split("|")
            _stype, _syear = _parts[0], _parts[1] if len(_parts) > 1 else ""
            _conds = ["cde_qte > 0"]
            _vp: list = []
            if _syear:
                _conds.append("CAST(season_year AS INTEGER) = ?")
                _vp.append(int(_syear))
            if _stype:
                _conds.append("season_type = ?")
                _vp.append(_stype)
            for r in conn.execute(
                f"SELECT DISTINCT client_id FROM client_orders WHERE {' AND '.join(_conds)}",
                _vp,
            ).fetchall():
                visited_ids.add(str(r[0]))

        customers: List[dict] = []
        for row in clients_rows:
            cid, cname, famille, cp, ville, pays, secteur, total_units, total_spend, num_skus, active_months, first_order, last_order = row
            cid = str(cid)
            total_spend = float(total_spend or 0)
            active_months = int(active_months or 0)

            spend_row = spend_map.get(cid)
            actual_spend = spend_row[0] if spend_row else 0
            if actual_spend == 0 and spend_row:
                actual_spend = spend_row[1]
            order_count = spend_row[2] if spend_row and spend_row[2] else 1

            if total_spend == 0:
                total_spend = actual_spend

            avg_basket = round(total_spend / max(order_count, 1), 2)
            region = _normalize_region(pays, secteur)
            typology = _derive_typology(total_spend)
            reorder_freq = _compute_reorder_frequency(active_months, total_months)
            categories = cat_top.get(cid, [])
            visited = cid in visited_ids

            customers.append({
                "id": cid,
                "name": str(cname or cid),
                "typology": typology,
                "region": region,
                "categories": categories if categories else ["General"],
                "reorderFrequency": reorder_freq,
                "avgBasket": avg_basket,
                "status": "visited" if visited else "not_visited",
            })

        customers = _assign_matches(customers)
        customers.sort(key=lambda x: x.get("avgBasket", 0), reverse=True)

        regions = sorted(set(c["region"] for c in customers))

        return {"customers": customers, "regions": regions, "latestSeason": latest_season_key}
    finally:
        conn.close()


@app.get("/api/customer-detail")
def get_customer_detail(
    user: AuthUser = Depends(require_role("manager")),
    customer: str = Query(...),
    season: Optional[str] = Query("All"),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        client_row = conn.execute(
            "SELECT client_id, client_name, pays, secteur, total_spend, active_months "
            "FROM clients WHERE client_id = ? OR client_name = ?",
            (customer, customer),
        ).fetchone()
        if not client_row:
            return {"customer": customer, "purchaseHistory": [], "seasons": []}
        cid = str(client_row[0])

        conditions = ["client_id = ?"]
        params: list = [cid]
        if season and str(season).strip() and str(season) != "All":
            conditions.append("season_type || ' ' || CAST(CAST(season_year AS INTEGER) AS TEXT) = ?")
            params.append(season)
        where = " AND ".join(conditions)

        rows = conn.execute(
            f"SELECT reference, couleur, season_type, season_year, "
            f"SUM(cde_qte) as units, SUM(CASE WHEN cde_net_ht > 0 THEN cde_net_ht ELSE prix * cde_qte END) as value "
            f"FROM client_orders WHERE {where} "
            f"GROUP BY reference, couleur, season_type, season_year "
            f"ORDER BY season_year DESC, value DESC",
            params,
        ).fetchall()

        # Bulk-fetch designations once (was one query per purchase-history row).
        designations: Dict[tuple, str] = {}
        for dr in conn.execute(
            "SELECT reference, couleur, MAX(designation) FROM recommendations GROUP BY reference, couleur"
        ).fetchall():
            if dr[2]:
                designations[(dr[0], dr[1])] = dr[2]

        purchase_history = []
        for row in rows:
            ref, couleur, stype, syear, units, value = row
            syear_str = str(int(syear)) if syear else ""
            season_label = f"{stype or ''} {syear_str}".strip()
            sku_name = designations.get((ref, couleur)) or f"{ref} {couleur}"
            purchase_history.append({
                "skuId": str(ref),
                "skuName": str(sku_name),
                "season": season_label,
                "units": int(units or 0),
                "value": round(float(value or 0), 2),
            })

        seasons_rows = conn.execute(
            "SELECT DISTINCT season_type || ' ' || CAST(CAST(season_year AS INTEGER) AS TEXT) "
            "FROM client_orders WHERE client_id = ? AND season_year IS NOT NULL "
            "ORDER BY season_year",
            (cid,),
        ).fetchall()
        seasons = [r[0] for r in seasons_rows if r[0] and r[0].strip()]

    finally:
        conn.close()

    return {
        "customer": customer,
        "purchaseHistory": purchase_history,
        "seasons": seasons,
    }


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
# SEASON CONFIG
# ---------------------------------------------------------------------------

@app.get("/api/season-config")
def get_season_config_endpoint(user: AuthUser = Depends(require_role("manager"))) -> Dict[str, Any]:
    conn = get_connection()
    try:
        active = get_active_season_config(conn)
        all_configs = list_season_configs(conn)
        return {"active": active, "seasons": all_configs}
    finally:
        conn.close()


# ============================================================================
# FINANCIAL HELPERS — season budget bands + configurable cost ratio
# ============================================================================

_SCENARIOS = ("conservative", "base", "optimistic")


def _clamp_cost_ratio(value) -> float:
    """Clamp a cost ratio to a sane 0–0.99 range, falling back to the default."""
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return config.DEFAULT_COST_RATIO
    return min(max(ratio, 0.0), 0.99)


def _season_cost_ratio(season_cfg) -> float:
    """Effective cost ratio for the active season (per-season override or default)."""
    if season_cfg and season_cfg.get("costRatio") is not None:
        return _clamp_cost_ratio(season_cfg["costRatio"])
    return config.DEFAULT_COST_RATIO


def _scenario_budget(season_cfg, scenario: str, fallback_cost: float = 0.0) -> float:
    """Buying budget for a scenario.

    The base-case budget is the value entered on the Season Setup page under
    "Seasonal Buying Budget". Conservative and optimistic budgets are derived
    from it using the configured +/- percentage band. When no budget is set,
    fall back to a multiple of projected purchase cost.
    """
    scenario = scenario if scenario in _SCENARIOS else "base"
    if season_cfg and (season_cfg.get("budget") or 0) > 0:
        base = float(season_cfg["budget"])
        band = float(season_cfg.get("budgetBandPct") or 0) / 100.0
        if scenario == "conservative":
            return max(base * (1 - band), 1)
        if scenario == "optimistic":
            return max(base * (1 + band), 1)
        return max(base, 1)
    return max(fallback_cost * config.BUDGET_MULTIPLIER, 1)


def _all_scenario_budgets(season_cfg, fallback_cost: float = 0.0) -> Dict[str, float]:
    return {s: round(_scenario_budget(season_cfg, s, fallback_cost), 2) for s in _SCENARIOS}


# Budget aggregates only change when the pipeline reruns or the season config is edited,
# so we cache the full response keyed by those inputs to avoid full-table scans per load.
_budget_cache: Dict[tuple, Dict[str, Any]] = {}


def _pipeline_last_run(conn) -> str:
    try:
        row = conn.execute(
            "SELECT value FROM pipeline_metadata WHERE key = 'last_run'"
        ).fetchone()
        return row[0] if row else ""
    except Exception:
        return ""


def _season_signature(season_cfg) -> tuple:
    cfg = season_cfg or {}
    return (
        round(float(cfg.get("budget") or 0), 2),
        float(cfg.get("budgetBandPct") or 0),
        _season_cost_ratio(season_cfg),
    )


@app.post("/api/season-config")
def create_season_config_endpoint(
    body: Dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    import uuid
    conn = get_connection()
    try:
        season_id = body.get("id") or f"season-{uuid.uuid4().hex[:12]}"
        name = body.get("name", "Untitled Season")
        currency = body.get("currency", "EUR")
        budget = float(body.get("budget", 0))
        target_margin = float(body.get("targetMargin", 50))
        budget_band_pct = float(body.get("budgetBandPct", 15))
        cost_ratio = _clamp_cost_ratio(body.get("costRatio", 0.5))
        create_season_config(
            conn, season_id, name, currency, budget, target_margin,
            budget_band_pct=budget_band_pct, cost_ratio=cost_ratio,
        )
        active = get_active_season_config(conn)
        return active
    finally:
        conn.close()


@app.patch("/api/season-config/{season_id}")
def update_season_config_endpoint(
    season_id: str,
    body: Dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        kwargs = {}
        if "name" in body:
            kwargs["name"] = body["name"]
        if "currency" in body:
            kwargs["currency"] = body["currency"]
        if "budget" in body:
            kwargs["budget"] = float(body["budget"])
        if "targetMargin" in body:
            kwargs["target_margin"] = float(body["targetMargin"])
        if "budgetBandPct" in body:
            kwargs["budget_band_pct"] = float(body["budgetBandPct"])
        if "costRatio" in body:
            kwargs["cost_ratio"] = _clamp_cost_ratio(body["costRatio"])
        if "status" in body:
            kwargs["status"] = body["status"]
        update_season_config(conn, season_id, **kwargs)
        active = get_active_season_config(conn)
        return active or {}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard(user: AuthUser = Depends(require_role("worker"))) -> Dict[str, Any]:
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
        expected_turnover = row[4] or 0
        total_clients = row[6] or 0

        # Cost & margin are estimated from the season's configurable cost ratio.
        season_cfg = get_active_season_config(conn)
        cost_ratio = _season_cost_ratio(season_cfg)
        total_purchase_cost = expected_turnover * cost_ratio
        gross_margin = expected_turnover - total_purchase_cost

        risk_row = conn.execute(
            "SELECT COUNT(DISTINCT reference || '|' || couleur) FROM recommendations WHERE LOWER(confidence) = 'low'"
        ).fetchone()
        risk_count = risk_row[0] if risk_row else 0

        coverage_row = conn.execute("""
            SELECT COUNT(DISTINCT client) FROM recommendations
            WHERE confirmed_orders > 0 AND client IS NOT NULL AND client != ''
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
            SELECT confidence, COUNT(DISTINCT reference || '|' || couleur)
            FROM recommendations GROUP BY confidence
        """).fetchall()
        confidence_dist = {_normalize_confidence(r[0]): r[1] for r in conf_rows if r[0]}

        # Base-case buying budget (from Season Setup); conservative/optimistic derive from it.
        season_budget = _scenario_budget(season_cfg, "base", total_purchase_cost)
        target_margin_display = season_cfg["targetMargin"] if season_cfg else config.TARGET_MARGIN_DISPLAY

        kpis = [
            {"label": "Total Forecast Units", "value": f"{total_forecast:,}", "subLabel": f"{total_skus} SKUs", "trend": "neutral", "trendValue": 0},
            {"label": "Confirmed Orders", "value": f"{total_confirmed:,}", "subLabel": f"{round(total_confirmed / total_forecast * 100)}% of forecast" if total_forecast > 0 else "0%", "trend": "up", "trendValue": round(total_confirmed / total_forecast * 100, 1) if total_forecast > 0 else 0},
            {"label": "Budget Usage", "value": f"{round(total_purchase_cost / season_budget * 100)}%", "subLabel": f"${total_purchase_cost:,.0f} / ${season_budget:,.0f}", "trend": "neutral", "trendValue": round(total_purchase_cost / season_budget * 100, 1)},
            {"label": "Gross Margin", "value": f"{margin_pct}%", "subLabel": f"${gross_margin:,.0f}", "trend": "up" if margin_pct >= 40 else "down", "trendValue": margin_pct},
            {"label": "Client Coverage", "value": f"{coverage}%", "subLabel": f"{visited_clients} / {total_clients} clients", "trend": "up" if coverage >= 70 else "down", "trendValue": coverage},
            {"label": "Risk Items", "value": str(risk_count), "subLabel": "Low-confidence SKUs", "trend": "down" if risk_count > 10 else "up", "trendValue": risk_count},
        ]

        financial_summary = {
            "budgetUsed": total_purchase_cost,
            "budgetTotal": season_budget,
            "margin": margin_pct,
            "targetMargin": target_margin_display,
            "coverage": coverage,
            "totalPurchaseCost": total_purchase_cost,
            "expectedTurnover": expected_turnover,
            "costRatio": cost_ratio,
            "costEstimated": True,
            "budgetsByScenario": _all_scenario_budgets(season_cfg, total_purchase_cost),
        }

        return {
            "kpis": kpis,
            "financialSummary": financial_summary,
            "confidenceDistribution": confidence_dist,
            "lastPipelineRun": last_run,
            "totalSKUs": total_skus,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PRODUCTS
# ---------------------------------------------------------------------------

@app.get("/api/products")
def get_products(
    user: AuthUser = Depends(require_role("worker")),
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
                MAX(confidence) AS confidence,
                MAX(diffusion_rate) AS diffusion_rate,
                MAX(depth_per_client) AS depth_per_client,
                MAX(reorder_rate) AS reorder_rate,
                MAX(total_buying_clients) AS total_buying_clients,
                COALESCE(SUM(forecast_base), 0) AS total_units_sold,
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

            designation = r.get("designation") or r["reference"]
            products.append({
                "skuId": f"{r['reference']}|{r['couleur']}",
                "name": designation,
                "style": designation,
                "category": r.get("famille") or "Unknown",
                "status": r.get("product_status") or "core",
                "season": r.get("saison") or "",
                "diffusionRate": round(float(r.get("diffusion_rate") or 0), 4),
                "depthPerCustomer": round(float(r.get("depth_per_client") or 0), 2),
                "reorderRate": round(float(r.get("reorder_rate") or 0), 4),
                "totalUnitsSold": int(r.get("total_units_sold") or 0),
                "buyingCustomers": int(r.get("total_buying_clients") or 0),
                "sizeBreakdown": size_breakdown,
                "aiConfidence": _normalize_confidence(r.get("confidence")),
            })

        return products
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PROJECTIONS
# ---------------------------------------------------------------------------

@app.get("/api/projections")
def get_projections(
    user: AuthUser = Depends(require_role("worker")),
    season: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
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
                MAX(confidence) AS confidence,
                COALESCE(SUM(confirmed_orders), 0) AS confirmed,
                COALESCE(SUM(probable_additional_base), 0) AS probable_reorders,
                COALESCE(SUM(forecast_base) - SUM(confirmed_orders) - SUM(probable_additional_base), 0) AS non_visited_projection,
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
            confirmed = int(r.get("confirmed") or 0)
            reorders = int(r.get("probable_reorders") or 0)
            non_visited = max(0, int(r.get("non_visited_projection") or 0))
            total_base = int(r.get("total_base") or 0)
            total_conservative = int(r.get("total_conservative") or 0)
            total_optimistic = int(r.get("total_optimistic") or 0)

            conf_level = _normalize_confidence(r.get("confidence"))
            dr = float(r.get("diffusion_rate") or 0)
            dpc = float(r.get("depth_per_client") or 0)
            cc = int(r.get("customer_count") or 0)
            rr = float(r.get("reorder_rate") or 0)

            projections.append({
                "skuId": f"SKU-{r['reference']}",
                "skuName": r.get("designation") or r["reference"],
                "category": r.get("category") or "Unknown",
                "scenarios": {
                    "conservative": {
                        "confirmed": confirmed,
                        "probableReorders": int(reorders * 0.85),
                        "nonVisitedProjection": int(non_visited * 0.85),
                        "total": total_conservative,
                    },
                    "base": {
                        "confirmed": confirmed,
                        "probableReorders": reorders,
                        "nonVisitedProjection": non_visited,
                        "total": total_base,
                    },
                    "optimistic": {
                        "confirmed": confirmed,
                        "probableReorders": int(reorders * 1.15),
                        "nonVisitedProjection": int(non_visited * 1.15),
                        "total": total_optimistic,
                    },
                },
                "confidence": conf_level,
                "explainability": {
                    "confirmedOrders": {"units": confirmed, "customerCount": cc},
                    "probableReorders": {"units": reorders, "reorderRate": round(rr, 3), "likelyCustomers": max(1, int(cc * rr)) if rr > 0 else 0},
                    "nonVisitedDemand": {"units": non_visited, "matchedCustomers": max(0, cc - int(cc * rr)) if rr < 1 else 0, "clusterProfile": "Based on ML model"},
                    "keySignals": {"diffusionRate": round(dr, 4), "depthPerCustomer": round(dpc, 2), "customerCluster": "ML-assigned", "scenarioMultiplier": 1.0},
                },
            })

        return projections
    finally:
        conn.close()


@app.get("/api/projections/{reference}/detail")
def get_projection_detail(
    reference: str,
    user: AuthUser = Depends(require_role("worker")),
) -> Dict[str, Any]:
    """Return detailed color x size matrix for a single reference (SKU). Matches SKUDetailedProjection type."""
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT
                reference, couleur, taille, saison, fournisseur, famille, theme, modele,
                designation, rayon, matiere, confidence,
                COALESCE(confirmed_orders, 0) AS confirmed_orders,
                COALESCE(confirmed_delivered, 0) AS confirmed_delivered,
                COALESCE(forecast_base, 0) AS forecast_base,
                COALESCE(current_stock, 0) AS current_stock,
                COALESCE(pipeline_stock, 0) AS pipeline_stock,
                COALESCE(net_to_order_base, 0) AS net_to_order_base
            FROM recommendations
            WHERE reference = ?
            ORDER BY couleur, taille
        """, (reference,))

        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return {"error": "Reference not found", "skuId": reference}

        first = rows[0]
        product_info = {
            "reference": first["reference"],
            "name": first.get("designation") or first["reference"],
            "matiere": first.get("matiere") or "",
            "theme": first.get("theme") or "",
            "famille": first.get("famille") or "",
            "sousFamille": first.get("modele") or "",
            "rayon": first.get("rayon") or "",
            "saison": first.get("saison") or "",
        }

        total_forecast = sum(int(r["forecast_base"]) for r in rows)
        total_supplier_order = sum(int(r["pipeline_stock"]) for r in rows)
        total_stock = sum(int(r["current_stock"]) for r in rows)
        stock_summary = {
            "forecastedQuantity": total_forecast,
            "supplierOrder": total_supplier_order,
            "stock": total_stock,
            "total": total_forecast + total_supplier_order - total_stock,
        }

        by_color: Dict[str, List[Dict]] = defaultdict(list)
        for r in rows:
            by_color[r["couleur"]].append(r)

        color_variants = []
        for color, color_rows in by_color.items():
            produit: Dict[str, int] = {}
            forecasted: Dict[str, int] = {}
            fournisseur: Dict[str, int] = {}
            cit_negoce: Dict[str, int] = {}
            le_stock: Dict[str, int] = {}

            for r in color_rows:
                size = str(r["taille"])
                produit[size] = int(r["confirmed_orders"])
                forecasted[size] = int(r["forecast_base"])
                fournisseur[size] = int(r["pipeline_stock"])
                cit_negoce[size] = int(r["confirmed_delivered"])
                le_stock[size] = int(r["net_to_order_base"])

            color_variants.append({
                "color": color,
                "totalDeProduit": produit,
                "forecastedQuantity": forecasted,
                "totalDeFournisseur": fournisseur,
                "totalDeCitNegoce": cit_negoce,
                "totalDeLeStock": le_stock,
            })

        conf = _normalize_confidence(first.get("confidence"))

        size_columns = _sort_sizes(list({
            size
            for variant in color_variants
            for metric in (
                variant["totalDeProduit"],
                variant["forecastedQuantity"],
                variant["totalDeFournisseur"],
                variant["totalDeCitNegoce"],
                variant["totalDeLeStock"],
            )
            for size in metric.keys()
        }))

        return {
            "skuId": f"SKU-{reference}",
            "skuName": product_info["name"],
            "category": product_info["famille"],
            "productInfo": product_info,
            "stockSummary": stock_summary,
            "colorVariants": color_variants,
            "sizeColumns": size_columns,
            "confidence": conf,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BUDGET
# ---------------------------------------------------------------------------

@app.get("/api/budget")
def get_budget(
    user: AuthUser = Depends(require_role("manager")),
    scenario: Optional[str] = Query("base"),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        scenario_col_map = {
            "conservative": ("forecast_conservative", "estimated_cost_conservative", "expected_revenue_conservative"),
            "base": ("forecast_base", "estimated_cost_base", "expected_revenue_base"),
            "optimistic": ("forecast_optimistic", "estimated_cost_optimistic", "expected_revenue_optimistic"),
        }
        fcst_col, cost_col, rev_col = scenario_col_map.get(scenario or "base", scenario_col_map["base"])

        # Serve from cache when nothing that affects budget has changed.
        season_cfg = get_active_season_config(conn)
        _cache_key = (scenario or "base", _pipeline_last_run(conn), _season_signature(season_cfg))
        _cached = _budget_cache.get(_cache_key)
        if _cached is not None:
            return _cached

        row = conn.execute(f"""
            SELECT
                COALESCE(SUM({cost_col}), 0),
                COALESCE(SUM({rev_col}), 0),
                COALESCE(SUM(estimated_margin_base), 0)
            FROM recommendations
        """).fetchone()
        total_revenue = row[1] or 0
        cost_ratio = _season_cost_ratio(season_cfg)
        # Cost & margin estimated from the season's configurable cost ratio.
        total_cost = total_revenue * cost_ratio
        total_margin = total_revenue - total_cost
        # Budget for THIS scenario, derived from the base-case Season Setup budget.
        season_budget = _scenario_budget(season_cfg, scenario or "base", total_cost)
        target_margin_display = season_cfg["targetMargin"] if season_cfg else config.TARGET_MARGIN_DISPLAY
        margin_pct = round(total_margin / total_revenue * 100, 1) if total_revenue > 0 else 0

        summary = {
            "totalPurchaseCost": round(total_cost, 2),
            "seasonBudget": round(season_budget, 2),
            "expectedTurnover": round(total_revenue, 2),
            "grossMargin": round(total_margin, 2),
            "grossMarginPercent": margin_pct,
            "scenario": scenario or "base",
            "costRatio": cost_ratio,
            "costEstimated": True,
            "budgetsByScenario": _all_scenario_budgets(season_cfg, total_cost),
        }

        cat_cursor = conn.execute(f"""
            SELECT
                COALESCE(famille, 'Other') AS category,
                COALESCE(SUM({cost_col}), 0) AS purchase_cost,
                COALESCE(SUM({rev_col}), 0) AS revenue,
                COALESCE(SUM(estimated_margin_base), 0) AS margin
            FROM recommendations
            GROUP BY famille
            ORDER BY SUM({cost_col}) DESC
        """)
        categories = []
        for cat_row in cat_cursor.fetchall():
            cat_name = cat_row[0] or "Other"
            cat_revenue = cat_row[2] or 0
            cat_cost = cat_revenue * cost_ratio
            cat_margin = cat_revenue - cat_cost
            cat_margin_pct = round(cat_margin / cat_revenue * 100, 1) if cat_revenue > 0 else 0
            budget_pct = round(cat_cost / season_budget * 100, 1) if season_budget > 0 else 0

            if cat_margin_pct >= 40:
                cat_status = "on_target"
            elif budget_pct > 100 / max(len(categories) + 1, 1) * 1.5:
                cat_status = "over_budget"
            else:
                cat_status = "below_margin"

            sku_cursor = conn.execute(f"""
                SELECT
                    reference, MAX(designation) AS name,
                    COALESCE(SUM({cost_col}), 0) AS sku_cost,
                    COALESCE(SUM(estimated_margin_base), 0) AS sku_margin,
                    COALESCE(SUM({rev_col}), 0) AS sku_revenue
                FROM recommendations
                WHERE famille = ?
                GROUP BY reference
                ORDER BY SUM({cost_col}) DESC
                LIMIT 20
            """, (cat_name,))

            skus = []
            for sr in sku_cursor.fetchall():
                sr_rev = sr[4] or 0
                sr_cost = sr_rev * cost_ratio
                sr_margin = sr_rev - sr_cost
                skus.append({
                    "skuId": sr[0],
                    "name": sr[1] or sr[0],
                    "purchaseCost": round(sr_cost, 2),
                    "margin": round(sr_margin / sr_rev * 100, 1) if sr_rev > 0 else 0,
                    "targetMargin": target_margin_display,
                })

            categories.append({
                "category": cat_name,
                "purchaseCost": round(cat_cost, 2),
                "budgetPercent": budget_pct,
                "marginPercent": cat_margin_pct,
                "status": cat_status,
                "skus": skus,
            })

        result = {"summary": summary, "categories": categories}
        _budget_cache[_cache_key] = result
        # Keep the cache tiny (3 scenarios × a couple of configs).
        if len(_budget_cache) > 24:
            _budget_cache.clear()
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# RECOMMENDATIONS
# ---------------------------------------------------------------------------

@app.get("/api/recommendations")
def get_recommendations(
    user: AuthUser = Depends(require_role("manager")),
    season: Optional[str] = Query(None),
    scenario: Optional[str] = Query("base"),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
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
                MAX(r.confidence) AS confidence,
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
            for lr in conn.execute("SELECT reference, couleur, locked FROM sku_locks").fetchall():
                locks[(lr[0], lr[1])] = bool(lr[2])
        except Exception:
            pass

        # Bulk-fetch sizes and overrides ONCE (previously 2 queries per grouped row).
        sizes_by_key: Dict[tuple, list] = defaultdict(list)
        for sr in conn.execute(
            "SELECT reference, couleur, taille, COALESCE(forecast_base, 0), "
            "COALESCE(net_to_order_base, 0) FROM recommendations "
            "ORDER BY reference, couleur, taille"
        ).fetchall():
            sizes_by_key[(sr[0], sr[1])].append((sr[2], int(sr[3] or 0)))

        overrides_by_key: Dict[tuple, dict] = defaultdict(dict)
        try:
            for ovr in conn.execute(
                "SELECT reference, couleur, taille, override_qty FROM user_overrides "
                "ORDER BY updated_at DESC"
            ).fetchall():
                d = overrides_by_key[(ovr[0], ovr[1])]
                if ovr[2] not in d:
                    d[ovr[2]] = ovr[3]
        except Exception:
            pass

        results = []
        for g in grouped_rows:
            ref, coul = g["reference"], g["couleur"]

            size_rows = sizes_by_key.get((ref, coul), [])
            override_map = overrides_by_key.get((ref, coul), {})

            size_breakdown = []
            for sr in size_rows:
                taille = sr[0]
                recommended = int(sr[1])
                override = override_map.get(taille)
                final_qty = int(override) if override is not None else recommended
                size_breakdown.append({
                    "size": taille,
                    "recommended": recommended,
                    "manualOverride": int(override) if override is not None else None,
                    "finalQty": final_qty,
                    "minUnits": None,
                    "maxUnits": None,
                    "blocked": False,
                    "rounding": None,
                })

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
            budget_impact = round(cost_val / max(cost_val * 50, 1) * 100, 2)

            results.append({
                "skuId": f"{ref}|{coul}",
                "skuName": f"{g.get('designation') or ref} — {coul}",
                "category": g.get("famille") or "Unknown",
                "status": rec_status,
                "locked": is_locked,
                "scenarios": {
                    "conservative": {"confirmed": confirmed, "probableReorders": 0, "nonVisitedProjection": 0, "total": fc},
                    "base": {"confirmed": confirmed, "probableReorders": 0, "nonVisitedProjection": 0, "total": fb},
                    "optimistic": {"confirmed": confirmed, "probableReorders": 0, "nonVisitedProjection": 0, "total": fo},
                },
                "currentScenarioTotal": fb,
                "sizeBreakdown": size_breakdown,
                "confidence": _normalize_confidence(g.get("confidence")),
                "explainability": {
                    "confirmedOrders": {"units": confirmed, "customerCount": int(g.get("bc") or 0)},
                    "probableReorders": {"units": 0, "reorderRate": round(float(g.get("rr") or 0), 3), "likelyCustomers": 0},
                    "nonVisitedDemand": {"units": 0, "matchedCustomers": 0, "clusterProfile": "ML-assigned"},
                    "keySignals": {"diffusionRate": round(float(g.get("dr") or 0), 4), "depthPerCustomer": round(float(g.get("dpc") or 0), 2), "customerCluster": "ML-assigned", "scenarioMultiplier": 1.0},
                },
                "financialImpact": {
                    "purchaseCost": round(cost_val, 2),
                    "expectedTurnover": round(revenue_val, 2),
                    "grossMargin": round(margin_val, 2),
                    "marginPercent": margin_pct,
                    "budgetImpactPercent": budget_impact,
                },
            })

        return results
    finally:
        conn.close()


@app.put("/api/recommendations/{reference}/{couleur}")
def update_recommendation(
    reference: str,
    couleur: str,
    body: Dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        now = datetime.datetime.utcnow().isoformat()
        size_breakdown = body.get("sizeBreakdown", [])
        reason = body.get("reason", "")
        notes = body.get("notes", "")
        audit_user = user.display_name

        for sb in size_breakdown:
            taille = sb.get("size", "")
            override_qty = sb.get("finalQty", sb.get("override_qty", 0))
            conn.execute(
                "INSERT INTO user_overrides (reference, couleur, taille, override_qty, reason, notes, user, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (reference, couleur, taille, int(override_qty), reason, notes, audit_user, now, now),
            )

        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, previous_value, new_value, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, audit_user, "override", "recommendation", f"{reference}|{couleur}", reference, "", json.dumps(size_breakdown), notes),
        )
        conn.commit()
        return {"status": "ok", "reference": reference, "couleur": couleur, "overridesApplied": len(size_breakdown)}
    finally:
        conn.close()


@app.post("/api/recommendations/{reference}/{couleur}/lock")
def lock_recommendation(
    reference: str,
    couleur: str,
    body: Dict[str, Any] = Body(default={}),
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        now = datetime.datetime.utcnow().isoformat()
        audit_user = user.display_name
        conn.execute(
            "INSERT OR REPLACE INTO sku_locks (reference, couleur, locked, locked_by, locked_at) VALUES (?, ?, 1, ?, ?)",
            (reference, couleur, audit_user, now),
        )
        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, audit_user, "lock", "recommendation", f"{reference}|{couleur}", reference, "Locked"),
        )
        conn.commit()
        return {"status": "locked", "reference": reference, "couleur": couleur}
    finally:
        conn.close()


@app.post("/api/recommendations/{reference}/{couleur}/unlock")
def unlock_recommendation(
    reference: str,
    couleur: str,
    body: Dict[str, Any] = Body(default={}),
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        now = datetime.datetime.utcnow().isoformat()
        audit_user = user.display_name
        conn.execute(
            "INSERT OR REPLACE INTO sku_locks (reference, couleur, locked, locked_by, locked_at) VALUES (?, ?, 0, ?, ?)",
            (reference, couleur, audit_user, now),
        )
        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, audit_user, "unlock", "recommendation", f"{reference}|{couleur}", reference, "Unlocked"),
        )
        conn.commit()
        return {"status": "unlocked", "reference": reference, "couleur": couleur}
    finally:
        conn.close()


class RevertOverrideRequest(BaseModel):
    reference: str
    couleur: Optional[str] = None
    taille: Optional[str] = None


@app.post("/api/overrides/revert")
def revert_override(
    payload: RevertOverrideRequest,
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    """Remove a manual override: a single size, or all sizes for a reference/couleur."""
    conn = get_connection()
    try:
        conds = ["reference = ?"]
        params: list = [payload.reference]
        if payload.couleur is not None:
            conds.append("couleur = ?")
            params.append(payload.couleur)
        if payload.taille is not None:
            conds.append("taille = ?")
            params.append(payload.taille)
        cur = conn.execute(
            f"DELETE FROM user_overrides WHERE {' AND '.join(conds)}", params
        )
        removed = cur.rowcount
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, user.display_name, "revert_override", "recommendation",
             f"{payload.reference}|{payload.couleur or ''}", payload.reference,
             f"Reverted {removed} override(s)"),
        )
        conn.commit()
        return {"status": "ok", "reverted": removed}
    finally:
        conn.close()


@app.post("/api/overrides/revert-all")
def revert_all_overrides(user: AuthUser = Depends(require_role("manager"))) -> Dict[str, Any]:
    """Remove ALL manual overrides in one action."""
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM user_overrides")
        removed = cur.rowcount
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, entity_name, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, user.display_name, "revert_all_overrides", "recommendation", "*", "All",
             f"Reverted {removed} override(s)"),
        )
        conn.commit()
        return {"status": "ok", "reverted": removed}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# VALIDATION & AUDIT
# ---------------------------------------------------------------------------

@app.get("/api/validation")
def get_validation(
    user: AuthUser = Depends(require_role("manager")),
    scenario: Optional[str] = Query("base"),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        season_cfg = get_active_season_config(conn)
        cost_ratio = _season_cost_ratio(season_cfg)
        scenarios_data = {}
        for sc, (fcst_col, rev_col) in [
            ("conservative", ("forecast_conservative", "expected_revenue_conservative")),
            ("base", ("forecast_base", "expected_revenue_base")),
            ("optimistic", ("forecast_optimistic", "expected_revenue_optimistic")),
        ]:
            row = conn.execute(f"""
                SELECT
                    COALESCE(SUM({fcst_col}), 0),
                    COALESCE(SUM({rev_col}), 0)
                FROM recommendations
            """).fetchone()
            total_units = int(row[0] or 0)
            revenue = float(row[1] or 0)
            # Cost & margin estimated from the season's configurable cost ratio.
            purchase_cost = revenue * cost_ratio
            margin = revenue - purchase_cost
            # Each scenario's budget derives from the base-case Season Setup budget.
            season_budget = _scenario_budget(season_cfg, sc, purchase_cost)

            risk_row = conn.execute(
                "SELECT COUNT(DISTINCT reference || '|' || couleur) FROM recommendations WHERE LOWER(confidence) = 'low'"
            ).fetchone()

            scenarios_data[sc] = {
                "totalUnits": total_units,
                "purchaseCost": round(purchase_cost, 2),
                "seasonBudget": round(season_budget, 2),
                "budgetUsage": round(purchase_cost / season_budget * 100, 1),
                "grossMargin": round(margin / revenue * 100, 1) if revenue > 0 else 0,
                "costEstimated": True,
                "skusAtRisk": risk_row[0] if risk_row else 0,
            }

        override_cursor = conn.execute("""
            SELECT uo.reference, uo.couleur, uo.taille, uo.override_qty, uo.reason, uo.notes,
                   r.forecast_base
            FROM user_overrides uo
            LEFT JOIN recommendations r ON r.reference = uo.reference AND r.couleur = uo.couleur AND r.taille = uo.taille
            ORDER BY uo.updated_at DESC
        """)
        overrides = []
        seen = set()
        for ovr in override_cursor.fetchall():
            key = f"{ovr[0]}|{ovr[1]}|{ovr[2]}"
            if key in seen:
                continue
            seen.add(key)
            overrides.append({
                "skuId": ovr[0],
                "skuName": ovr[0],
                "reference": ovr[0],
                "couleur": ovr[1],
                "taille": ovr[2],
                "aiRecommended": int(ovr[6] or 0),
                "userOverride": int(ovr[3] or 0),
                "reasonTag": ovr[4] or "",
                "notes": ovr[5] or "",
            })

        return {
            "scenarioMetrics": scenarios_data,
            "overrides": overrides[:50],
        }
    finally:
        conn.close()


@app.get("/api/audit")
def get_audit(
    user: AuthUser = Depends(require_role("manager")),
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


@app.post("/api/export")
def export_recommendations(
    user: AuthUser = Depends(require_role("manager")),
    format: Optional[str] = Query("csv"),
) -> Any:
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT reference, couleur, taille, saison, fournisseur, famille, theme, modele,
                   forecast_conservative, forecast_base, forecast_optimistic,
                   confirmed_orders, current_stock, pipeline_stock,
                   net_to_order_conservative, net_to_order_base, net_to_order_optimistic,
                   avg_price, estimated_cost_base, expected_revenue_base, estimated_margin_base,
                   confidence, explanation
            FROM recommendations
            ORDER BY reference, couleur, taille
        """)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()

        if format == "json":
            data = [dict(zip(columns, row)) for row in rows]
            return data

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        writer.writerows(rows)
        output.seek(0)

        now = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        conn2 = get_connection()
        try:
            conn2.execute(
                "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.datetime.utcnow().isoformat(), "system", "export", "recommendations", "all", f"format={format}"),
            )
            conn2.commit()
        finally:
            conn2.close()

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=recommendations_{now}.csv"},
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# INGEST & FORECAST JOBS
# ---------------------------------------------------------------------------


def _run_forecast_pipeline_job(job_id: str) -> None:
    conn = get_connection()
    try:
        from preduit_app.main import run_phase1

        run_phase1()
        update_job_complete(conn, job_id, 0, 0, 0, None)
    except Exception as ex:
        update_job_complete(conn, job_id, 0, 0, 0, f"{type(ex).__name__}: {ex}\n{traceback.format_exc()}")
    finally:
        conn.commit()
        conn.close()


@app.post("/api/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_role("admin")),
) -> Dict[str, Any]:
    job_id = new_job_id()
    conn = None
    try:
        conn = get_connection()
        insert_job_running(conn, job_id, "file")
        conn.commit()

        raw = await file.read()
        name = (file.filename or "").lower()
        buf = io.BytesIO(raw)
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(buf)
        else:
            df = pd.read_csv(buf, low_memory=False)

        df_std, df_parsed = normalize_dataframe(df)
        if df_parsed.empty:
            raise ValueError("No rows left after parsing (check dates and required columns).")

        stats = dedupe_and_upsert(conn, df_parsed)
        refresh_non_ml_aggregates(conn)
        append_to_ingest_csv(df_std)
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
        if conn:
            try:
                update_job_complete(conn, job_id, 0, 0, 0, str(ex))
                conn.commit()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    finally:
        if conn:
            conn.close()


# ============================================================================
# ADMIN — database durability (backups + health)
# ============================================================================

@app.get("/api/admin/db/health")
def db_health(user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
    """Schema version + integrity check for the serving database."""
    conn = get_connection()
    try:
        recorded = get_schema_version(conn)
        return {
            "schemaVersion": recorded,
            "expectedSchemaVersion": SCHEMA_VERSION,
            "schemaUpToDate": recorded == SCHEMA_VERSION,
            "integrityOk": check_integrity(conn),
            "dbPath": str(config.DB_PATH),
        }
    finally:
        conn.close()


@app.get("/api/admin/db/backups")
def db_list_backups(user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
    return {"backups": list_backups()}


@app.post("/api/admin/db/backup")
def db_create_backup(user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
    """Take a consistent online backup of the serving database."""
    try:
        return create_backup()
    except Exception as ex:
        raise HTTPException(status_code=400, detail=f"Backup failed: {ex}") from ex


@app.get("/api/ingest/erp/status")
def get_erp_status(user: AuthUser = Depends(require_role("manager"))) -> Dict[str, Any]:
    """Tell the UI whether the ERP is connected or the button will fall back to sample data."""
    configured = config.erp_is_configured()
    return {
        "enabled": config.ERP_ENABLED,
        "configured": configured,
        "hasHistoryQuery": bool(config.ERP_HISTORY_SQL),
        "baseUrl": config.ERP_BASE_URL if configured else None,
        "enseigne": config.ERP_ENSEIGNE if configured else None,
        "mode": "erp" if configured else "sample",
        "provider": "Joolan / Lisa",
    }


def _load_erp_dataframe() -> tuple:
    """Return (dataframe, mode). Uses the real Joolan connector when configured;
    otherwise falls back to the bundled sample data so the manual button still works."""
    if config.erp_is_configured():
        from preduit_engine.erp_joolan import JoolanClient

        client = JoolanClient(
            base_url=config.ERP_BASE_URL,
            enseigne=config.ERP_ENSEIGNE,
            api_key=config.ERP_API_KEY,
            magasins=config.ERP_MAGASINS,
        )
        if not config.ERP_HISTORY_SQL:
            raise HTTPException(
                status_code=400,
                detail="ERP is connected but no history query is set (FORECASTER_ERP_HISTORY_SQL).",
            )
        return client.fetch_sales_history(config.ERP_HISTORY_SQL), "erp"
    # Fallback: bundled sample data.
    return load_mock_erp_dataframe(), "sample"


@app.post("/api/ingest/erp")
def ingest_erp(user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
    job_id = new_job_id()
    conn = get_connection()
    try:
        insert_job_running(conn, job_id, "erp")
        conn.commit()

        df, mode = _load_erp_dataframe()
        df_std, df_parsed = normalize_dataframe(df)
        if df_parsed.empty:
            raise ValueError("No rows after normalization.")

        stats = dedupe_and_upsert(conn, df_parsed)
        refresh_non_ml_aggregates(conn)
        append_to_ingest_csv(df_std)
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
            "mode": mode,
            "rowsAdded": stats["added"],
            "rowsUpdated": stats["updated"],
            "rowsSkipped": stats["skipped"],
            "byTable": stats.get("by_table", {}),
        }
    except HTTPException:
        update_job_complete(conn, job_id, 0, 0, 0, "configuration error")
        conn.commit()
        raise
    except Exception as ex:
        update_job_complete(conn, job_id, 0, 0, 0, str(ex))
        conn.commit()
        raise HTTPException(status_code=400, detail=str(ex)) from ex
    finally:
        conn.close()


@app.get("/api/ingest/status/{job_id}")
def get_ingest_status(job_id: str, user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
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
def trigger_forecast_refresh(user: AuthUser = Depends(require_role("admin"))) -> Dict[str, Any]:
    job_id = new_job_id()
    conn = get_connection()
    try:
        insert_job_running(conn, job_id, "forecast")
        conn.commit()
    finally:
        conn.close()

    _forecast_executor.submit(_run_forecast_pipeline_job, job_id)
    return {"jobId": job_id, "status": "running"}


@app.get("/api/forecast/job")
def get_forecast_job(user: AuthUser = Depends(require_role("manager"))) -> Dict[str, Any]:
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
def get_pipeline_status(user: AuthUser = Depends(require_role("worker"))) -> Dict[str, Any]:
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
async def sse_events(user: AuthUser = Depends(require_role("manager"))):
    """Server-Sent Events: emits when pipeline_metadata last_run or last_import changes."""
    global _last_known_fingerprint

    async def event_generator():
        global _last_known_fingerprint
        yield "data: connected\n\n"

        while True:
            await asyncio.sleep(config.SSE_POLL_INTERVAL_SECONDS)
            try:
                conn = get_connection()
                try:
                    rows = conn.execute(
                        "SELECT key, value FROM pipeline_metadata WHERE key IN ('last_run', 'last_import') ORDER BY key"
                    ).fetchall()
                    fp = json.dumps(rows)
                finally:
                    conn.close()

                if fp != _last_known_fingerprint:
                    _last_known_fingerprint = fp
                    payload: Dict[str, Any] = {"lastRun": None, "lastImport": None}
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

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# FORECAST ACCURACY / BACKTEST
# ---------------------------------------------------------------------------

def _run_backtest_job(run_id: int, holdout_months: int) -> None:
    conn = get_connection()
    try:
        from preduit_engine.backtest import run_walk_forward_backtest

        run_walk_forward_backtest(holdout_months=holdout_months, conn=conn, run_id=run_id)
        conn.execute(
            "UPDATE backtest_runs SET status = 'completed' WHERE id = ?",
            (run_id,),
        )
        conn.commit()
    except Exception as ex:
        complete_backtest_job(
            conn,
            run_id,
            "failed",
            error=f"{type(ex).__name__}: {ex}\n{traceback.format_exc()}",
        )
    finally:
        conn.close()


@app.get("/api/forecast/accuracy")
def get_forecast_accuracy(user: AuthUser = Depends(require_role("manager"))) -> Dict[str, Any]:
    from preduit_engine.backtest import format_accuracy_api_payload

    conn = get_connection()
    try:
        latest = get_latest_backtest(conn)
        return format_accuracy_api_payload(latest)
    finally:
        conn.close()


@app.post("/api/forecast/backtest")
def trigger_backtest(
    holdoutMonths: Optional[int] = Query(None),
    user: AuthUser = Depends(require_role("admin")),
) -> Dict[str, Any]:
    from preduit_engine.config import BACKTEST_HOLDOUT_MONTHS

    holdout = holdoutMonths or BACKTEST_HOLDOUT_MONTHS

    conn = get_connection()
    try:
        run_id = insert_backtest_job_running(conn, holdout)
    finally:
        conn.close()

    _forecast_executor.submit(_run_backtest_job, run_id, holdout)
    return {"runId": run_id, "status": "running", "holdoutMonths": holdout}


@app.get("/api/forecast/backtest/status")
def get_backtest_status(
    runId: Optional[int] = Query(None),
    user: AuthUser = Depends(require_role("manager")),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        if runId is not None:
            job = get_backtest_job(conn, runId)
            if not job:
                raise HTTPException(status_code=404, detail="Backtest job not found.")
            return job

        row = conn.execute(
            """
            SELECT id, started_at, completed_at, holdout_months, status
            FROM backtest_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return {"runId": None, "status": "idle"}
        return {
            "runId": row[0],
            "startedAt": row[1],
            "completedAt": row[2],
            "holdoutMonths": row[3],
            "status": row[4],
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "preduit_app.api_server:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
    )
