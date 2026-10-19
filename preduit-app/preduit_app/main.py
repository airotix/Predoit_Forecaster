"""
============================================================
MAIN ORCHESTRATOR
Runs all Phase 1 modules in sequence.
============================================================

Usage:
    python -m preduit_app.main
    python -m preduit_app.main --data path/to/your/file.csv
"""

import importlib
import os
import sys
import time

import preduit_app.client_config  # noqa: F401 — load .env before engine merges overlay

from preduit_engine.config import DATA_FILE_PATH
from preduit_engine.database import populate_database
from preduit_engine.ingestion import merge_config_csv_with_append
from preduit_engine.m1_data_preparation import run_module1
from preduit_engine.m2_model_assignment import run_module2
from preduit_engine.m3_kpis import run_module3
from preduit_engine.m4_sarima import run_module4
from preduit_engine.m5_catboost import run_module5
from preduit_engine.m6_size_curves import run_module6
from preduit_engine.m7_recommendations import run_module7
from preduit_engine.m8_output import run_module8


ENGINE_DIR = os.path.dirname(importlib.import_module("preduit_engine").__file__)


def run_phase1(data_path=None):
    """
    Execute the complete Phase 1 pipeline.
    """
    start_time = time.time()

    print("╔" + "═" * 58 + "╗")
    print("║  AI-DRIVEN ORDER PLANNING — PHASE 1 EXECUTION          ║")
    print("║  SARIMA + CatBoost Forecasting Pipeline                 ║")
    print("╚" + "═" * 58 + "╝")
    print()

    filepath = data_path or DATA_FILE_PATH
    if data_path is None:
        try:
            merged = merge_config_csv_with_append()
            if merged:
                filepath = merged
                print(f"[INFO] Using merged pipeline input: {filepath}")
        except Exception as ex:
            print(f"[WARN] merge_config_csv_with_append failed: {ex}")

    if not os.path.exists(filepath):
        msg = (
            f"Data file not found: {filepath} (cwd={os.getcwd()}, engine={ENGINE_DIR})"
        )
        print(f"[ERROR] {msg}")
        raise FileNotFoundError(msg)

    required_modules = [
        "config.py",
        "m1_data_preparation.py",
        "m2_model_assignment.py",
        "m3_kpis.py",
        "m4_sarima.py",
        "m5_catboost.py",
        "m6_size_curves.py",
        "m7_recommendations.py",
        "m8_output.py",
    ]
    missing = []
    for mod in required_modules:
        mod_path = os.path.join(ENGINE_DIR, mod)
        if not os.path.exists(mod_path):
            missing.append(mod)

    if missing:
        print(f"[ERROR] Missing engine module files in {ENGINE_DIR}:")
        for m in missing:
            print(f"        ✗ {m}")
        sys.exit(1)

    print(f"[INFO] Engine directory: {ENGINE_DIR}")
    print(f"[INFO] Data file: {filepath}")
    print(f"[INFO] All module files found ✓")
    print()

    data = run_module1(filepath)

    profiles = run_module2(data["monthly_sku_color"])

    kpis = run_module3(data["raw"], data["monthly_sku_color"], profiles)

    sarima_output = run_module4(data["monthly_sku_color"], profiles)

    catboost_output = run_module5(
        data["monthly_sku_color_size"],
        data["monthly_sku_color"],
        data["raw"],
        kpis,
        profiles,
        sarima_output,
    )

    size_output = run_module6(
        data["raw"],
        kpis["size_kpis"],
        sarima_output["sarima_forecasts"],
        catboost_output["catboost_forecasts"],
    )

    reco_output = run_module7(
        size_output["sarima_forecasts_by_size"],
        size_output["catboost_forecasts_validated"],
        data["raw"],
        data["stock_info"],
        kpis["sku_kpis"],
        kpis["size_kpis"],
        data["critere_map"],
    )

    run_module8(
        reco_output["recommendations"],
        reco_output["monthly_detail"],
        sarima_output["sarima_results"],
        catboost_output.get("catboost_models"),
        kpis["sku_kpis"],
    )

    populate_database({
        "data": data,
        "profiles": profiles,
        "kpis": kpis,
        "sarima_output": sarima_output,
        "catboost_output": catboost_output,
        "size_output": size_output,
        "recommendations": reco_output,
    })

    elapsed = time.time() - start_time
    print("\n" + "╔" + "═" * 58 + "╗")
    print(
        f"║  PHASE 1 COMPLETE — {elapsed:.1f} seconds"
        + " " * max(0, 38 - len(f"{elapsed:.1f}"))
        + "║"
    )
    print("╚" + "═" * 58 + "╝")

    return {
        "data": data,
        "profiles": profiles,
        "kpis": kpis,
        "sarima_output": sarima_output,
        "catboost_output": catboost_output,
        "size_output": size_output,
        "recommendations": reco_output,
    }


if __name__ == "__main__":
    data_path = None
    for arg in sys.argv[1:]:
        if arg.startswith("--data"):
            continue
        if not arg.startswith("--"):
            data_path = arg

    if "--data" in sys.argv:
        idx = sys.argv.index("--data")
        if idx + 1 < len(sys.argv):
            data_path = sys.argv[idx + 1]

    try:
        run_phase1(data_path)
    except FileNotFoundError as err:
        print(err)
        sys.exit(1)
