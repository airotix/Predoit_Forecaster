"""
SQLite serving layer for the forecasting pipeline.
Schema creation, indexes, and population from pipeline results.
DB path comes from config.DB_PATH (FORECASTER_DB_PATH env var; see .env.example).
"""

import sqlite3
import pandas as pd
import numpy as np

from .config import DB_PATH as DB_FILE

DB_FILE.parent.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 10_000

# Bump when the persistent schema changes. Recorded in the `schema_meta` table on
# startup so a deployment can detect/verify the DB's schema version.
SCHEMA_VERSION = 2


def get_connection(db_path=None):
    """Return a sqlite3 connection with performance pragmas."""
    path = db_path or DB_FILE
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")
    return conn


def _safe_val(val, target_type="str"):
    """Safely convert to int/float/str handling NaN/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        if target_type == "int":
            return 0
        if target_type == "float":
            return 0.0
        return ""
    if target_type == "int":
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return 0
    if target_type == "float":
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0
    return str(val).strip() if val is not None else ""


def _create_persistent_tables(conn):
    """Create tables that survive pipeline re-runs (user data)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            taille TEXT NOT NULL,
            override_qty INTEGER NOT NULL,
            reason TEXT,
            notes TEXT,
            user TEXT DEFAULT 'system',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user TEXT DEFAULT 'system',
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_name TEXT,
            previous_value TEXT,
            new_value TEXT,
            details TEXT
        );

        CREATE TABLE IF NOT EXISTS sku_locks (
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            locked INTEGER DEFAULT 0,
            locked_by TEXT,
            locked_at TEXT,
            PRIMARY KEY (reference, couleur)
        );

        CREATE INDEX IF NOT EXISTS idx_uo_ref_coul ON user_overrides(reference, couleur);
        CREATE INDEX IF NOT EXISTS idx_uo_ref_coul_taille ON user_overrides(reference, couleur, taille);
        CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_locks_ref_coul ON sku_locks(reference, couleur);

        CREATE TABLE IF NOT EXISTS import_jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            rows_added INTEGER DEFAULT 0,
            rows_updated INTEGER DEFAULT 0,
            rows_skipped INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_import_jobs_started ON import_jobs(started_at DESC);

        CREATE TABLE IF NOT EXISTS season_config (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            budget REAL NOT NULL DEFAULT 0,
            target_margin REAL NOT NULL DEFAULT 50,
            budget_band_pct REAL NOT NULL DEFAULT 15,
            cost_ratio REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'draft',
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_season_config_active ON season_config(is_active);

        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            holdout_months INTEGER NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT
        );

        CREATE TABLE IF NOT EXISTS backtest_fold_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            fold_month TEXT NOT NULL,
            wmape REAL,
            bias REAL,
            coverage_80 REAL,
            total_actual REAL,
            FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
        );

        CREATE TABLE IF NOT EXISTS backtest_breakdown (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            dimension TEXT NOT NULL,
            dimension_value TEXT NOT NULL,
            wmape REAL,
            bias REAL,
            coverage_80 REAL,
            sku_count INTEGER,
            FOREIGN KEY (run_id) REFERENCES backtest_runs(id)
        );

        CREATE INDEX IF NOT EXISTS idx_backtest_fold_run ON backtest_fold_metrics(run_id);
        CREATE INDEX IF NOT EXISTS idx_backtest_breakdown_run ON backtest_breakdown(run_id);

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'worker',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # Lightweight column migrations for tables that pre-date newer fields.
    _add_missing_columns(
        conn,
        "season_config",
        {
            "budget_band_pct": "REAL NOT NULL DEFAULT 15",
            "cost_ratio": "REAL NOT NULL DEFAULT 0.5",
        },
    )

    # Record the schema version so deployments can verify what they're running.
    set_schema_version(conn, SCHEMA_VERSION)
    conn.commit()


def get_schema_version(conn) -> int:
    """Return the recorded schema version (0 if never set)."""
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row and str(row[0]).isdigit() else 0


def set_schema_version(conn, version: int) -> None:
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


def check_integrity(conn) -> bool:
    """Run SQLite's integrity check. True when the database is healthy."""
    row = conn.execute("PRAGMA integrity_check").fetchone()
    return bool(row) and row[0] == "ok"


