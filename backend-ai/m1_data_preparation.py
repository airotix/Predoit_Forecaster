"""
============================================================
MODULE 1: DATA LOADING & PREPARATION
- Load raw data (auto-detect separator and encoding)
- Parse dates
- Extract season info from Critere (for display)
- Compute true_demand
- Aggregate to monthly level
============================================================
"""

import pandas as pd
import numpy as np
import re
import os
from config import *


# ─────────────────────────────────────────────
# EXPECTED COLUMNS (standardized clean names)
# ─────────────────────────────────────────────
EXPECTED_COLUMNS = [
    "Famille_client", "Client", "Nom", "Adresse1", "Adresse2",
    "CP", "Ville", "Pays", "Secteur", "Localisation", "Magasin",
    "Piece", "Critere", "Reference_CDE", "Representant",
    "Date_Commande", "Gencod", "Reference", "Couleur", "Taille",
    "Designation", "Rayon", "Famille", "Theme", "Modele",
    "Matiere", "Fournisseur", "Saison", "Prix",
    "CDE_qte", "CDE_brut_ht", "CDE_remise_ht", "CDE_net_ht",
    "LIV_qte", "LIV_brut_ht", "LIV_remise_ht", "LIV_net_ht",
    "RELIQUAT_qte", "RELIQUAT_brut_ht", "RELIQUAT_remise_ht", "RELIQUAT_net_ht",
    "ANN_qte", "ANN_brut_ht", "ANN_remise_ht", "ANN_net_ht",
    "STOCK", "CDE_four", "CDE_four_date_liv", "CDE_four_qte"
]


def load_data(filepath=DATA_FILE_PATH, sep=DATA_SEPARATOR, encoding=DATA_ENCODING):
    """
    Load raw data from file.
    Auto-detects separator and encoding if initial attempt fails.
    """
    print(f"[M1] Loading data from {filepath}...")

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Data file not found: {filepath}")

    df = None

    # ── Strategy: try multiple separator + encoding combos ──
    attempts = [
        (sep, encoding),
        (",", "utf-8"),
        (",", "latin-1"),
        (",", "cp1252"),
        (",", "iso-8859-1"),
        ("\t", "utf-8"),
        ("\t", "latin-1"),
        ("\t", "cp1252"),
        (";", "utf-8"),
        (";", "latin-1"),
    ]

    for attempt_sep, attempt_enc in attempts:
        try:
            test_df = pd.read_csv(
                filepath,
                sep=attempt_sep,
                encoding=attempt_enc,
                low_memory=False,
                nrows=5  # quick test with 5 rows
            )
            # Check if we got a reasonable number of columns
            if test_df.shape[1] >= 40:
                # Good — now load the full file
                df = pd.read_csv(
                    filepath,
                    sep=attempt_sep,
                    encoding=attempt_enc,
                    low_memory=False,
                    dtype=str,keep_default_na=False
                )
                print(f"[M1] OK Loaded with sep='{repr(attempt_sep)}' "
                      f"encoding='{attempt_enc}'")
                print(f"[M1] Shape: {df.shape[0]} rows × {df.shape[1]} columns")
                break
            else:
                continue
        except Exception:
            continue

    if df is None:
        raise ValueError(
            f"Could not load {filepath} with any separator/encoding combination. "
            f"Please check the file format."
        )

    # ── Standardize column names ──
    df = _standardize_columns(df)

    return df


