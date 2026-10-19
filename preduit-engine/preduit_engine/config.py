"""
Engine configuration: algorithm constants and derived field names.

Loads optional `preduit_app.client_config` first so `.env` is applied before
reading FORECASTER_* defaults.

Pipeline modules use Choice A: ``from .config import *``.
Application-facing paths and business policy are defined in `preduit_app.client_config`
and merged onto this module when the app package is installed.
"""

from pathlib import Path

try:
    import preduit_app.client_config as _app  # noqa: F401  — loads dotenv side effects
except ImportError:
    _app = None

from ._env import (
    _env_bool,
    _env_float,
    _env_int,
    _env_list,
    _env_optional_float,
    _env_str,
)

# ── Derived column names (pipeline internal contract) ──
COL_TRUE_DEMAND = "true_demand"
COL_YEAR_MONTH = "year_month"
COL_SEASON_TYPE = "season_type"
COL_SEASON_YEAR = "season_year"
COL_PRODUCT_STATUS = "product_status"
COL_MODEL_ASSIGNMENT = "model_assignment"

# ── Temporal / forecasting algorithm ──
FORECAST_GRANULARITY = "monthly"
SARIMA_SEASONAL_PERIOD = _env_int("FORECASTER_SARIMA_SEASONAL_PERIOD", 12)
SARIMA_MIN_MONTHS_SPAN = _env_int("FORECASTER_SARIMA_MIN_MONTHS_SPAN", 36)
CATBOOST_MIN_MONTHS = _env_int("FORECASTER_CATBOOST_MIN_MONTHS", 3)

FORECAST_HORIZON_MONTHS = _env_int("FORECASTER_FORECAST_HORIZON_MONTHS", 6)

SARIMA_P_MAX = _env_int("FORECASTER_SARIMA_P_MAX", 2)
SARIMA_D_MAX = _env_int("FORECASTER_SARIMA_D_MAX", 1)
SARIMA_Q_MAX = _env_int("FORECASTER_SARIMA_Q_MAX", 2)
SARIMA_SP_MAX = _env_int("FORECASTER_SARIMA_SP_MAX", 1)
SARIMA_SD_MAX = _env_int("FORECASTER_SARIMA_SD_MAX", 1)
SARIMA_SQ_MAX = _env_int("FORECASTER_SARIMA_SQ_MAX", 1)

CATBOOST_ITERATIONS = _env_int("FORECASTER_CATBOOST_ITERATIONS", 1000)
CATBOOST_DEPTH = _env_int("FORECASTER_CATBOOST_DEPTH", 6)
CATBOOST_LEARNING_RATE = _env_float("FORECASTER_CATBOOST_LEARNING_RATE", 0.05)
CATBOOST_L2_REG = _env_float("FORECASTER_CATBOOST_L2_REG", 3.0)
CATBOOST_EARLY_STOPPING = _env_int("FORECASTER_CATBOOST_EARLY_STOPPING", 50)

BACKTEST_HOLDOUT_MONTHS = _env_int("FORECASTER_BACKTEST_HOLDOUT_MONTHS", 6)
BACKTEST_MIN_ACTUALS = _env_float("FORECASTER_BACKTEST_MIN_ACTUALS", 1.0)
BACKTEST_MAX_SKUS = _env_int("FORECASTER_BACKTEST_MAX_SKUS", 0)

QUANTILE_CONSERVATIVE = _env_float("FORECASTER_QUANTILE_CONSERVATIVE", 0.20)
QUANTILE_BASE = _env_float("FORECASTER_QUANTILE_BASE", 0.50)
QUANTILE_OPTIMISTIC = _env_float("FORECASTER_QUANTILE_OPTIMISTIC", 0.80)

MIN_UNITS_FOR_PRODUCT_SIZE_CURVE = _env_int(
    "FORECASTER_MIN_UNITS_FOR_PRODUCT_SIZE_CURVE", 30
)
SIZE_MAX_SHARE_CAP = _env_float("FORECASTER_SIZE_MAX_SHARE_CAP", 0.35)
SIZE_MIN_QTY = _env_int("FORECASTER_SIZE_MIN_QTY", 0)
EXTREME_SIZE_DAMPENING_FACTOR = _env_float(
    "FORECASTER_EXTREME_SIZE_DAMPENING_FACTOR", 1.0
)

SIZE_ORDER_ALPHA = [
    "XXS",
    "XS",
    "S",
    "M",
    "L",
    "XL",
    "XL2",
    "XL3",
    "XL4",
    "XL5",
    "XL6",
    "XL7",
    "XL8",
]
SIZE_ORDER_NUMERIC = [str(i) for i in range(24, 70)]
SIZE_ORDER_PANTS = ["26", "27", "28", "29", "30", "31", "32", "33", "34", "36", "38", "40", "42"]

