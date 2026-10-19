"""
Incremental data ingest: normalize uploads to pipeline schema, upsert facts tables,
append to ingest buffer for full pipeline merges, refresh non-ML aggregates.
"""

from __future__ import annotations

import datetime
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from database import _safe_val, get_connection
from m1_data_preparation import (
    _standardize_columns,
    aggregate_monthly_sku_color,
    aggregate_monthly_sku_color_size,
    parse_and_prepare,
    parse_order_dates,
)

BASE_DIR = Path(__file__).resolve().parent


def _ingest_append_path() -> Path:
    return BASE_DIR / "data" / "raw" / "ingest_append.csv"


def _pipeline_merged_path() -> Path:
    return BASE_DIR / "data" / "raw" / ".pipeline_merged.csv"


def normalize_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Standardize headers and run M1 parse_and_prepare.
    Returns (df_standardized_before_parse, df_parsed) for append + upsert.
    """
    df_std = _standardize_columns(df.copy())
    df_parsed = parse_and_prepare(df_std.copy())
    return df_std, df_parsed


def append_to_ingest_csv(df_std: pd.DataFrame) -> None:
    """Append standardized rows so the next full pipeline run can merge with base CSV."""
    path = _ingest_append_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    df_out = df_std.copy()
    if "Date_Commande" in df_out.columns:
        df_out["Date_Commande"] = parse_order_dates(df_out['Date_Commande']).dt.strftime('%Y-%m-%d')
    df_out = with_line_keys(df_out)
    df_out.to_csv(path, mode="a", header=header, index=False, encoding="utf-8")


def merge_config_csv_with_append() -> Optional[str]:
    """
    If ingest_append.csv exists, merge with config DATA_FILE_PATH and write .pipeline_merged.csv.
    Returns path to merged file, or None if no append file.
    """
    from config import DATA_FILE_PATH

    append_path = _ingest_append_path()
    if not append_path.is_file() or append_path.stat().st_size == 0:
        return None
    base = pd.read_csv(DATA_FILE_PATH, low_memory=False, dtype=str) if os.path.exists(DATA_FILE_PATH) else pd.DataFrame()
    extra = pd.read_csv(append_path, low_memory=False, dtype=str)
    from m1_data_preparation import _standardize_columns
    base=_standardize_columns(base) if not base.empty else base
    extra=_standardize_columns(extra)
    base=with_line_keys(base) if not base.empty else base;extra=with_line_keys(extra)
    merged = pd.concat([base, extra], ignore_index=True).drop_duplicates(subset=['Source_Line_Key'],keep='last')
    out = _pipeline_merged_path()
    merged.to_csv(out, index=False, encoding="utf-8")
    return str(out.resolve())


def bump_import_metadata(conn) -> None:
    """Touch pipeline_metadata so SSE clients can refetch actuals without ML run."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO pipeline_metadata (key, value, updated_at) VALUES (?,?,?)",
        ("last_import", now, now),
    )