def _add_missing_columns(conn, table: str, columns: dict) -> None:
    """Add columns that don't yet exist on an existing table (safe migration)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


# ── User account CRUD (local email/password auth) ──

_USER_COLUMNS = (
    "id", "email", "name", "password_hash", "role",
    "status", "created_at", "updated_at", "last_login_at",
)


def _row_to_user(row) -> dict:
    if row is None:
        return None
    return dict(zip(_USER_COLUMNS, row))


def count_users(conn) -> int:
    """Total number of registered accounts (used to bootstrap the first owner)."""
    cur = conn.execute("SELECT COUNT(*) FROM users")
    return int(cur.fetchone()[0])


def get_user_by_email(conn, email: str) -> dict:
    """Return the user record for an email (case-insensitive) or None."""
    cur = conn.execute(
        f"SELECT {', '.join(_USER_COLUMNS)} FROM users WHERE email = ? COLLATE NOCASE",
        (email.strip().lower(),),
    )
    return _row_to_user(cur.fetchone())


def create_user(
    conn,
    *,
    email: str,
    name: str,
    password_hash: str,
    role: str,
    status: str,
    now: str,
) -> dict:
    """Insert a new user and return the created record."""
    conn.execute(
        """
        INSERT INTO users (email, name, password_hash, role, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (email.strip().lower(), name.strip(), password_hash, role, status, now, now),
    )
    conn.commit()
    return get_user_by_email(conn, email)


def touch_user_login(conn, email: str, now: str) -> None:
    """Record the last successful login timestamp."""
    conn.execute(
        "UPDATE users SET last_login_at = ?, updated_at = ? WHERE email = ? COLLATE NOCASE",
        (now, now, email.strip().lower()),
    )
    conn.commit()


def list_users(conn) -> list:
    """Return all users (without password hashes) for admin management."""
    cols = [c for c in _USER_COLUMNS if c != "password_hash"]
    cur = conn.execute(f"SELECT {', '.join(cols)} FROM users ORDER BY created_at ASC")
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def update_user_role(conn, email: str, role: str, now: str) -> dict:
    """Change a user's role (admin/owner action)."""
    conn.execute(
        "UPDATE users SET role = ?, updated_at = ? WHERE email = ? COLLATE NOCASE",
        (role, now, email.strip().lower()),
    )
    conn.commit()
    return get_user_by_email(conn, email)


_DROP_PIPELINE_TABLES = """
        DROP TABLE IF EXISTS pipeline_metadata;
        DROP TABLE IF EXISTS filter_options;
        DROP TABLE IF EXISTS client_orders;
        DROP TABLE IF EXISTS clients;
        DROP TABLE IF EXISTS historical_sku_color;
        DROP TABLE IF EXISTS historical_demand;
        DROP TABLE IF EXISTS forecast_monthly;
        DROP TABLE IF EXISTS recommendations;
"""

_PIPELINE_TABLES_DDL = """
        CREATE TABLE IF NOT EXISTS recommendations (
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            taille TEXT NOT NULL,
            model_type TEXT,
            fournisseur TEXT,
            famille TEXT,
            theme TEXT,
            modele TEXT,
            client TEXT,
            saison TEXT,
            critere TEXT,
            season_type TEXT,
            product_status TEXT,
            confidence TEXT,
            forecast_conservative INTEGER,
            forecast_base INTEGER,
            forecast_optimistic INTEGER,
            confirmed_orders INTEGER,
            confirmed_delivered INTEGER,
            confirmed_clients INTEGER,
            current_stock INTEGER,
            pipeline_stock INTEGER,
            available_inventory INTEGER,
            net_to_order_conservative INTEGER,
            net_to_order_base INTEGER,
            net_to_order_optimistic INTEGER,
            probable_additional_base INTEGER,
            diffusion_rate REAL,
            total_buying_clients INTEGER,
            depth_per_client REAL,
            reorder_rate REAL,
            fill_rate REAL,
            backorder_rate REAL,
            size_share REAL,
            size_had_stockout INTEGER,
            total_true_demand REAL,
            avg_price REAL,
            expected_revenue_conservative REAL,
            expected_revenue_base REAL,
            expected_revenue_optimistic REAL,
            estimated_cost_conservative REAL,
            estimated_cost_base REAL,
            estimated_cost_optimistic REAL,
            estimated_margin_base REAL,
            margin_rate_base REAL,
            financial_note TEXT,
            span_months REAL,
            explanation TEXT,
            designation TEXT,
            rayon TEXT,
            matiere TEXT,
            PRIMARY KEY (reference, couleur, taille)
        );

        CREATE TABLE IF NOT EXISTS forecast_monthly (
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            taille TEXT NOT NULL,
            forecast_month TEXT NOT NULL,
            forecast_conservative INTEGER,
            forecast_base INTEGER,
            forecast_optimistic INTEGER,
            model_type TEXT
        );

        CREATE TABLE IF NOT EXISTS historical_demand (
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            taille TEXT NOT NULL,
            year_month TEXT NOT NULL,
            true_demand REAL,
            cde_qte REAL,
            liv_qte REAL,
            reliquat_qte REAL,
            ann_qte REAL,
            num_clients INTEGER,
            prix REAL
        );

        CREATE TABLE IF NOT EXISTS historical_sku_color (
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            year_month TEXT NOT NULL,
            true_demand REAL,
            num_clients INTEGER,
            prix REAL
        );

        CREATE TABLE IF NOT EXISTS client_orders (
            client_id TEXT NOT NULL,
            client_name TEXT,
            reference TEXT NOT NULL,
            couleur TEXT NOT NULL,
            taille TEXT NOT NULL,
            critere TEXT,
            season_type TEXT,
            season_year REAL,
            date_commande TEXT,
            cde_qte REAL,
            liv_qte REAL,
            true_demand REAL,
            prix REAL,
            cde_net_ht REAL
        );

        CREATE TABLE IF NOT EXISTS clients (
            client_id TEXT PRIMARY KEY,
            client_name TEXT,
            famille_client TEXT,
            cp TEXT,
            ville TEXT,
            pays TEXT,
            secteur TEXT,
            total_units REAL,
            total_spend REAL,
            num_skus INTEGER,
            active_months INTEGER,
            first_order TEXT,
            last_order TEXT
        );

        CREATE TABLE IF NOT EXISTS filter_options (
            filter_type TEXT NOT NULL,
            filter_value TEXT NOT NULL,
            saison TEXT NOT NULL,
            item_count INTEGER
        );

        CREATE TABLE IF NOT EXISTS pipeline_metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        );
"""