def _standardize_columns(df):
    """
    Map raw (possibly garbled) column names to clean standardized names.
    Uses position-based mapping since encoding may corrupt column names.
    """
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    # Explicit aliases observed in the supplied FINAL CSV, whose accented
    # headers were corrupted before export. Never infer meanings by position.
    df = df.rename(columns={
        'Pi鐵e': 'Piece', 'Crit鑽e': 'Critere', 'R馭駻ence_CDE': 'Reference_CDE',
        'Repr駸entant': 'Representant', 'R馭駻ence': 'Reference',
        'D駸ignation': 'Designation', 'Th鑪e': 'Theme', 'Mod鑞e': 'Modele',
        'Mati鑽e': 'Matiere',
    })

    num_cols = len(df.columns)
    num_expected = len(EXPECTED_COLUMNS)

    print(f"[M1] Found {num_cols} columns, expected {num_expected}")

    if False:  # Never infer semantic column names from column position.
        # ── BEST CASE: exact column count match -> rename by position ──
        print(f"[M1] OK Column count matches — renaming by position")
        df.columns = EXPECTED_COLUMNS
        return df

    # ── Try to match columns by recognizable patterns ──
    # Build a mapping from garbled -> clean names
    print(f"[M1] Column count mismatch ({num_cols} vs {num_expected})")
    print(f"[M1] Attempting pattern-based column matching...")

    raw_cols = list(df.columns)
    col_mapping = {}

    # Patterns to match (garbled name pattern -> clean name)
    patterns = {
        r"famille_client": "Famille_client",
        r"^client$": "Client",
        r"^nom$": "Nom",
        r"adresse1": "Adresse1",
        r"adresse2": "Adresse2",
        r"^cp$": "CP",
        r"ville": "Ville",
        r"pays": "Pays",
        r"secteur": "Secteur",
        r"localisation": "Localisation",
        r"magasin": "Magasin",
        r"pi.*ce": "Piece",
        r"crit.*re": "Critere",
        r"r.*f.*rence_cde": "Reference_CDE",
        r"repr.*sentant": "Representant",
        r"date_commande": "Date_Commande",
        r"gencod": "Gencod",
        r"r.*f.*rence$": "Reference",
        r"couleur": "Couleur",
        r"taille": "Taille",
        r"d.*signation": "Designation",
        r"rayon": "Rayon",
        r"^famille$": "Famille",
        r"th.*me": "Theme",
        r"mod.*le": "Modele",
        r"mati.*re": "Matiere",
        r"fournisseur": "Fournisseur",
        r"saison": "Saison",
        r"^prix$": "Prix",
        r"cde_qte": "CDE_qte",
        r"cde_brut_ht": "CDE_brut_ht",
        r"cde_remise_ht": "CDE_remise_ht",
        r"cde_net_ht": "CDE_net_ht",
        r"^liv_qte": "LIV_qte",
        r"liv_brut_ht": "LIV_brut_ht",
        r"liv_remise_ht": "LIV_remise_ht",
        r"liv_net_ht": "LIV_net_ht",
        r"reliquat_qte": "RELIQUAT_qte",
        r"reliquat_brut_ht": "RELIQUAT_brut_ht",
        r"reliquat_remise_ht": "RELIQUAT_remise_ht",
        r"reliquat_net_ht": "RELIQUAT_net_ht",
        r"ann_qte": "ANN_qte",
        r"ann_brut_ht": "ANN_brut_ht",
        r"ann_remise_ht": "ANN_remise_ht",
        r"ann_net_ht": "ANN_net_ht",
        r"^stock$": "STOCK",
        r"cde_four$": "CDE_four",
        r"cde_four_date": "CDE_four_date_liv",
        r"cde_four_qte": "CDE_four_qte",
    }

    for raw_col in raw_cols:
        raw_lower = raw_col.lower().strip()
        for pattern, clean_name in patterns.items():
            if re.search(pattern, raw_lower):
                if clean_name not in col_mapping.values():
                    col_mapping[raw_col] = clean_name
                    break

    # Apply mapping
    if col_mapping:
        df = df.rename(columns=col_mapping)
        matched = len(col_mapping)
        print(f"[M1] Matched {matched}/{num_expected} columns by pattern")

        # Show any unmatched
        unmatched = [c for c in df.columns if c not in EXPECTED_COLUMNS]
        if unmatched:
            print(f"[M1] Unmatched columns (kept as-is): {unmatched[:10]}...")
    else:
        # Last resort: if column count is close, try position mapping
        if False:  # Reject unrecognized headers instead of silently shifting fields.
            print(f"[M1] Pattern matching failed — forcing position-based rename")
            min_cols = min(num_cols, num_expected)
            new_names = EXPECTED_COLUMNS[:min_cols]
            if num_cols > num_expected:
                new_names += [f"EXTRA_COL_{i}" for i in range(num_cols - num_expected)]
            df.columns = new_names[:num_cols]
        else:
            print(f"[M1] WARNING: Could not match columns. Using raw names.")
            print(f"[M1] Raw columns: {list(df.columns[:10])}...")

    # ── Verify critical columns exist ──
    critical_cols = [
        "Date_Commande", "Reference", "Couleur", "Taille",
        "CDE_qte", "LIV_qte", "RELIQUAT_qte", "Prix", "Client"
    ]
    missing_critical = [c for c in critical_cols if c not in df.columns]
    if missing_critical:
        print(f"[M1] WARNING CRITICAL COLUMNS MISSING: {missing_critical}")
        print(f"[M1] Available columns: {list(df.columns)}")
        raise KeyError(
            f"Critical columns not found after mapping: {missing_critical}. "
            f"Check your file format and separator."
        )

    print(f"[M1] OK All critical columns verified")
    return df


