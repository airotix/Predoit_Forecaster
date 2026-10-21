# ──────────────────────────────────────────────
# DATA SETTINGS — UPDATE THIS TO YOUR FILE
# ──────────────────────────────────────────────
import os

# Automatically find the script directory
import paths
_BASE_DIR = str(paths.HOME)

# Your data file — UPDATE THIS NAME to match your actual file
DATA_FILE_NAME = "THE_FINAL_10Y_cleaned.csv"  # ← change this to your actual filename

# Build full path
_DATA_FILE_CANDIDATES = [
    os.path.join(_BASE_DIR, "data", "raw", DATA_FILE_NAME),
    os.path.join(_BASE_DIR, "data", DATA_FILE_NAME),
    os.path.join(_BASE_DIR, DATA_FILE_NAME),
]
DATA_FILE_PATH = next(
    (path for path in _DATA_FILE_CANDIDATES if os.path.exists(path)),
    _DATA_FILE_CANDIDATES[0],
)

# If data is directly in the backend-ai folder, use this instead:
# DATA_FILE_PATH = os.path.join(_BASE_DIR, DATA_FILE_NAME)

DATA_SEPARATOR = ","          # ← CHANGED FROM "\t" TO ","
DATA_ENCODING = "utf-8"      # ← CHANGED — will auto-detect if fails

# ──────────────────────────────────────────────
# REST OF CONFIG STAYS THE SAME...
# ──────────────────────────────────────────────                 # handles the mojibake characters

# ──────────────────────────────────────────────
# COLUMN NAMES (exactly as in your file)
# ──────────────────────────────────────────────
COL_CLIENT = "Client"
COL_NOM = "Nom"
COL_FAMILLE_CLIENT = "Famille_client"
COL_CP = "CP"
COL_VILLE = "Ville"
COL_PAYS = "Pays"
COL_SECTEUR = "Secteur"
COL_LOCALISATION = "Localisation"
COL_MAGASIN = "Magasin"
COL_PIECE = "Pi\xe8ce" if False else "Pièce"  # handle encoding
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

# ──────────────────────────────────────────────
# DERIVED COLUMN NAMES (created by the system)
# ──────────────────────────────────────────────
COL_TRUE_DEMAND = "true_demand"
COL_YEAR_MONTH = "year_month"
COL_SEASON_TYPE = "season_type"
COL_SEASON_YEAR = "season_year"
COL_PRODUCT_STATUS = "product_status"
COL_MODEL_ASSIGNMENT = "model_assignment"

# ──────────────────────────────────────────────
# TEMPORAL SETTINGS
# ──────────────────────────────────────────────
FORECAST_GRANULARITY = "monthly"          # monthly aggregation
SARIMA_SEASONAL_PERIOD = 12              # m=12 for monthly data
SARIMA_MIN_MONTHS_SPAN = 36             # 3 years minimum span for SARIMA
CATBOOST_MIN_MONTHS = 3                  # minimum months with data for CatBoost

# ──────────────────────────────────────────────
# FORECASTING SETTINGS
# ──────────────────────────────────────────────
FORECAST_HORIZON_MONTHS = 6             # forecast next 6 months

# SARIMA search space
SARIMA_P_MAX = 2
SARIMA_D_MAX = 1
SARIMA_Q_MAX = 2
SARIMA_SP_MAX = 1
SARIMA_SD_MAX = 1
SARIMA_SQ_MAX = 1

# CatBoost settings
CATBOOST_ITERATIONS = 1000
CATBOOST_DEPTH = 6
CATBOOST_LEARNING_RATE = 0.05
CATBOOST_L2_REG = 3
CATBOOST_EARLY_STOPPING = 50

# Scenario quantiles
QUANTILE_CONSERVATIVE = 0.20
QUANTILE_BASE = 0.50
QUANTILE_OPTIMISTIC = 0.80

# ──────────────────────────────────────────────
# SIZE CURVE SETTINGS
# ──────────────────────────────────────────────
MIN_UNITS_FOR_PRODUCT_SIZE_CURVE = 30   # min total units to trust product-specific curve
SIZE_MAX_SHARE_CAP = 0.35               # no single size > 35%
SIZE_MIN_QTY = 0                         # min units per size (0 for POC)
EXTREME_SIZE_DAMPENING_FACTOR = 1.0     # 1.0 = no dampening (POC)

# Known size orderings (extend as needed)
SIZE_ORDER_ALPHA = ["XXS", "XS", "S", "M", "L", "XL", "XL2", "XL3",
                    "XL4", "XL5", "XL6", "XL7", "XL8"]
SIZE_ORDER_NUMERIC = [str(i) for i in range(24, 70)]  # 24 to 69
SIZE_ORDER_PANTS = ["26", "27", "28", "29", "30", "31", "32",
                    "33", "34", "36", "38", "40", "42"]

# ──────────────────────────────────────────────
# FINANCIAL PLACEHOLDERS
# ──────────────────────────────────────────────
DEFAULT_COST_RATIO = 0.50               # assumed cost = 50% of Prix
TARGET_MARGIN_RATE = None               # to be provided later
SEASONAL_BUDGET = None                  # to be provided later

# ──────────────────────────────────────────────
# ACTIVE CLIENT SETTINGS
# ──────────────────────────────────────────────
ACTIVE_CLIENT_LOOKBACK_MONTHS = 24      # clients active in last 24 months

# ──────────────────────────────────────────────
# OUTPUT SETTINGS
# ──────────────────────────────────────────────
OUTPUT_DIR = "output/"
OUTPUT_RECOMMENDATIONS_FILE = "recommendations.csv"
OUTPUT_SUMMARY_FILE = "summary_report.csv"
OUTPUT_MODEL_PERFORMANCE_FILE = "model_performance.csv"