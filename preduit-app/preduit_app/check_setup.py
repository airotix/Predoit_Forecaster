"""
Quick diagnostic to verify everything is set up correctly.
Run this FIRST before the pipeline.

Usage: python -m preduit_app.check_setup
"""

import importlib
import os
import sys

print("=" * 60)
print("SETUP DIAGNOSTIC")
print("=" * 60)

pkg_dir = os.path.dirname(os.path.abspath(__file__))
print(f"\n1. App package directory: {pkg_dir}")
print(f"2. Current working directory: {os.getcwd()}")
print(f"3. Python executable: {sys.executable}")
print(f"4. Python version: {sys.version}")

ENGINE_DIR = os.path.dirname(importlib.import_module("preduit_engine").__file__)
print(f"\n5. Engine directory: {ENGINE_DIR}")

print(f"\n6. Engine module files check:")
required = [
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

all_found = True
for mod in required:
    path = os.path.join(ENGINE_DIR, mod)
    exists = os.path.exists(path)
    status = "[OK] FOUND" if exists else "[X] MISSING"
    print(f"   {status}: {mod}")
    if not exists:
        all_found = False

print(f"\n7. Data file check:")
possible_data_paths = []
try:
    import preduit_app.client_config as cc

    possible_data_paths.append(cc.DATA_FILE_PATH)
    legacy = cc.LEGACY_BACKEND_DIR
    possible_data_paths.extend(
        [
            os.path.join(legacy, "data", "raw", "THE_FINAL_10Y_cleaned.csv"),
            os.path.join(legacy, "data", "raw", "orders.csv"),
            os.path.join(legacy, "data", "raw", "orders.txt"),
        ]
    )
except Exception:
    pass

data_found = False
seen = set()
for dp in possible_data_paths:
    dp = os.path.abspath(dp)
    if dp not in seen and os.path.exists(dp):
        seen.add(dp)
        size_mb = os.path.getsize(dp) / (1024 * 1024)
        print(f"   [OK] DATA FILE FOUND: {dp} ({size_mb:.1f} MB)")
        data_found = True

if not data_found:
    print(f"   [X] No data file found in common locations")
    print(f"   Configure FORECASTER_DATA_FILE or place CSV under backend-ai/data/raw/")

print(f"\n8. Package check:")
packages = {
    "pandas": "pandas",
    "numpy": "numpy",
    "pmdarima": "pmdarima",
    "statsmodels": "statsmodels",
    "catboost": "catboost",
    "shap": "shap",
    "sklearn": "scikit-learn",
    "openpyxl": "openpyxl",
}

for import_name, pip_name in packages.items():
    try:
        mod = __import__(import_name)
        version = getattr(mod, "__version__", "unknown")
        print(f"   [OK] {pip_name}: {version}")
    except ImportError:
        print(f"   [X] {pip_name}: NOT INSTALLED -> pip install {pip_name}")

print(f"\n{'=' * 60}")
if all_found and data_found:
    print("[OK] ALL CHECKS PASSED - Ready: python -m preduit_app.main")
else:
    if not all_found:
        print("[X] MISSING ENGINE MODULE FILES - see above")
    if not data_found:
        print("[X] DATA FILE NOT FOUND — see preduit_app.client_config")
print("=" * 60)