def parse_order_dates(values):
    text=values.astype(str).str.strip()
    iso=text.str.match(r'^\d{4}-\d{2}-\d{2}(?:$|[ T])')
    result=pd.to_datetime(values,errors='coerce',format='mixed',dayfirst=True)
    result.loc[iso]=pd.to_datetime(values.loc[iso],errors='coerce',format='ISO8601')
    return result

def parse_and_prepare(df):
    """
    Core preparation:
    - Parse dates
    - Extract season type from Critere
    - Compute true demand
    - Clean types
    """
    print("[M1] Parsing and preparing data...")

    # ── 1. Parse Date_Commande ──
    df["Date_Commande"] = parse_order_dates(df['Date_Commande'])
    date_null_count = df["Date_Commande"].isna().sum()
    if date_null_count > 0:
        raise ValueError(f'{date_null_count} legacy rows have missing or invalid dates. Import a corrected file; existing published results are preserved. Joolan imports retain invalid lines in quarantine.')

    # ── 2. Create year_month column ──
    df["year_month"] = df["Date_Commande"].dt.to_period("M")

    # ── 3. Extract season info from Critere (for display/filtering) ──
    if "Critere" in df.columns:
        df["season_type"] = df["Critere"].apply(_extract_season_type)
        df["season_year"] = df["Critere"].apply(_extract_season_year)
        df["product_status"] = df["Critere"].apply(_extract_product_status)
    else:
        df["season_type"] = "UNKNOWN"
        df["season_year"] = None
        df["product_status"] = "UNKNOWN"

    # ── 4. Clean numeric columns ──
    qty_cols = ["CDE_qte", "LIV_qte", "RELIQUAT_qte", "ANN_qte",
                "STOCK", "CDE_four_qte"]
    for col in qty_cols:
        if col in df.columns:
            supplied=df[col].notna() & df[col].astype(str).str.strip().ne('')
            parsed=pd.to_numeric(df[col],errors='coerce')
            invalid=supplied & (parsed.isna() | ~np.isfinite(parsed) | ((parsed<0) if col!='STOCK' else False))
            if invalid.any():raise ValueError(f'{int(invalid.sum())} invalid or negative values in {col}. Existing results are preserved.')
            values = pd.to_numeric(df[col], errors="coerce").fillna(0)
            df[col] = pd.to_numeric(df[col], errors="coerce") if col in ("STOCK","CDE_four_qte") else values.astype(float)

    money_cols = ["CDE_brut_ht", "CDE_remise_ht", "CDE_net_ht",
                  "LIV_brut_ht", "LIV_remise_ht", "LIV_net_ht",
                  "RELIQUAT_brut_ht", "RELIQUAT_remise_ht", "RELIQUAT_net_ht",
                  "ANN_brut_ht", "ANN_remise_ht", "ANN_net_ht", "Prix", "Selling_Price", "Purchase_Cost"]
    for col in money_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce") if col in ("Prix","Selling_Price","Purchase_Cost") else pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # ── 5. Clean string columns ──
    str_cols = ["Client", "Reference", "Couleur", "Taille", "Rayon",
                "Famille", "Theme", "Modele", "Matiere", "Fournisseur",
                "Famille_client", "Nom", "Pays", "Secteur", "Representant"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(
                {"nan": "UNKNOWN", "": "UNKNOWN", "None": "UNKNOWN",
                 "NaN": "UNKNOWN", "none": "UNKNOWN"}
            )

    # ── 6. Clean Client ID (remove leading dots/spaces) ──
    if "Client" in df.columns:
        df["Client"] = df["Client"].str.lstrip(". ")

    # ── 7. Clean Taille (strip spaces) ──
    if "Taille" in df.columns:
        df["Taille"] = df["Taille"].str.strip()

    # ── 8. Compute TRUE DEMAND ──
    df["true_demand"] = df["LIV_qte"] + df["RELIQUAT_qte"]
    if "Data_Source" in df.columns:
        joolan = df["Data_Source"].eq("joolan")
        df.loc[joolan, "true_demand"] = (df.loc[joolan, "CDE_qte"]-df.loc[joolan,"ANN_qte"]).clip(lower=0)

    # ── 9. Print summary ──
    print(f"[M1] OK Preparation complete. Shape: {df.shape}")
    print(f"[M1] Date range: {df['Date_Commande'].min().date()} "
          f"to {df['Date_Commande'].max().date()}")
    print(f"[M1] Unique Références: {df['Reference'].nunique()}")
    print(f"[M1] Unique Couleurs: {df['Couleur'].nunique()}")
    print(f"[M1] Unique Tailles: {df['Taille'].nunique()}")
    print(f"[M1] Unique Clients: {df['Client'].nunique()}")
    print(f"[M1] Season types found: {sorted(df['season_type'].unique())}")
    print(f"[M1] Total true demand: {df['true_demand'].sum():,.0f} units")

    # Quick data quality check
    zero_demand = (df["true_demand"] == 0).sum()
    print(f"[M1] Rows with zero true demand: {zero_demand} "
          f"({zero_demand/len(df)*100:.1f}%)")

    return df


def _extract_season_type(critere_val):
    """Extract season type from Critère column."""
    if pd.isna(critere_val) or str(critere_val).strip() == "":
        return "UNKNOWN"

    val = str(critere_val).strip().upper()

    if "HIVER" in val:
        return "HIVER"
    elif "PRINTEMPS" in val:
        return "PRINTEMPS"
    elif "CORE" in val:
        return "CORE"
    elif "RECONDUIT" in val:
        return "RECONDUIT"
    else:
        return "OTHER"


def _extract_season_year(critere_val):
    """Extract year from Critère column. E.g., 'Hiver(2022)' -> 2022"""
    if pd.isna(critere_val):
        return None

    match = re.search(r'\((\d{4})\)', str(critere_val))
    if match:
        return int(match.group(1))
    return None


def _extract_product_status(critere_val):
    """Classify product status from Critère."""
    if pd.isna(critere_val):
        return "UNKNOWN"

    val = str(critere_val).strip().upper()

    if "CORE" in val:
        return "CORE"
    elif "RECONDUIT" in val:
        return "CARRY-OVER"
    else:
        return "SEASONAL"


def aggregate_monthly_sku_color(df):
    """
    Aggregate transaction-level data to monthly level.
    Granularity: Reference × Couleur × year_month
    This is the level at which SARIMA will forecast.
    """
    print("[M1] Aggregating to monthly SKU-Color level...")

    agg_dict = {
        "true_demand": "sum",
        "CDE_qte": "sum",
        "LIV_qte": "sum",
        "RELIQUAT_qte": "sum",
        "ANN_qte": "sum",
        "Prix": "mean",
        "Client": "nunique",
    }

    # Only include columns that exist
    agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}

    # Add Reference_CDE if it exists
    if "Reference_CDE" in df.columns:
        agg_dict["Reference_CDE"] = "nunique"

    monthly_sku_color = (
        df.groupby(["Reference", "Couleur", "year_month"])
        .agg(agg_dict)
        .reset_index()
    )

    # Rename count columns
    rename_map = {}
    if "Client" in monthly_sku_color.columns and "Client" in agg_dict:
        rename_map["Client"] = "num_clients"
    if "Reference_CDE" in monthly_sku_color.columns:
        rename_map["Reference_CDE"] = "num_orders"
    monthly_sku_color = monthly_sku_color.rename(columns=rename_map)

    # Add product metadata (take first occurrence for each ref-color)
    meta_cols = ["Reference", "Couleur", "Designation", "Rayon", "Famille",
                 "Theme", "Modele", "Matiere", "Fournisseur", "product_status"]
    available_meta = [c for c in meta_cols if c in df.columns]
    if len(available_meta) > 2:  # at least Reference + Couleur + something
        meta = df.drop_duplicates(subset=["Reference", "Couleur"])[available_meta]
        monthly_sku_color = monthly_sku_color.merge(
            meta, on=["Reference", "Couleur"], how="left"
        )

    n_combos = monthly_sku_color.groupby(["Reference", "Couleur"]).ngroups
    print(f"[M1] Monthly SKU-Color aggregation: {monthly_sku_color.shape[0]} rows")
    print(f"[M1] Unique SKU-Color combos: {n_combos}")

    return monthly_sku_color


