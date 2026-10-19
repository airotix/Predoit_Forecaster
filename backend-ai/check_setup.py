"""
Quick diagnostic to verify everything is set up correctly.
Run this FIRST before main.py
"""

import os
import sys

print("=" * 60)
print("SETUP DIAGNOSTIC")
print("=" * 60)

script_dir = os.path.dirname(os.path.abspath(__file__))
print(f"\n1. Script directory: {script_dir}")
print(f"2. Current working directory: {os.getcwd()}")
print(f"3. Python executable: {sys.executable}")
print(f"4. Python version: {sys.version}")

# Check module files
print(f"\n5. Module files check:")
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
    "main.py",
    "backtest.py",
]

all_found = True
for mod in required:
    path = os.path.join(script_dir, mod)
    exists = os.path.exists(path)
    status = "[OK] FOUND" if exists else "[X] MISSING"
    print(f"   {status}: {mod}")
    if not exists:
        all_found = False

# Check data file
print(f"\n6. Data file check:")
# Prefer path from config if available
possible_data_paths = []
try:
    import config
    possible_data_paths.append(config.DATA_FILE_PATH)
except Exception:
    pass
# Then check common locations
possible_data_paths.extend([
    os.path.join(script_dir, "data", "raw", "THE_FINAL_10Y_cleaned.csv"),
    os.path.join(script_dir, "data", "raw", "orders.csv"),
    os.path.join(script_dir, "data", "raw", "orders.txt"),
    os.path.join(script_dir, "data", "orders.csv"),
    os.path.join(script_dir, "orders.csv"),
    os.path.join(script_dir, "data.csv"),
    os.path.join(script_dir, "data.txt"),
])

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
    print(f"   All files in {script_dir}:")
    for f in sorted(os.listdir(script_dir)):
        fpath = os.path.join(script_dir, f)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            print(f"      {f} ({size:,} bytes)")
        elif os.path.isdir(fpath):
            print(f"      {f}/ (directory)")
            # List contents of subdirectory
            for sf in os.listdir(fpath):
                sfpath = os.path.join(fpath, sf)
                if os.path.isfile(sfpath):
                    ssize = os.path.getsize(sfpath)
                    print(f"         {sf} ({ssize:,} bytes)")
                elif os.path.isdir(sfpath):
                    print(f"         {sf}/")
                    for ssf in os.listdir(sfpath):
                        ssfpath = os.path.join(sfpath, ssf)
                        if os.path.isfile(ssfpath):
                            sssize = os.path.getsize(ssfpath)
                            print(f"            {ssf} ({sssize:,} bytes)")

# Check Python packages
print(f"\n7. Package check:")
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

# Summary
print(f"\n{'=' * 60}")
if all_found and data_found:
    print("[OK] ALL CHECKS PASSED - Ready to run: python main.py")
else:
    if not all_found:
        print("[X] MISSING MODULE FILES - see above")
    if not data_found:
        print("[X] DATA FILE NOT FOUND")
        print("  Place your data file and update DATA_FILE_PATH in config.py")
print("=" * 60)