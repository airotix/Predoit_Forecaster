"""
Verify SQLite database is correctly populated and API-style queries return correct shapes.
Run after: python main.py
Usage: python test_db.py
"""

import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "forecast.db"

EXPECTED_INDEXES = [
    "idx_reco_reference", "idx_reco_couleur", "idx_reco_ref_coul", "idx_reco_critere",
    "idx_reco_saison", "idx_reco_famille", "idx_reco_fournisseur", "idx_reco_theme",
    "idx_reco_modele", "idx_reco_client", "idx_reco_confidence", "idx_reco_model_type",
    "idx_reco_net_to_order_base", "idx_reco_forecast_base",
    "idx_fm_ref_coul", "idx_fm_forecast_month",
    "idx_hd_ref_coul", "idx_hd_ref_coul_taille", "idx_hd_year_month",
    "idx_hsc_ref_coul",
    "idx_co_client_id", "idx_co_ref_coul", "idx_co_critere", "idx_co_client_name",
    "idx_fo_filter_type", "idx_fo_type_saison",
]

TABLES = [
    "recommendations", "forecast_monthly", "historical_demand", "historical_sku_color",
    "client_orders", "clients", "filter_options", "pipeline_metadata",
]


def main():
    print("Database verification\n" + "=" * 50)

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run 'python main.py' first to generate the pipeline and populate the DB.")
        return 1

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"Database: {DB_PATH} ({size_mb:.1f} MB)\n")

    from database import get_connection

    conn = get_connection()

    # Table row counts
    print("Table row counts:")
    for table in TABLES:
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
            n = cur.fetchone()[0]
            print(f"  {table}: {n:,}")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")
    print()

    # Query tests with timing
    print("Query tests:")

    # Articles-style query
    t0 = time.perf_counter()
    cur = conn.execute(
        "SELECT reference, couleur, taille, saison, fournisseur, forecast_base, current_stock, confirmed_orders FROM recommendations WHERE saison IS NOT NULL LIMIT 5000"
    )
    rows = cur.fetchall()
    refs = list({r[0] for r in rows})
    t1 = time.perf_counter()
    print(f"  Articles query (sample {len(refs)} refs): {len(rows):,} rows in {(t1-t0)*1000:.0f}ms")

    # Verify article response shape (one article has id, season, matrix, demandTrend, etc.)
    from api_server import _get_filtered_recommendations, _get_demand_trend_by_references, _rows_to_articles
    t0 = time.perf_counter()
    rows2 = _get_filtered_recommendations(season=None, supplier=None, family=None, theme=None, model=None, customer=None, search_query=None)
    if rows2:
        refs2 = list({r["reference"] for r in rows2})[:100]
        conn2 = get_connection()
        try:
            trend = _get_demand_trend_by_references(conn2, refs2)
        finally:
            conn2.close()
        articles = _rows_to_articles(rows2[:500], trend)
    else:
        articles = []
    t1 = time.perf_counter()
    if articles:
        a = articles[0]
        required = {"id", "season", "supplier", "customer", "family", "theme", "model", "sizes", "colors", "matrix", "demandTrend", "price", "cost"}
        missing = required - set(a.keys())
        if missing:
            print(f"  Article shape check: MISSING keys {missing}")
        else:
            matrix_ok = not a.get("matrix") or all(
                set(cell) >= {"forecast", "stock", "orders"}
                for col_d in a["matrix"].values()
                for cell in col_d.values()
            )
            trend_ok = not a.get("demandTrend") or (a["demandTrend"] and "date" in a["demandTrend"][0] and "value" in a["demandTrend"][0])
            if matrix_ok and trend_ok:
                print(f"  Article shape check: OK (id, matrix.forecast/stock/orders, demandTrend.date/value)")
            else:
                print(f"  Article shape check: matrix or demandTrend shape unexpected")
        print(f"  Full articles build (sample): {len(articles)} articles in {(t1-t0)*1000:.0f}ms")
    else:
        print(f"  No articles (empty DB or no data)")

    # Filter options
    t0 = time.perf_counter()
    cur = conn.execute("SELECT filter_type, filter_value FROM filter_options")
    fo_rows = cur.fetchall()
    t1 = time.perf_counter()
    types = set(r[0] for r in fo_rows)
    print(f"  Filter options: {len(types)} categories, {len(fo_rows):,} rows in {(t1-t0)*1000:.0f}ms")

    # Customers list
    t0 = time.perf_counter()
    cur = conn.execute("SELECT client, saison, confirmed_orders, forecast_base FROM recommendations WHERE client IS NOT NULL LIMIT 10000")
    cust_rows = cur.fetchall()
    t1 = time.perf_counter()
    print(f"  Customers list (sample): {len(set(r[0] for r in cust_rows))} customers in {(t1-t0)*1000:.0f}ms")

    # Customer detail
    if cust_rows:
        sample_client = cust_rows[0][0]
        t0 = time.perf_counter()
        cur = conn.execute(
            "SELECT reference, couleur, taille, saison, fournisseur, famille, theme, modele, client, forecast_base, current_stock, confirmed_orders, avg_price, estimated_cost_base FROM recommendations WHERE client = ? LIMIT 500",
            (sample_client,),
        )
        detail_rows = cur.fetchall()
        t1 = time.perf_counter()
        print(f"  Customer detail (client={sample_client}): {len(detail_rows)} rows in {(t1-t0)*1000:.0f}ms")
    print()

    # Index verification
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_%'")
    existing = {r[0] for r in cur.fetchall()}
    found = [n for n in EXPECTED_INDEXES if n in existing]
    missing = [n for n in EXPECTED_INDEXES if n not in existing]
    print(f"Index verification: {len(found)}/{len(EXPECTED_INDEXES)} indexes present", end="")
    if missing:
        print(f" (missing: {missing})")
    else:
        print(" OK")
    conn.close()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    exit(main())