# ── Merge app overlay (paths, API, client policy) ──
if _app is not None:
    BACKEND_DIR = _app.BACKEND_DIR
    PROJECT_ROOT = _app.PROJECT_ROOT
    LEGACY_BACKEND_DIR = _app.LEGACY_BACKEND_DIR
    RAW_DATA_DIR = _app.RAW_DATA_DIR
    DB_PATH = _app.DB_PATH
    DATA_FILE_PATH = _app.DATA_FILE_PATH
    DATA_FILE_NAME = _app.DATA_FILE_NAME
    DATA_SEPARATOR = _app.DATA_SEPARATOR
    DATA_ENCODING = _app.DATA_ENCODING
    DEFAULT_COST_RATIO = _app.DEFAULT_COST_RATIO
    ACTIVE_CLIENT_LOOKBACK_MONTHS = _app.ACTIVE_CLIENT_LOOKBACK_MONTHS
    TARGET_MARGIN_RATE = _app.TARGET_MARGIN_RATE
    SEASONAL_BUDGET = _app.SEASONAL_BUDGET
    BUDGET_MULTIPLIER = _app.BUDGET_MULTIPLIER
    TARGET_MARGIN_DISPLAY = _app.TARGET_MARGIN_DISPLAY
    OUTPUT_DIR = _app.OUTPUT_DIR
    OUTPUT_RECOMMENDATIONS_FILE = _app.OUTPUT_RECOMMENDATIONS_FILE
    OUTPUT_SUMMARY_FILE = _app.OUTPUT_SUMMARY_FILE
    OUTPUT_MODEL_PERFORMANCE_FILE = _app.OUTPUT_MODEL_PERFORMANCE_FILE
    OUTPUT_MONTHLY_DETAIL_FILE = _app.OUTPUT_MONTHLY_DETAIL_FILE
    API_HOST = _app.API_HOST
    API_PORT = _app.API_PORT
    API_RELOAD = _app.API_RELOAD
    CORS_ORIGINS = _app.CORS_ORIGINS
    FORECAST_THREAD_POOL_SIZE = _app.FORECAST_THREAD_POOL_SIZE
    SSE_POLL_INTERVAL_SECONDS = _app.SSE_POLL_INTERVAL_SECONDS
else:
    _here = Path(__file__).resolve().parent
    BACKEND_DIR = _here
    PROJECT_ROOT = _here.parent
    LEGACY_BACKEND_DIR = PROJECT_ROOT / "backend-ai"
    RAW_DATA_DIR = LEGACY_BACKEND_DIR / "data" / "raw"
    DB_PATH = LEGACY_BACKEND_DIR / "data" / "forecast.db"
    DATA_FILE_NAME = "THE_FINAL_10Y_cleaned.csv"
    import os as _os

    DATA_FILE_PATH = _os.path.join(str(LEGACY_BACKEND_DIR), "data", "raw", DATA_FILE_NAME)
    DATA_SEPARATOR = ","
    DATA_ENCODING = "utf-8"
    DEFAULT_COST_RATIO = _env_float("FORECASTER_DEFAULT_COST_RATIO", 0.50)
    ACTIVE_CLIENT_LOOKBACK_MONTHS = _env_int("FORECASTER_ACTIVE_CLIENT_LOOKBACK_MONTHS", 24)
    TARGET_MARGIN_RATE = _env_optional_float("FORECASTER_TARGET_MARGIN_RATE", None)
    SEASONAL_BUDGET = _env_optional_float("FORECASTER_SEASONAL_BUDGET", None)
    BUDGET_MULTIPLIER = _env_float("FORECASTER_BUDGET_MULTIPLIER", 1.2)
    TARGET_MARGIN_DISPLAY = _env_int("FORECASTER_TARGET_MARGIN_DISPLAY", 45)
    OUTPUT_DIR = _env_str("FORECASTER_OUTPUT_DIR", "output/")
    OUTPUT_RECOMMENDATIONS_FILE = _env_str(
        "FORECASTER_OUTPUT_RECOMMENDATIONS_FILE", "recommendations.csv"
    )
    OUTPUT_SUMMARY_FILE = _env_str("FORECASTER_OUTPUT_SUMMARY_FILE", "summary_report.csv")
    OUTPUT_MODEL_PERFORMANCE_FILE = _env_str(
        "FORECASTER_OUTPUT_MODEL_PERFORMANCE_FILE", "model_performance.csv"
    )
    OUTPUT_MONTHLY_DETAIL_FILE = _env_str(
        "FORECASTER_OUTPUT_MONTHLY_DETAIL_FILE", "forecast_monthly_detail.csv"
    )
    API_HOST = _env_str("FORECASTER_API_HOST", "0.0.0.0")
    API_PORT = _env_int("FORECASTER_API_PORT", 4000)
    API_RELOAD = _env_bool("FORECASTER_API_RELOAD", True)
    CORS_ORIGINS = _env_list(
        "FORECASTER_CORS_ORIGINS",
        ["http://localhost:3000", "http://127.0.0.1:3000"],
    )
    FORECAST_THREAD_POOL_SIZE = _env_int("FORECASTER_FORECAST_THREAD_POOL_SIZE", 1)
    SSE_POLL_INTERVAL_SECONDS = _env_int("FORECASTER_SSE_POLL_INTERVAL_SECONDS", 5)