def ensure_pipeline_schema(conn):
    """Create pipeline tables if missing (e.g. API started before first populate)."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recommendations'"
    ).fetchone()
    if row:
        return
    conn.executescript(_PIPELINE_TABLES_DDL)
    _create_indexes(conn)


def _create_schema(conn):
    """Create all tables (drops pipeline-generated tables only)."""
    conn.executescript(_DROP_PIPELINE_TABLES)
    conn.executescript(_PIPELINE_TABLES_DDL)


def _create_indexes(conn):
    """Create all indexes."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_reco_reference ON recommendations(reference)",
        "CREATE INDEX IF NOT EXISTS idx_reco_couleur ON recommendations(couleur)",
        "CREATE INDEX IF NOT EXISTS idx_reco_ref_coul ON recommendations(reference, couleur)",
        "CREATE INDEX IF NOT EXISTS idx_reco_critere ON recommendations(critere)",
        "CREATE INDEX IF NOT EXISTS idx_reco_saison ON recommendations(saison)",
        "CREATE INDEX IF NOT EXISTS idx_reco_famille ON recommendations(famille)",
        "CREATE INDEX IF NOT EXISTS idx_reco_fournisseur ON recommendations(fournisseur)",
        "CREATE INDEX IF NOT EXISTS idx_reco_theme ON recommendations(theme)",
        "CREATE INDEX IF NOT EXISTS idx_reco_modele ON recommendations(modele)",
        "CREATE INDEX IF NOT EXISTS idx_reco_client ON recommendations(client)",
        "CREATE INDEX IF NOT EXISTS idx_reco_confidence ON recommendations(confidence)",
        "CREATE INDEX IF NOT EXISTS idx_reco_model_type ON recommendations(model_type)",
        "CREATE INDEX IF NOT EXISTS idx_reco_net_to_order_base ON recommendations(net_to_order_base DESC)",
        "CREATE INDEX IF NOT EXISTS idx_reco_forecast_base ON recommendations(forecast_base DESC)",
        "CREATE INDEX IF NOT EXISTS idx_fm_ref_coul ON forecast_monthly(reference, couleur)",
        "CREATE INDEX IF NOT EXISTS idx_fm_forecast_month ON forecast_monthly(forecast_month)",
        "CREATE INDEX IF NOT EXISTS idx_hd_ref_coul ON historical_demand(reference, couleur)",
        "CREATE INDEX IF NOT EXISTS idx_hd_ref_coul_taille ON historical_demand(reference, couleur, taille)",
        "CREATE INDEX IF NOT EXISTS idx_hd_year_month ON historical_demand(year_month)",
        "CREATE INDEX IF NOT EXISTS idx_hsc_ref_coul ON historical_sku_color(reference, couleur)",
        "CREATE INDEX IF NOT EXISTS idx_co_client_id ON client_orders(client_id)",
        "CREATE INDEX IF NOT EXISTS idx_co_ref_coul ON client_orders(reference, couleur)",
        "CREATE INDEX IF NOT EXISTS idx_co_critere ON client_orders(critere)",
        "CREATE INDEX IF NOT EXISTS idx_co_client_name ON client_orders(client_name)",
        "CREATE INDEX IF NOT EXISTS idx_fo_filter_type ON filter_options(filter_type)",
        "CREATE INDEX IF NOT EXISTS idx_fo_type_saison ON filter_options(filter_type, saison)",
    ]
    for sql in indexes:
        conn.execute(sql)
    _ensure_unique_fact_indexes(conn)