def aggregate_monthly_sku_color_size(df):
    """
    Aggregate to monthly level at size detail.
    Granularity: Reference × Couleur × Taille × year_month
    This is the level at which CatBoost will forecast.
    """
    print("[M1] Aggregating to monthly SKU-Color-Size level...")

    agg_dict = {
        "true_demand": "sum",
        "CDE_qte": "sum",
        "LIV_qte": "sum",
        "RELIQUAT_qte": "sum",
        "ANN_qte": "sum",
        "Prix": "mean",
        "Client": "nunique",
    }
    agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}

    monthly_sku_color_size = (
        df.groupby(["Reference", "Couleur", "Taille", "year_month"])
        .agg(agg_dict)
        .reset_index()
    )

    rename_map = {}
    if "Client" in agg_dict:
        rename_map["Client"] = "num_clients"
    monthly_sku_color_size = monthly_sku_color_size.rename(columns=rename_map)

    # Add product metadata
    meta_cols = ["Reference", "Couleur", "Taille", "Designation", "Rayon",
                 "Famille", "Theme", "Modele", "Matiere", "Fournisseur",
                 "product_status"]
    available_meta = [c for c in meta_cols if c in df.columns]
    if len(available_meta) > 3:
        meta = df.drop_duplicates(
            subset=["Reference", "Couleur", "Taille"]
        )[available_meta]
        monthly_sku_color_size = monthly_sku_color_size.merge(
            meta, on=["Reference", "Couleur", "Taille"], how="left"
        )

    n_combos = monthly_sku_color_size.groupby(
        ["Reference", "Couleur", "Taille"]
    ).ngroups
    print(f"[M1] Monthly SKU-Color-Size aggregation: "
          f"{monthly_sku_color_size.shape[0]} rows")
    print(f"[M1] Unique SKU-Color-Size combos: {n_combos}")

    return monthly_sku_color_size