def _client_orders_agg(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Same aggregation as database._insert_client_orders."""
    if df_raw.empty or "Client" not in df_raw.columns:
        return pd.DataFrame()
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
    agg["season_year"] = pd.to_numeric(agg["season_year"], errors="coerce").fillna(0.0)
    return agg


def _row_tuple_client_order(row) -> Tuple:
    return (
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
    )


def _upsert_client_orders(conn, agg: pd.DataFrame) -> Dict[str, int]:
    added = updated = skipped = 0
    sql_sel = """
        SELECT client_name, date_commande, cde_qte, liv_qte, true_demand, prix, cde_net_ht
        FROM client_orders
        WHERE client_id = ? AND reference = ? AND couleur = ? AND taille = ?
          AND critere = ? AND season_type = ?
          AND COALESCE(season_year, -9e18) = COALESCE(?, -9e18)
    """
    sql_ins = """INSERT INTO client_orders (
        client_id, client_name, reference, couleur, taille, critere, season_type, season_year,
        date_commande, cde_qte, liv_qte, true_demand, prix, cde_net_ht
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    sql_upd = """UPDATE client_orders SET
        client_name=?, date_commande=?, cde_qte=?, liv_qte=?, true_demand=?, prix=?, cde_net_ht=?
        WHERE client_id = ? AND reference = ? AND couleur = ? AND taille = ?
          AND critere = ? AND season_type = ?
          AND COALESCE(season_year, -9e18) = COALESCE(?, -9e18)
    """
    for _, row in agg.iterrows():
        tup = _row_tuple_client_order(row)
        sy = _safe_val(row["season_year"], "float")
        cur = conn.execute(
            sql_sel,
            (tup[0], tup[2], tup[3], tup[4], tup[5], tup[6], sy),
        )
        ex = cur.fetchone()
        new_vals = (tup[1], tup[8], tup[9], tup[10], tup[11], tup[12], tup[13])
        if ex is None:
            conn.execute(sql_ins, tup)
            added += 1
        else:
            old = tuple(ex)
            same = True
            for i in range(len(old)):
                a, b = old[i], new_vals[i]
                if i in (2, 3, 4, 5, 6):
                    if abs(float(a or 0) - float(b or 0)) > 1e-4:
                        same = False
                        break
                else:
                    if str(a or "") != str(b or ""):
                        same = False
                        break
            if same:
                skipped += 1
            else:
                conn.execute(
                    sql_upd,
                    (
                        tup[1], tup[8], tup[9], tup[10], tup[11], tup[12], tup[13],
                        tup[0], tup[2], tup[3], tup[4], tup[5], tup[6], sy,
                    ),
                )
                updated += 1
    return {"added": added, "updated": updated, "skipped": skipped}


def _hd_key(row) -> Tuple:
    return (
        _safe_val(row["Reference"], "str"),
        _safe_val(row["Couleur"], "str"),
        _safe_val(row["Taille"], "str"),
        _safe_val(str(row["year_month"]), "str"),
    )


def _upsert_historical_demand(conn, df: pd.DataFrame) -> Dict[str, int]:
    added = updated = skipped = 0
    if df.empty:
        return {"added": 0, "updated": 0, "skipped": 0}
    use = df.copy()
    use["year_month"] = use["year_month"].astype(str)
    for old, new in [("CDE_qte", "cde_qte"), ("LIV_qte", "liv_qte"), ("RELIQUAT_qte", "reliquat_qte"), ("ANN_qte", "ann_qte")]:
        if old in use.columns:
            use[new] = use[old]
    for c in ["cde_qte", "liv_qte", "reliquat_qte", "ann_qte", "num_clients", "prix"]:
        if c not in use.columns:
            use[c] = 0
    if "Prix" in use.columns and "prix" not in use.columns:
        use["prix"] = use["Prix"]

    sql_sel = """SELECT true_demand, cde_qte, liv_qte, reliquat_qte, ann_qte, num_clients, prix
        FROM historical_demand WHERE reference=? AND couleur=? AND taille=? AND year_month=?"""
    sql_ins = """INSERT INTO historical_demand (
        reference, couleur, taille, year_month, true_demand, cde_qte, liv_qte, reliquat_qte, ann_qte, num_clients, prix
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)"""
    sql_upd = """UPDATE historical_demand SET true_demand=?, cde_qte=?, liv_qte=?, reliquat_qte=?, ann_qte=?, num_clients=?, prix=?
        WHERE reference=? AND couleur=? AND taille=? AND year_month=?"""

    for _, row in use.iterrows():
        key = _hd_key(row)
        vals = (
            _safe_val(row["true_demand"], "float"),
            _safe_val(row.get("cde_qte", 0), "float"),
            _safe_val(row.get("liv_qte", 0), "float"),
            _safe_val(row.get("reliquat_qte", 0), "float"),
            _safe_val(row.get("ann_qte", 0), "float"),
            _safe_val(row.get("num_clients", 0), "int"),
            _safe_val(row.get("prix", 0), "float"),
        )
        cur = conn.execute(sql_sel, key)
        ex = cur.fetchone()
        if ex is None:
            conn.execute(sql_ins, key + vals)
            added += 1
        else:
            same = True
            for i, (a, b) in enumerate(zip(ex, vals)):
                if i == 5:
                    if int(a or 0) != int(b or 0):
                        same = False
                        break
                else:
                    if abs(float(a or 0) - float(b or 0)) > 1e-4:
                        same = False
                        break
            if same:
                skipped += 1
            else:
                conn.execute(sql_upd, vals + key)
                updated += 1
    return {"added": added, "updated": updated, "skipped": skipped}


def _upsert_historical_sku_color(conn, df: pd.DataFrame) -> Dict[str, int]:
    added = updated = skipped = 0
    if df.empty:
        return {"added": 0, "updated": 0, "skipped": 0}
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

    sql_sel = "SELECT true_demand, num_clients, prix FROM historical_sku_color WHERE reference=? AND couleur=? AND year_month=?"
    sql_ins = "INSERT INTO historical_sku_color (reference, couleur, year_month, true_demand, num_clients, prix) VALUES (?,?,?,?,?,?)"
    sql_upd = "UPDATE historical_sku_color SET true_demand=?, num_clients=?, prix=? WHERE reference=? AND couleur=? AND year_month=?"

    for _, row in use.iterrows():
        key = (
            _safe_val(row["Reference"], "str"),
            _safe_val(row["Couleur"], "str"),
            _safe_val(row["year_month"], "str"),
        )
        vals = (
            _safe_val(row["true_demand"], "float"),
            _safe_val(row["num_clients"], "int"),
            _safe_val(row["prix"], "float"),
        )
        cur = conn.execute(sql_sel, key)
        ex = cur.fetchone()
        if ex is None:
            conn.execute(sql_ins, key + vals)
            added += 1
        else:
            if abs(float(ex[0] or 0) - vals[0]) < 1e-6 and int(ex[1] or 0) == vals[1] and abs(float(ex[2] or 0) - vals[2]) < 1e-6:
                skipped += 1
            else:
                conn.execute(sql_upd, vals + key)
                updated += 1
    return {"added": added, "updated": updated, "skipped": skipped}


def dedupe_and_upsert(conn, df_parsed: pd.DataFrame) -> Dict[str, Any]:
    """
    Upsert client_orders, historical_demand, historical_sku_color. Returns aggregate counts.
    """
    if df_parsed.empty:
        return {"added": 0, "updated": 0, "skipped": 0, "by_table": {}}

    agg = _client_orders_agg(df_parsed)
    co = _upsert_client_orders(conn, agg)

    msc = aggregate_monthly_sku_color(df_parsed)
    mscs = aggregate_monthly_sku_color_size(df_parsed)
    hd = _upsert_historical_demand(conn, mscs)
    hsc = _upsert_historical_sku_color(conn, msc)

    total_added = co["added"] + hd["added"] + hsc["added"]
    total_updated = co["updated"] + hd["updated"] + hsc["updated"]
    total_skipped = co["skipped"] + hd["skipped"] + hsc["skipped"]

    return {
        "added": total_added,
        "updated": total_updated,
        "skipped": total_skipped,
        "by_table": {
            "client_orders": co,
            "historical_demand": hd,
            "historical_sku_color": hsc,
        },
    }


def refresh_non_ml_aggregates(conn) -> None:
    """Recompute clients dimension from client_orders; does not touch ML output tables."""
    conn.execute(
        """
        INSERT OR REPLACE INTO clients (
            client_id, client_name, famille_client, cp, ville, pays, secteur,
            total_units, total_spend, num_skus, active_months, first_order, last_order
        )
        SELECT
            client_id,
            MAX(client_name) AS client_name,
            '', '', '', '', '',
            SUM(true_demand) AS total_units,
            SUM(cde_net_ht) AS total_spend,
            COUNT(DISTINCT reference || '|' || couleur) AS num_skus,
            COUNT(DISTINCT substr(date_commande, 1, 7)) AS active_months,
            MIN(date_commande) AS first_order,
            MAX(date_commande) AS last_order
        FROM client_orders
        GROUP BY client_id
        """
    )
    conn.execute("DELETE FROM filter_options WHERE filter_type = 'customer'")
    conn.execute(
        """
        INSERT INTO filter_options (filter_type, filter_value, saison, item_count)
        SELECT 'customer', client_name, 'All', COUNT(*)
        FROM client_orders
        GROUP BY client_name
        """
    )


def load_mock_erp_dataframe() -> pd.DataFrame:
    """Sample rows from the configured base CSV — replace with real ERP client later."""
    from config import DATA_FILE_PATH

    if not os.path.exists(DATA_FILE_PATH):
        raise FileNotFoundError(f"No base CSV for ERP mock: {DATA_FILE_PATH}")
    return pd.read_csv(DATA_FILE_PATH, nrows=50, low_memory=False)


def new_job_id() -> str:
    return str(uuid.uuid4())


def insert_job_running(conn, job_id: str, job_type: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO import_jobs (job_id, job_type, status, rows_added, rows_updated, rows_skipped, error_message, started_at, finished_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (job_id, job_type, "running", 0, 0, 0, None, now, None),
    )


def update_job_complete(
    conn,
    job_id: str,
    rows_added: int,
    rows_updated: int,
    rows_skipped: int,
    error_message: Optional[str] = None,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    st = "error" if error_message else "complete"
    conn.execute(
        """
        UPDATE import_jobs SET status=?, rows_added=?, rows_updated=?, rows_skipped=?, error_message=?, finished_at=?
        WHERE job_id=?
        """,
        (st, rows_added, rows_updated, rows_skipped, error_message, now, job_id),
    )


def with_line_keys(frame):
    import hashlib,json
    result=frame.copy()
    if 'Source_Line_Key' in result and result.Source_Line_Key.notna().all():return result
    names=[k for k in ['Reference_CDE','Client','Magasin','Reference','Couleur','Taille','Date_Commande','Critere'] if k in result]
    identifiers=result[names].fillna('').astype(str)
    if 'Date_Commande' in identifiers:
        identifiers['Date_Commande']=parse_order_dates(identifiers.Date_Commande).dt.strftime('%Y-%m-%d').fillna('')
    occurrences=identifiers.groupby(names,dropna=False).cumcount()
    result['Source_Line_Key']=[hashlib.sha256(json.dumps([list(row),int(n)]).encode()).hexdigest() for row,n in zip(identifiers.itertuples(index=False,name=None),occurrences)]
    return result
