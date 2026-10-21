"""
SQLite serving layer for the forecasting pipeline.
Schema creation, indexes, and population from pipeline results.
Default DB: backend-ai/data/joolan_live.db. Override with FORECASTER_DB_PATH.
Legacy databases are retained separately and never chosen automatically.
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

import paths
BASE_DIR = paths.HOME


def _resolve_db_file() -> Path:
    # One deterministic default (paths.LIVE_DB); FORECASTER_DB_PATH overrides it.
    return paths.LIVE_DB


DB_FILE = _resolve_db_file()

CHUNK_SIZE = 10_000


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
    from planning import ensure_schema
    ensure_schema(conn)
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
    """)
    from planning import ensure_schema
    ensure_schema(conn)


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
            confidence_reason TEXT,
            calibration_points REAL,
            calibration_wape REAL,
            calibration_bias REAL,
            forecast_conservative INTEGER,
            forecast_base INTEGER,
            forecast_optimistic INTEGER,
            model_forecast_conservative REAL,
            model_forecast_base REAL,
            model_forecast_optimistic REAL,
            season_booked REAL,
            season_delivered REAL,
            all_open_orders REAL,
            historical_delivered REAL,
            delivery_open REAL,
            delivery_unknown REAL,
            next_delivery_date TEXT,
            required_future_conservative REAL,
            required_future_base REAL,
            required_future_optimistic REAL,
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
            model_forecast_conservative REAL,
            model_forecast_base REAL,
            model_forecast_optimistic REAL,
            season_booked REAL,
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
    if not conn.in_transaction: conn.execute('BEGIN IMMEDIATE')
    for script in (_DROP_PIPELINE_TABLES, _PIPELINE_TABLES_DDL):
        for statement in script.split(';'):
            if statement.strip(): conn.execute(statement)
    conn.execute('ALTER TABLE recommendations ADD COLUMN unit_selling_price REAL')
    conn.execute('ALTER TABLE recommendations ADD COLUMN unit_purchase_cost REAL')


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
            # Duplicate rows in legacy DB â€” skip; ingestion still uses SELECT-based dedupe
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
    probable = rec["forecast_base"].sub(rec.get("season_booked",rec.get("confirmed_orders", 0))).clip(lower=0) if "forecast_base" in rec.columns else 0
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
        "Client", "Saison", "Critere", "season_type", "product_status", "confidence", "confidence_reason", "calibration_points", "calibration_wape", "calibration_bias",
        "forecast_conservative", "forecast_base", "forecast_optimistic",
        "model_forecast_conservative", "model_forecast_base", "model_forecast_optimistic", "season_booked", "season_delivered",
        "all_open_orders", "historical_delivered", "delivery_open", "delivery_unknown", "required_future_conservative", "required_future_base", "required_future_optimistic",
        "next_delivery_date",
        "confirmed_orders", "confirmed_delivered", "confirmed_clients",
        "current_stock", "pipeline_stock", "available_inventory",
        "net_to_order_conservative", "net_to_order_base", "net_to_order_optimistic",
        "probable_additional_base",
        "diffusion_rate", "total_buying_clients", "depth_per_client", "reorder_rate",
        "fill_rate", "backorder_rate", "size_share", "size_had_stockout", "total_true_demand",
        "avg_price", "expected_revenue_conservative", "expected_revenue_base", "expected_revenue_optimistic",
        "estimated_cost_conservative", "estimated_cost_base", "estimated_cost_optimistic",
        "estimated_margin_base", "margin_rate_base", "financial_note", "span_months", "explanation",
        "Designation", "Rayon", "Matiere", "unit_selling_price", "unit_purchase_cost"
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

    int_cols -= {"forecast_conservative", "forecast_base", "forecast_optimistic", "confirmed_orders", "confirmed_delivered", "current_stock", "pipeline_stock", "available_inventory", "net_to_order_conservative", "net_to_order_base", "net_to_order_optimistic", "probable_additional_base"}
    float_cols |= {"forecast_conservative", "forecast_base", "forecast_optimistic", "confirmed_orders", "confirmed_delivered", "current_stock", "pipeline_stock", "available_inventory", "net_to_order_conservative", "net_to_order_base", "net_to_order_optimistic", "probable_additional_base", "unit_selling_price", "unit_purchase_cost"}
    float_cols |= {'model_forecast_'+s for s in ('conservative','base','optimistic')} | {'season_booked','season_delivered'}
    float_cols |= {'calibration_points','calibration_wape','calibration_bias'}
    float_cols |= {'all_open_orders','historical_delivered','delivery_open','delivery_unknown'} | {'required_future_'+s for s in ('conservative','base','optimistic')}
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
                    r.append(None if val is None or pd.isna(val) else float(val))
                else:
                    r.append(_safe_val(val, "str"))
            rows.append(tuple(r))
        conn.executemany(sql, rows)
    print(f"[DB] recommendations: {len(rec)} rows")