def _ensure_unique_fact_indexes(conn):
    """Unique indexes for upsert/dedupe on facts (safe if no duplicate rows exist)."""
    for sql, label in [
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_co_dedup ON client_orders(client_id, reference, couleur, taille, critere, season_type, COALESCE(season_year, -1))",
            "client_orders",
        ),
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_hd_dedup ON historical_demand(reference, couleur, taille, year_month)",
            "historical_demand",
        ),
        (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_hsc_dedup ON historical_sku_color(reference, couleur, year_month)",
            "historical_sku_color",
        ),
    ]:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            # Duplicate rows in legacy DB — skip; ingestion still uses SELECT-based dedupe
            pass


def _insert_recommendations(conn, df, df_raw):
    """Populate recommendations table. Merge extra metadata from raw if needed."""
    if df.empty:
        return
    rec = df.copy()
    # Ensure we have Saison (already in m8 output)
    if "Designation" not in rec.columns and "Designation" in df_raw.columns:
        ref_meta = df_raw.drop_duplicates(subset=["Reference"])[["Reference", "Designation", "Rayon", "Matiere"]]
        rec = rec.merge(ref_meta, on="Reference", how="left", suffixes=("", "_meta"))
    probable = rec["forecast_base"].sub(rec.get("confirmed_orders", 0)).clip(lower=0) if "forecast_base" in rec.columns else 0
    rec["probable_additional_base"] = probable
    if "confirmed_delivered" not in rec.columns:
        rec["confirmed_delivered"] = 0
    if "confirmed_clients" not in rec.columns:
        rec["confirmed_clients"] = 0
    for c in ["expected_revenue_conservative", "expected_revenue_optimistic",
              "estimated_cost_conservative", "estimated_cost_optimistic"]:
        if c not in rec.columns:
            rec[c] = 0.0
    if "Designation" not in rec.columns:
        rec["Designation"] = ""
        rec["Rayon"] = ""
        rec["Matiere"] = ""

    cols = [
        "Reference", "Couleur", "Taille", "model_type", "Fournisseur", "Famille", "Theme", "Modele",
        "Client", "Saison", "Critere", "season_type", "product_status", "confidence",
        "forecast_conservative", "forecast_base", "forecast_optimistic",
        "confirmed_orders", "confirmed_delivered", "confirmed_clients",
        "current_stock", "pipeline_stock", "available_inventory",
        "net_to_order_conservative", "net_to_order_base", "net_to_order_optimistic",
        "probable_additional_base",
        "diffusion_rate", "total_buying_clients", "depth_per_client", "reorder_rate",
        "fill_rate", "backorder_rate", "size_share", "size_had_stockout", "total_true_demand",
        "avg_price", "expected_revenue_conservative", "expected_revenue_base", "expected_revenue_optimistic",
        "estimated_cost_conservative", "estimated_cost_base", "estimated_cost_optimistic",
        "estimated_margin_base", "margin_rate_base", "financial_note", "span_months", "explanation",
        "Designation", "Rayon", "Matiere"
    ]

    int_cols = {"forecast_conservative", "forecast_base", "forecast_optimistic", "confirmed_orders",
                 "confirmed_delivered", "confirmed_clients", "current_stock", "pipeline_stock",
                 "available_inventory", "net_to_order_conservative", "net_to_order_base",
                 "net_to_order_optimistic", "probable_additional_base", "total_buying_clients",
                 "size_had_stockout"}
    float_cols = {"diffusion_rate", "depth_per_client", "reorder_rate", "fill_rate", "backorder_rate",
                  "size_share", "total_true_demand", "avg_price", "expected_revenue_conservative",
                  "expected_revenue_base", "expected_revenue_optimistic", "estimated_cost_conservative",
                  "estimated_cost_base", "estimated_cost_optimistic", "estimated_margin_base",
                  "margin_rate_base", "span_months"}

    db_cols = [c.lower() for c in cols]
    placeholders = ",".join(["?" for _ in db_cols])
    sql = f"INSERT INTO recommendations ({','.join(db_cols)}) VALUES ({placeholders})"

    for start in range(0, len(rec), CHUNK_SIZE):
        chunk = rec.iloc[start:start + CHUNK_SIZE]
        rows = []
        for _, row in chunk.iterrows():
            r = []
            for c in cols:
                val = row.get(c, None)
                if c in int_cols:
                    r.append(_safe_val(val, "int"))
                elif c in float_cols:
                    r.append(_safe_val(val, "float"))
                else:
                    r.append(_safe_val(val, "str"))
            rows.append(tuple(r))
        conn.executemany(sql, rows)
    print(f"[DB] recommendations: {len(rec)} rows")