def build_client_table(df):
    """Build client-level summary table and stock info."""
    print("[M1] Building client-level table...")

    # Get latest stock info per Reference-Couleur-Taille
    stock_cols = ["Reference", "Couleur", "Taille"]
    if "STOCK" in df.columns:
        stock_cols.append("STOCK")
    if "CDE_four_qte" in df.columns:
        stock_cols.append("CDE_four_qte")

    stock_info = (
        df.sort_values("Date_Commande")
        .drop_duplicates(subset=["Reference", "Couleur", "Taille"], keep="last")
        [stock_cols]
    )

    # Ensure STOCK and CDE_four_qte columns exist
    if "STOCK" not in stock_info.columns:
        stock_info["STOCK"] = 0
    if "CDE_four_qte" not in stock_info.columns:
        stock_info["CDE_four_qte"] = 0

    # Client summary
    client_agg = {
        "true_demand": "sum",
        "Reference": "nunique",
        "Date_Commande": ["min", "max", "count"],
        "year_month": "nunique",
        "Prix": "mean",
    }
    if "CDE_net_ht" in df.columns:
        client_agg["CDE_net_ht"] = "sum"
    if "Famille" in df.columns:
        client_agg["Famille"] = "nunique"

    client_summary = (
        df.groupby("Client")
        .agg(client_agg)
        .reset_index()
    )

    # Flatten multi-level columns
    flat_cols = []
    for col in client_summary.columns:
        if isinstance(col, tuple):
            flat_cols.append("_".join([str(c) for c in col if c != ""]).strip("_"))
        else:
            flat_cols.append(str(col))
    client_summary.columns = flat_cols

    # Get client metadata
    client_meta_cols = ["Client", "Nom", "Famille_client", "CP", "Ville",
                        "Pays", "Secteur", "Localisation"]
    available_meta = [c for c in client_meta_cols if c in df.columns]
    if len(available_meta) > 1:
        client_meta = df.drop_duplicates(subset=["Client"])[available_meta]
        client_summary = client_summary.merge(client_meta, on="Client", how="left")

    print(f"[M1] Client table: {client_summary.shape[0]} clients")
    print(f"[M1] Stock info: {stock_info.shape[0]} SKU-Color-Size entries")

    return client_summary, stock_info


