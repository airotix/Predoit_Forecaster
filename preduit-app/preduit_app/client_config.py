"""
Per-client / deployment configuration: paths, API, schema labels, business policy.

Loaded before `preduit_engine.config` so `.env` applies to engine defaults too.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from preduit_engine._env import (
    _env_bool,
    _env_float,
    _env_int,
    _env_list,
    _env_optional_float,
    _env_str,
)

_PKG_DIR = Path(__file__).resolve().parent
APP_SERVICE_ROOT = _PKG_DIR.parent
PROJECT_ROOT = APP_SERVICE_ROOT.parent

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# Legacy layout: data still lives under repo `backend-ai/` unless overridden by env.
LEGACY_BACKEND_DIR = PROJECT_ROOT / "backend-ai"
BACKEND_DIR = LEGACY_BACKEND_DIR
RAW_DATA_DIR = LEGACY_BACKEND_DIR / "data" / "raw"
_BASE_DIR = str(BACKEND_DIR)

_db_override = _env_str("FORECASTER_DB_PATH", "")
DB_PATH = (
    Path(_db_override).expanduser().resolve()
    if _db_override
    else LEGACY_BACKEND_DIR / "data" / "forecast.db"
)

API_HOST = _env_str("FORECASTER_API_HOST", "0.0.0.0")
API_PORT = _env_int("FORECASTER_API_PORT", 4000)
API_RELOAD = _env_bool("FORECASTER_API_RELOAD", True)
CORS_ORIGINS = _env_list(
    "FORECASTER_CORS_ORIGINS",
    ["http://localhost:3000", "http://127.0.0.1:3000"],
)

_data_file_env = _env_str("FORECASTER_DATA_FILE", "")
if _data_file_env:
    _data_path = Path(_data_file_env).expanduser()
    if not _data_path.is_absolute():
        _data_path = (PROJECT_ROOT / _data_path).resolve()
    DATA_FILE_PATH = str(_data_path)
    DATA_FILE_NAME = _data_path.name
else:
    DATA_FILE_NAME = "THE_FINAL_10Y_cleaned.csv"
    DATA_FILE_PATH = os.path.join(_BASE_DIR, "data", "raw", DATA_FILE_NAME)

DATA_SEPARATOR = _env_str("FORECASTER_DATA_SEPARATOR", ",")
DATA_ENCODING = _env_str("FORECASTER_DATA_ENCODING", "utf-8")

COL_CLIENT = "Client"
COL_NOM = "Nom"
COL_FAMILLE_CLIENT = "Famille_client"
COL_CP = "CP"
COL_VILLE = "Ville"
COL_PAYS = "Pays"
COL_SECTEUR = "Secteur"
COL_LOCALISATION = "Localisation"
COL_MAGASIN = "Magasin"
COL_PIECE = "Pièce"
COL_CRITERE = "Critère"
COL_REF_CDE = "Référence_CDE"
COL_REPRESENTANT = "Représentant"
COL_DATE_COMMANDE = "Date_Commande"
COL_GENCOD = "Gencod"
COL_REFERENCE = "Référence"
COL_COULEUR = "Couleur"
COL_TAILLE = "Taille"
COL_DESIGNATION = "Désignation"
COL_RAYON = "Rayon"
COL_FAMILLE = "Famille"
COL_THEME = "Thème"
COL_MODELE = "Modèle"
COL_MATIERE = "Matière"
COL_FOURNISSEUR = "Fournisseur"
COL_SAISON = "Saison"
COL_PRIX = "Prix"
COL_CDE_QTE = "CDE_qte"
COL_CDE_BRUT = "CDE_brut_ht"
COL_CDE_REMISE = "CDE_remise_ht"
COL_CDE_NET = "CDE_net_ht"
COL_LIV_QTE = "LIV_qte"
COL_LIV_BRUT = "LIV_brut_ht"
COL_LIV_REMISE = "LIV_remise_ht"
COL_LIV_NET = "LIV_net_ht"
COL_RELIQUAT_QTE = "RELIQUAT_qte"
COL_RELIQUAT_BRUT = "RELIQUAT_brut_ht"
COL_RELIQUAT_REMISE = "RELIQUAT_remise_ht"
COL_RELIQUAT_NET = "RELIQUAT_net_ht"
COL_ANN_QTE = "ANN_qte"
COL_ANN_BRUT = "ANN_brut_ht"
COL_ANN_REMISE = "ANN_remise_ht"
COL_ANN_NET = "ANN_net_ht"
COL_STOCK = "STOCK"
COL_CDE_FOUR = "CDE_four"
COL_CDE_FOUR_DATE = "CDE_four_date_liv"
COL_CDE_FOUR_QTE = "CDE_four_qte"

DEFAULT_COST_RATIO = _env_float("FORECASTER_DEFAULT_COST_RATIO", 0.50)
TARGET_MARGIN_RATE = _env_optional_float("FORECASTER_TARGET_MARGIN_RATE", None)
SEASONAL_BUDGET = _env_optional_float("FORECASTER_SEASONAL_BUDGET", None)
BUDGET_MULTIPLIER = _env_float("FORECASTER_BUDGET_MULTIPLIER", 1.2)
TARGET_MARGIN_DISPLAY = _env_int("FORECASTER_TARGET_MARGIN_DISPLAY", 45)

ACTIVE_CLIENT_LOOKBACK_MONTHS = _env_int("FORECASTER_ACTIVE_CLIENT_LOOKBACK_MONTHS", 24)

OUTPUT_DIR = _env_str("FORECASTER_OUTPUT_DIR", "output/")
OUTPUT_RECOMMENDATIONS_FILE = _env_str(
    "FORECASTER_OUTPUT_RECOMMENDATIONS_FILE", "recommendations.csv"
)
OUTPUT_SUMMARY_FILE = _env_str(
    "FORECASTER_OUTPUT_SUMMARY_FILE", "summary_report.csv"
)
OUTPUT_MODEL_PERFORMANCE_FILE = _env_str(
    "FORECASTER_OUTPUT_MODEL_PERFORMANCE_FILE", "model_performance.csv"
)
OUTPUT_MONTHLY_DETAIL_FILE = _env_str(
    "FORECASTER_OUTPUT_MONTHLY_DETAIL_FILE", "forecast_monthly_detail.csv"
)

FORECAST_THREAD_POOL_SIZE = _env_int("FORECASTER_FORECAST_THREAD_POOL_SIZE", 1)
SSE_POLL_INTERVAL_SECONDS = _env_int("FORECASTER_SSE_POLL_INTERVAL_SECONDS", 5)

# ── Authentication ──
# Roles (highest to lowest): owner = admin (top) > manager > worker (view-only).
AUTH_ENABLED = _env_bool("FORECASTER_AUTH_ENABLED", False)
AUTH_DEV_BYPASS = _env_bool("FORECASTER_AUTH_DEV_BYPASS", True)
AUTH_DEV_ROLE = _env_str("FORECASTER_AUTH_DEV_ROLE", "admin")

# Azure Entra ID (SSO) settings.
AZURE_TENANT_ID = _env_str("FORECASTER_AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = _env_str("FORECASTER_AZURE_CLIENT_ID", "")
AZURE_API_AUDIENCE = _env_str(
    "FORECASTER_AZURE_API_AUDIENCE",
    _env_str("FORECASTER_AZURE_CLIENT_ID", ""),
)

# Local email/password authentication settings.
AUTH_LOCAL_SECRET = _env_str("FORECASTER_AUTH_SECRET", "")
AUTH_TOKEN_TTL_HOURS = _env_int("FORECASTER_AUTH_TOKEN_TTL_HOURS", 12)
AUTH_ALLOW_SIGNUP = _env_bool("FORECASTER_AUTH_ALLOW_SIGNUP", True)
# True when Azure SSO is configured enough to attempt it.
SSO_ENABLED = bool(AZURE_TENANT_ID and AZURE_CLIENT_ID)
BACKTEST_HOLDOUT_MONTHS = _env_int("FORECASTER_BACKTEST_HOLDOUT_MONTHS", 6)

# ── ERP integration (Joolan / Lisa API v2) ──
# Dormant until enabled + credentials are supplied. The manual "ERP Sync" button
# falls back to sample data / CSV upload while unconfigured.
ERP_ENABLED = _env_bool("FORECASTER_ERP_ENABLED", False)
ERP_BASE_URL = _env_str("FORECASTER_ERP_BASE_URL", "https://lisa.joolan.com/api/v2")
ERP_ENSEIGNE = _env_str("FORECASTER_ERP_ENSEIGNE", "")
ERP_API_KEY = _env_str("FORECASTER_ERP_API_KEY", "")
ERP_MAGASINS = _env_str("FORECASTER_ERP_MAGASINS", "")  # ';'-separated; empty = all
# SQL for /query.do — set once Joolan's table/column names are known. Each query should
# alias its columns to the names the pipeline expects.
ERP_HISTORY_SQL = _env_str("FORECASTER_ERP_HISTORY_SQL", "")
ERP_COST_SQL = _env_str("FORECASTER_ERP_COST_SQL", "")


def erp_is_configured() -> bool:
    """True when the ERP is enabled and has the minimum credentials to attempt a sync."""
    return bool(ERP_ENABLED and ERP_BASE_URL and ERP_ENSEIGNE and ERP_API_KEY)