def _insert_forecast_monthly(conn, df):
    """Populate forecast_monthly from monthly_detail DataFrame."""
    if df.empty:
        return
    cols = ["Reference", "Couleur", "Taille", "forecast_month", "forecast_conservative", "forecast_base", "forecast_optimistic", "model_type"]
    df = df[[c for c in cols if c in df.columns]].copy()
    if "forecast_month" in df.columns:
        df["forecast_month"] = df["forecast_month"].astype(str)
    sql = "INSERT INTO forecast_monthly (reference, couleur, taille, forecast_month, forecast_conservative, forecast_base, forecast_optimistic, model_type) VALUES (?,?,?,?,?,?,?,?)"
    for start in range(0, len(df), CHUNK_SIZE):
        chunk = df.iloc[start:start + CHUNK_SIZE]
        rows = []
        for _, row in chunk.iterrows():
            rows.append((
                _safe_val(row.get("Reference"), "str"),
                _safe_val(row.get("Couleur"), "str"),
                _safe_val(row.get("Taille"), "str"),
                _safe_val(row.get("forecast_month"), "str"),
                _safe_val(row.get("forecast_conservative"), "int"),
                _safe_val(row.get("forecast_base"), "int"),
                _safe_val(row.get("forecast_optimistic"), "int"),
                _safe_val(row.get("model_type"), "str"),
            ))
        conn.executemany(sql, rows)
    print(f"[DB] forecast_monthly: {len(df)} rows")


def _insert_historical_demand(conn, df):
    """Populate from monthly_sku_color_size."""
    if df.empty:
        return
    renames = {"CDE_qte": "cde_qte", "LIV_qte": "liv_qte", "RELIQUAT_qte": "reliquat_qte", "ANN_qte": "ann_qte", "Prix": "prix", "num_clients": "num_clients", "true_demand": "true_demand", "year_month": "year_month"}
    use = df.copy()
    use["year_month"] = use["year_month"].astype(str)
    if "Prix" in use.columns and "prix" not in use.columns:
        use["prix"] = use["Prix"]
    for old, new in [("CDE_qte", "cde_qte"), ("LIV_qte", "liv_qte"), ("RELIQUAT_qte", "reliquat_qte"), ("ANN_qte", "ann_qte")]:
        if old in use.columns:
            use[new] = use[old]
    cols_need = ["Reference", "Couleur", "Taille", "year_month", "true_demand", "cde_qte", "liv_qte", "reliquat_qte", "ann_qte", "num_clients", "prix"]
    for c in cols_need:
        if c not in use.columns:
            use[c] = 0
    sql = "INSERT INTO historical_demand (reference, couleur, taille, year_month, true_demand, cde_qte, liv_qte, reliquat_qte, ann_qte, num_clients, prix) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    for start in range(0, len(use), CHUNK_SIZE):
        chunk = use.iloc[start:start + CHUNK_SIZE]
        rows = []
        for _, row in chunk.iterrows():
            rows.append((
                _safe_val(row["Reference"], "str"),
                _safe_val(row["Couleur"], "str"),
                _safe_val(row["Taille"], "str"),
                _safe_val(row["year_month"], "str"),
                _safe_val(row["true_demand"], "float"),
                _safe_val(row.get("cde_qte", 0), "float"),
                _safe_val(row.get("liv_qte", 0), "float"),
                _safe_val(row.get("reliquat_qte", 0), "float"),
                _safe_val(row.get("ann_qte", 0), "float"),
                _safe_val(row.get("num_clients", 0), "int"),
                _safe_val(row.get("prix", 0), "float"),
            ))
        conn.executemany(sql, rows)
    print(f"[DB] historical_demand: {len(use)} rows")


def _insert_historical_sku_color(conn, df):
    """Populate from monthly_sku_color."""
    if df.empty:
        return
    use = df.copy()
    use["year_month"] = use["year_month"].astype(str)
    if "Prix" in use.columns:
        use["prix"] = use["Prix"]
    elif "prix" not in use.columns:
        use["prix"] = 0
    if "num_clients" not in use.columns and "Client" in use.columns:
        use["num_clients"] = use["Client"]
    elif "num_clients" not in use.columns:
        use["num_clients"] = 0
    sql = "INSERT INTO historical_sku_color (reference, couleur, year_month, true_demand, num_clients, prix) VALUES (?,?,?,?,?,?)"
    for start in range(0, len(use), CHUNK_SIZE):
        chunk = use.iloc[start:start + CHUNK_SIZE]
        rows = []
        for _, row in chunk.iterrows():
            rows.append((
                _safe_val(row["Reference"], "str"),
                _safe_val(row["Couleur"], "str"),
                _safe_val(row["year_month"], "str"),
                _safe_val(row["true_demand"], "float"),
                _safe_val(row["num_clients"], "int"),
                _safe_val(row["prix"], "float"),
            ))
        conn.executemany(sql, rows)
    print(f"[DB] historical_sku_color: {len(use)} rows")