def get_critere_display_map(df):
    """Build mapping of Reference -> Critère for display purposes."""
    if "Critere" not in df.columns:
        return pd.DataFrame(columns=[
            "Reference", "Critere", "season_type", "season_year", "product_status"
        ])

    critere_map = (
        df.sort_values("Date_Commande")
        .drop_duplicates(subset=["Reference"], keep="last")
        [["Reference", "Critere", "season_type", "season_year", "product_status"]]
    )
    return critere_map


def run_module1(filepath=DATA_FILE_PATH):
    """Execute all Module 1 steps and return prepared data."""
    print("=" * 60)
    print("MODULE 1: DATA LOADING & PREPARATION")
    print("=" * 60)

    # Step 1: Load
    df_raw = load_data(filepath)

    # Step 2: Parse and prepare
    df = parse_and_prepare(df_raw)

    # Step 3: Aggregate to monthly SKU-Color (for SARIMA)
    monthly_sku_color = aggregate_monthly_sku_color(df)

    # Step 4: Aggregate to monthly SKU-Color-Size (for CatBoost)
    monthly_sku_color_size = aggregate_monthly_sku_color_size(df)

    # Step 5: Build client table
    client_summary, stock_info = build_client_table(df)

    # Step 6: Critère display map
    critere_map = get_critere_display_map(df)

    # Package results
    data = {
        "raw": df,
        "monthly_sku_color": monthly_sku_color,
        "monthly_sku_color_size": monthly_sku_color_size,
        "client_summary": client_summary,
        "stock_info": stock_info,
        "critere_map": critere_map,
    }

    print(f"\n[M1] OK Module 1 complete")
    return data


if __name__ == "__main__":
    data = run_module1()
    print("\n--- Quick Data Check ---")
    print(f"Raw shape: {data['raw'].shape}")
    print(f"Columns: {list(data['raw'].columns[:10])}...")
    print(f"\nFirst 3 rows of monthly_sku_color:")
    print(data['monthly_sku_color'].head(3))