def _insert_forecast_monthly(conn, df):
    """Persist operational projections and their original statistical predictions."""
    if df.empty:return
    cols=['Reference','Couleur','Taille','forecast_month','forecast_conservative','forecast_base','forecast_optimistic','model_type','model_forecast_conservative','model_forecast_base','model_forecast_optimistic','season_booked']
    sql='INSERT INTO forecast_monthly ('+','.join(c.lower() for c in cols)+') VALUES ('+','.join('?' for _ in cols)+')'
    for start in range(0,len(df),CHUNK_SIZE):
        rows=[]
        for _,row in df.iloc[start:start+CHUNK_SIZE].iterrows():
            rows.append(tuple(_safe_val(row.get(c),'str' if c in ('Reference','Couleur','Taille','forecast_month','model_type') else 'float') for c in cols))
        conn.executemany(sql,rows)
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
    if 'true_demand' not in df:
        df["true_demand"] = df.get("LIV_qte", 0) + df.get("RELIQUAT_qte", 0)
    agg = df.groupby(["Client", "Reference", "Couleur", "Taille", "Critere", "season_type", "season_year"],dropna=False).agg({
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
    df["total_units"] = df["true_demand_sum"] if "true_demand_sum" in df.columns else df["true_demand"] if "true_demand" in df.columns else 0
    df["num_skus"] = df["Reference_nunique"] if "Reference_nunique" in df.columns else df["Reference"] if "Reference" in df.columns else 0
    df["active_months"] = df["year_month_nunique"] if "year_month_nunique" in df.columns else df["year_month"] if "year_month" in df.columns else 0
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
        ("last_run", datetime.datetime.now(datetime.timezone.utc).isoformat(), datetime.datetime.now(datetime.timezone.utc).isoformat())
    )


def populate_database(pipeline_results):
    """
    Populate SQLite from pipeline results.
    pipeline_results: dict with data, profiles, kpis, sarima_output, catboost_output, size_output, recommendations
    """
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        print("\n[DB] Populating database...")
        _create_persistent_tables(conn)
        conn.execute('BEGIN IMMEDIATE')
        publication=pipeline_results.get('lineage',{})
        if publication.get('source')=='fresh':
            from operating_scope import revision
            if publication.get('operatingScopeRevision')!=revision(conn):raise ValueError('Business scope changed during forecasting. Previous published results were retained; run the forecast again.')
            current=dict(conn.execute('SELECT key,value FROM joolan_state'))
            if current.get('fresh_run')!=publication.get('freshRun'):raise ValueError('Active Joolan export changed during forecasting. Run the forecast again.')
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
        import json
        lineage=pipeline_results.get("lineage",{})
        conn.execute("INSERT OR REPLACE INTO pipeline_metadata VALUES(?,?,?)",("lineage",json.dumps(lineage),lineage.get("createdAt","")))
        _insert_order_ledger(conn,df_raw)

        _create_indexes(conn)
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
        # Keep publication short; vacuum is an explicit maintenance operation.
    finally:
        conn.close()

    size_mb = DB_FILE.stat().st_size / (1024 * 1024) if DB_FILE.exists() else 0
    print(f"[DB] Database ready: {DB_FILE} ({size_mb:.1f} MB)")


def _insert_order_ledger(conn,df):
    import collections,hashlib,json
    from planning import ensure_schema
    conn.execute('DELETE FROM order_lines')
    occurrence=collections.Counter()
    rows=[]
    for row in df.to_dict('records'):
        identity=tuple(str(row.get(k,'')) for k in ('Reference_CDE','Client','Magasin','Reference','Couleur','Taille'))
        occurrence[identity]+=1
        key=hashlib.sha256(json.dumps([identity,occurrence[identity]]).encode()).hexdigest()
        payload={k:(None if pd.isna(v) else str(v) if isinstance(v,(pd.Timestamp,pd.Period)) else v) for k,v in row.items()}
        rows.append((key,json.dumps(payload,default=str)))
    conn.executemany('INSERT INTO order_lines VALUES(?,?)',rows)