def _insert_client_orders(conn, df_raw):
    """Build client_orders from raw aggregated by client, reference, couleur, taille, critere."""
    if df_raw.empty or "Client" not in df_raw.columns:
        return
    df = df_raw.copy()
    if "Critere" not in df.columns:
        df["Critere"] = ""
    if "season_type" not in df.columns:
        df["season_type"] = ""
    if "season_year" not in df.columns:
        df["season_year"] = np.nan
    df["Date_Commande"] = pd.to_datetime(df["Date_Commande"], errors="coerce")
    df["date_commande"] = df["Date_Commande"].dt.strftime("%Y-%m-%d")
    df["true_demand"] = df.get("LIV_qte", 0) + df.get("RELIQUAT_qte", 0)
    agg = df.groupby(["Client", "Reference", "Couleur", "Taille", "Critere", "season_type", "season_year"]).agg({
        "date_commande": "max",
        "CDE_qte": "sum",
        "LIV_qte": "sum",
        "true_demand": "sum",
        "Prix": "mean",
        "CDE_net_ht": "sum",
    }).reset_index()
    agg["client_id"] = agg["Client"].astype(str)
    if "Nom" in df_raw.columns:
        nom_map = df_raw.drop_duplicates(subset=["Client"])[["Client", "Nom"]].set_index("Client")["Nom"]
        agg["client_name"] = agg["Client"].map(lambda x: nom_map.get(x, str(x)))
    else:
        agg["client_name"] = agg["client_id"]
    sql = "INSERT INTO client_orders (client_id, client_name, reference, couleur, taille, critere, season_type, season_year, date_commande, cde_qte, liv_qte, true_demand, prix, cde_net_ht) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    rows = []
    for _, row in agg.iterrows():
        rows.append((
            _safe_val(row["client_id"], "str"),
            _safe_val(row["client_name"], "str"),
            _safe_val(row["Reference"], "str"),
            _safe_val(row["Couleur"], "str"),
            _safe_val(row["Taille"], "str"),
            _safe_val(row["Critere"], "str"),
            _safe_val(row["season_type"], "str"),
            _safe_val(row["season_year"], "float"),
            _safe_val(row["date_commande"], "str"),
            _safe_val(row["CDE_qte"], "float"),
            _safe_val(row["LIV_qte"], "float"),
            _safe_val(row["true_demand"], "float"),
            _safe_val(row["Prix"], "float"),
            _safe_val(row.get("CDE_net_ht", 0), "float"),
        ))
    for start in range(0, len(rows), CHUNK_SIZE):
        conn.executemany(sql, rows[start:start + CHUNK_SIZE])
    print(f"[DB] client_orders: {len(rows)} rows")


def _insert_clients(conn, client_summary):
    """Populate clients table from data['client_summary']."""
    if client_summary is None or client_summary.empty:
        return
    df = client_summary.copy()
    df.columns = [str(c).strip() for c in df.columns]
    id_col = "Client" if "Client" in df.columns else df.columns[0]
    df["client_id"] = df[id_col].astype(str)
    df["client_name"] = df["Nom"] if "Nom" in df.columns else df["client_id"]
    df["total_units"] = df["true_demand"] if "true_demand" in df.columns else 0
    df["num_skus"] = df["Reference"] if "Reference" in df.columns else 0
    df["active_months"] = df["year_month"] if "year_month" in df.columns else 0
    df["total_spend"] = df["CDE_net_ht_sum"] if "CDE_net_ht_sum" in df.columns else 0.0
    if "Date_Commande_min" in df.columns:
        df["first_order"] = pd.to_datetime(df["Date_Commande_min"], errors="coerce").dt.strftime("%Y-%m-%d")
    else:
        df["first_order"] = ""
    if "Date_Commande_max" in df.columns:
        df["last_order"] = pd.to_datetime(df["Date_Commande_max"], errors="coerce").dt.strftime("%Y-%m-%d")
    else:
        df["last_order"] = ""
    df["famille_client"] = df["Famille_client"] if "Famille_client" in df.columns else ""
    for c in ["CP", "Ville", "Pays", "Secteur"]:
        if c in df.columns:
            df[c.lower()] = df[c]
    for c in ["cp", "ville", "pays", "secteur"]:
        if c not in df.columns:
            df[c] = ""
    sql = "INSERT OR REPLACE INTO clients (client_id, client_name, famille_client, cp, ville, pays, secteur, total_units, total_spend, num_skus, active_months, first_order, last_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    rows = []
    for _, row in df.iterrows():
        rows.append((
            _safe_val(row["client_id"], "str"),
            _safe_val(row["client_name"], "str"),
            _safe_val(row.get("famille_client", ""), "str"),
            _safe_val(row.get("cp", ""), "str"),
            _safe_val(row.get("ville", ""), "str"),
            _safe_val(row.get("pays", ""), "str"),
            _safe_val(row.get("secteur", ""), "str"),
            _safe_val(row.get("total_units", 0), "float"),
            _safe_val(row.get("total_spend", 0), "float"),
            _safe_val(row.get("num_skus", 0), "int"),
            _safe_val(row.get("active_months", 0), "int"),
            _safe_val(row.get("first_order", ""), "str"),
            _safe_val(row.get("last_order", ""), "str"),
        ))
    conn.executemany(sql, rows)
    print(f"[DB] clients: {len(rows)} rows")


def _insert_filter_options(conn, rec_df, df_raw):
    """Pre-compute filter options per Saison. Use Client for customer filter (display id/name as in recommendations)."""
    if rec_df.empty:
        return
    # Exclude Saison "L" from filter option counts
    rec_df = rec_df[rec_df["Saison"].astype(str).str.strip().str.upper() != "L"]
    if rec_df.empty:
        return
    if "Saison" not in rec_df.columns:
        rec_df = rec_df.copy()
        rec_df["Saison"] = "Unknown"
    saisons = sorted(rec_df["Saison"].dropna().astype(str).unique().tolist())
    rows = []
    for saison in saisons:
        sub = rec_df[rec_df["Saison"] == saison]
        for col, ftype in [("Fournisseur", "supplier"), ("Famille", "family"), ("Theme", "theme"), ("Modele", "model"), ("Client", "customer")]:
            if col not in sub.columns:
                continue
            for val in sub[col].dropna().astype(str).unique().tolist():
                if not str(val).strip():
                    continue
                cnt = (sub[col] == val).sum()
                rows.append((ftype, str(val).strip(), saison, int(cnt)))
        rows.append(("season", saison, saison, len(sub)))
    if not rows:
        return
    sql = "INSERT INTO filter_options (filter_type, filter_value, saison, item_count) VALUES (?,?,?,?)"
    conn.executemany(sql, rows)
    print(f"[DB] filter_options: {len(rows)} rows")


def _insert_pipeline_metadata(conn):
    """Store pipeline run metadata."""
    import datetime
    conn.execute(
        "INSERT OR REPLACE INTO pipeline_metadata (key, value, updated_at) VALUES (?,?,?)",
        ("last_run", datetime.datetime.utcnow().isoformat(), datetime.datetime.utcnow().isoformat())
    )


def populate_database(pipeline_results):
    """
    Populate SQLite from pipeline results.
    pipeline_results: dict with data, profiles, kpis, sarima_output, catboost_output, size_output, recommendations
    """
    conn = get_connection()
    try:
        print("\n[DB] Populating database...")
        _create_persistent_tables(conn)
        _create_schema(conn)
        rec = pipeline_results.get("recommendations", {})
        reco_df = rec.get("recommendations", pd.DataFrame())
        monthly_detail = rec.get("monthly_detail", pd.DataFrame())
        data = pipeline_results.get("data", {})
        df_raw = data.get("raw", pd.DataFrame())

        _insert_recommendations(conn, reco_df, df_raw)
        _insert_forecast_monthly(conn, monthly_detail)
        _insert_historical_demand(conn, data.get("monthly_sku_color_size", pd.DataFrame()))
        _insert_historical_sku_color(conn, data.get("monthly_sku_color", pd.DataFrame()))
        _insert_client_orders(conn, df_raw)
        _insert_clients(conn, data.get("client_summary", pd.DataFrame()))
        _insert_filter_options(conn, reco_df, df_raw)
        _insert_pipeline_metadata(conn)

        _create_indexes(conn)
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

    size_mb = DB_FILE.stat().st_size / (1024 * 1024) if DB_FILE.exists() else 0
    print(f"[DB] Database ready: {DB_FILE} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Season Config Helpers
# ---------------------------------------------------------------------------

_SEASON_COLUMNS = (
    "id, name, currency, budget, target_margin, budget_band_pct, cost_ratio, "
    "status, is_active, created_at, updated_at"
)


def _row_to_season(row):
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "currency": row[2],
        "budget": row[3],
        "targetMargin": row[4],
        "budgetBandPct": row[5],
        "costRatio": row[6],
        "status": row[7],
        "isActive": bool(row[8]),
        "createdAt": row[9],
        "updatedAt": row[10],
    }


def create_season_config(
    conn, season_id, name, currency, budget, target_margin,
    budget_band_pct=15.0, cost_ratio=0.5,
):
    """Insert a new season config and mark it as active (deactivating others)."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute("UPDATE season_config SET is_active = 0 WHERE is_active = 1")
    conn.execute(
        """INSERT OR REPLACE INTO season_config
           (id, name, currency, budget, target_margin, budget_band_pct, cost_ratio,
            status, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)""",
        (season_id, name, currency, budget, target_margin, budget_band_pct, cost_ratio, now, now),
    )
    conn.commit()


def get_active_season_config(conn):
    """Return the active season config row as a dict, or None."""
    row = conn.execute(
        f"SELECT {_SEASON_COLUMNS} FROM season_config WHERE is_active = 1 LIMIT 1"
    ).fetchone()
    return _row_to_season(row)


def update_season_config(conn, season_id, **kwargs):
    """Update fields on a season config row. Only touches supplied kwargs."""
    import datetime
    allowed = {
        "name", "currency", "budget", "target_margin",
        "budget_band_pct", "cost_ratio", "status", "is_active",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE season_config SET {set_clause} WHERE id = ?", (*fields.values(), season_id))
    conn.commit()


def list_season_configs(conn):
    """Return all season configs as list of dicts."""
    cursor = conn.execute(
        f"SELECT {_SEASON_COLUMNS} FROM season_config ORDER BY created_at DESC"
    )
    return [_row_to_season(row) for row in cursor.fetchall()]


def save_backtest_results(conn, holdout_months, summary, fold_metrics, breakdowns, run_id=None):
    """Persist a completed backtest run and return run_id."""
    import datetime
    import json

    now = datetime.datetime.utcnow().isoformat()
    if run_id is None:
        cursor = conn.execute(
            """
            INSERT INTO backtest_runs (started_at, completed_at, holdout_months, status, summary_json)
            VALUES (?, ?, ?, 'completed', ?)
            """,
            (now, now, holdout_months, json.dumps(summary)),
        )
        run_id = cursor.lastrowid
    else:
        conn.execute(
            """
            UPDATE backtest_runs
            SET completed_at = ?, holdout_months = ?, status = 'completed', summary_json = ?
            WHERE id = ?
            """,
            (now, holdout_months, json.dumps(summary), run_id),
        )
        conn.execute("DELETE FROM backtest_fold_metrics WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM backtest_breakdown WHERE run_id = ?", (run_id,))

    for fold in fold_metrics:
        conn.execute(
            """
            INSERT INTO backtest_fold_metrics (run_id, fold_month, wmape, bias, coverage_80, total_actual)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                fold["fold_month"],
                fold.get("wmape"),
                fold.get("bias"),
                fold.get("coverage_80"),
                fold.get("total_actual"),
            ),
        )

    for row in breakdowns:
        conn.execute(
            """
            INSERT INTO backtest_breakdown
            (run_id, dimension, dimension_value, wmape, bias, coverage_80, sku_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                row["dimension"],
                row["dimension_value"],
                row.get("wmape"),
                row.get("bias"),
                row.get("coverage_80"),
                row.get("sku_count", 0),
            ),
        )

    conn.commit()
    return run_id


def get_latest_backtest(conn):
    """Return latest completed backtest run with fold metrics and breakdowns."""
    import json

    row = conn.execute(
        """
        SELECT id, started_at, completed_at, holdout_months, status, summary_json
        FROM backtest_runs
        WHERE status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None

    run_id = row[0]
    summary = json.loads(row[5]) if row[5] else {}

    folds = conn.execute(
        """
        SELECT fold_month, wmape, bias, coverage_80, total_actual
        FROM backtest_fold_metrics
        WHERE run_id = ?
        ORDER BY fold_month
        """,
        (run_id,),
    ).fetchall()

    breakdown = conn.execute(
        """
        SELECT dimension, dimension_value, wmape, bias, coverage_80, sku_count
        FROM backtest_breakdown
        WHERE run_id = ?
        ORDER BY dimension, dimension_value
        """,
        (run_id,),
    ).fetchall()

    return {
        "runId": run_id,
        "startedAt": row[1],
        "completedAt": row[2],
        "holdoutMonths": row[3],
        "summary": summary,
        "folds": [
            {
                "foldMonth": f[0],
                "wmape": f[1],
                "bias": f[2],
                "coverage80": f[3],
                "totalActual": f[4],
            }
            for f in folds
        ],
        "breakdown": [
            {
                "dimension": b[0],
                "dimensionValue": b[1],
                "wmape": b[2],
                "bias": b[3],
                "coverage80": b[4],
                "skuCount": b[5],
            }
            for b in breakdown
        ],
    }


def insert_backtest_job_running(conn, holdout_months):
    """Create a running backtest job row."""
    import datetime

    now = datetime.datetime.utcnow().isoformat()
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (started_at, holdout_months, status, summary_json)
        VALUES (?, ?, 'running', NULL)
        """,
        (now, holdout_months),
    )
    conn.commit()
    return cursor.lastrowid


def complete_backtest_job(conn, run_id, status, summary=None, error=None):
    """Mark backtest job completed or failed."""
    import datetime
    import json

    now = datetime.datetime.utcnow().isoformat()
    payload = summary if summary is not None else {"error": error}
    conn.execute(
        """
        UPDATE backtest_runs
        SET completed_at = ?, status = ?, summary_json = ?
        WHERE id = ?
        """,
        (now, status, json.dumps(payload) if payload else None, run_id),
    )
    conn.commit()


def get_backtest_job(conn, run_id):
    """Return backtest job status."""
    row = conn.execute(
        """
        SELECT id, started_at, completed_at, holdout_months, status, summary_json
        FROM backtest_runs WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "runId": row[0],
        "startedAt": row[1],
        "completedAt": row[2],
        "holdoutMonths": row[3],
        "status": row[4],
    }
