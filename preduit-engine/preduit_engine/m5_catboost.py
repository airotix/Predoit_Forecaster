"""
============================================================
MODULE 5: CATBOOST FORECASTING (MEMORY OPTIMIZED)
- NO complete monthly grid — uses only actual data points
- Filters to CatBoost products BEFORE building features
- Processes in manageable chunks
- Memory-efficient lag computation
============================================================
"""

import pandas as pd
import numpy as np
import warnings
import gc
from .config import *

warnings.filterwarnings("ignore")

try:
    from catboost import CatBoostRegressor, Pool
    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False
    print("[M5] WARNING: catboost not installed. Run: pip install catboost")

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False


def determine_size_order(sizes):
    """Determine natural ordering of sizes."""
    alpha_order = {s: i for i, s in enumerate(SIZE_ORDER_ALPHA)}
    sizes_clean = [str(s).strip().upper() for s in sizes if pd.notna(s)]

    if all(s in alpha_order for s in sizes_clean):
        return sorted(sizes_clean, key=lambda s: alpha_order[s])
    try:
        return sorted(sizes_clean, key=lambda s: float(s))
    except (ValueError, TypeError):
        pass

    known = [s for s in sizes_clean if s in alpha_order]
    unknown = [s for s in sizes_clean if s not in alpha_order]
    return sorted(known, key=lambda s: alpha_order[s]) + sorted(unknown)


def build_catboost_features(monthly_sku_color_size, monthly_sku_color,
                            df_raw, kpis, profiles, fallback_list=None):
    """
    Build feature matrix for CatBoost — MEMORY OPTIMIZED.

    Key difference from original:
    - Filters to only CatBoost-eligible products FIRST
    - NO complete grid creation — uses only actual data rows
    - Computes lags directly on sorted actual data
    """
    print("[M5] Building CatBoost feature matrix (memory-optimized)...")

    # ── 1. FILTER TO CATBOOST PRODUCTS ONLY ──
    catboost_products = profiles[
        profiles["model_assignment"].isin(["CATBOOST", "CATBOOST_ANALOGY"])
    ][["Reference", "Couleur"]].copy()

    # Add SARIMA fallbacks
    if fallback_list:
        fallback_df = pd.DataFrame(fallback_list, columns=["Reference", "Couleur"])
        catboost_products = pd.concat(
            [catboost_products, fallback_df], ignore_index=True
        ).drop_duplicates()

    if catboost_products.empty:
        print("[M5] No products assigned to CatBoost")
        return pd.DataFrame()

    print(f"[M5] CatBoost products: {catboost_products.shape[0]} SKU-Colors")

    # Create a key for fast filtering
    catboost_keys = set(
        catboost_products["Reference"] + "|||" + catboost_products["Couleur"]
    )

    # Filter the size-level data to CatBoost products only
    df = monthly_sku_color_size.copy()
    df["_key"] = df["Reference"] + "|||" + df["Couleur"]
    df = df[df["_key"].isin(catboost_keys)].copy()
    df = df.drop(columns=["_key"])

    if df.empty:
        print("[M5] No data for CatBoost products after filtering")
        return pd.DataFrame()

    print(f"[M5] Filtered data: {df.shape[0]} rows "
          f"(from {monthly_sku_color_size.shape[0]} total)")

    # ── 2. SORT FOR LAG COMPUTATION ──
    df = df.sort_values(["Reference", "Couleur", "Taille", "year_month"])
    df["group_key"] = df["Reference"] + "_" + df["Couleur"] + "_" + df["Taille"]

    # Temporal features from year_month
    df["ym_timestamp"] = df["year_month"].dt.to_timestamp()
    df["year"] = df["ym_timestamp"].dt.year
    df["month"] = df["ym_timestamp"].dt.month

    # ── 3. LAG FEATURES (computed on actual data, no grid filling) ──
    print("[M5]   Computing lag features...")

    grp = df.groupby("group_key")["true_demand"]

    df["demand_lag_1"] = grp.shift(1)
    df["demand_lag_2"] = grp.shift(2)
    df["demand_lag_3"] = grp.shift(3)

    # Rolling features on actual data
    df["demand_rolling_mean_3"] = grp.transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).mean()
    )
    df["demand_rolling_sum_3"] = grp.transform(
        lambda x: x.shift(1).rolling(3, min_periods=1).sum()
    )
    df["demand_rolling_std_3"] = grp.transform(
        lambda x: x.shift(1).rolling(3, min_periods=2).std()
    )

    # Cumulative demand
    df["cumulative_demand"] = grp.cumsum().shift(1)

    # Count of non-zero months so far
    df["nonzero_months_so_far"] = grp.transform(
        lambda x: (x > 0).cumsum().shift(1)
    )

    # ── 4. PRODUCT FEATURES ──
    print("[M5]   Computing product features...")

    # Product age (months since first appearance in data)
    first_seen = (
        df.groupby("Reference")["ym_timestamp"].min()
        .reset_index()
        .rename(columns={"ym_timestamp": "first_seen"})
    )
    df = df.merge(first_seen, on="Reference", how="left")
    df["product_age_months"] = (
        (df["ym_timestamp"] - df["first_seen"]).dt.days / 30.44
    ).clip(lower=0).astype(int)
    df = df.drop(columns=["first_seen"])

    # ── 5. DIFFUSION FEATURES (per SKU-Color) ──
    print("[M5]   Computing diffusion features...")

    if "sku_kpis" in kpis:
        diffusion_cols = ["Reference", "Couleur"]
        for col in ["diffusion_rate", "depth_per_client", "reorder_rate",
                     "fill_rate", "backorder_rate"]:
            if col in kpis["sku_kpis"].columns:
                diffusion_cols.append(col)

        df = df.merge(
            kpis["sku_kpis"][diffusion_cols],
            on=["Reference", "Couleur"],
            how="left"
        )

    # Number of clients (lagged) — from existing num_clients column
    if "num_clients" in df.columns:
        df["clients_lag_1"] = df.groupby(
            ["Reference", "Couleur"]
        )["num_clients"].shift(1)
    else:
        df["clients_lag_1"] = 0

    # ── 6. CATEGORY CONTEXT ──
    print("[M5]   Computing category context features...")

    if "Famille" in df.columns and "cat_kpis_monthly" in kpis:
        cat_monthly = kpis["cat_kpis_monthly"][
            ["Famille", "year_month", "cat_monthly_demand"]
        ].rename(columns={"cat_monthly_demand": "category_demand"})

        df = df.merge(cat_monthly, on=["Famille", "year_month"], how="left")
        df["category_demand"] = df["category_demand"].fillna(0)
    else:
        df["category_demand"] = 0

    # ── 7. TEMPORAL FEATURES ──
    df["quarter"] = df["ym_timestamp"].dt.quarter
    df["is_hiver_campaign"] = df["month"].isin([1, 2, 3, 4]).astype(int)
    df["is_printemps_campaign"] = df["month"].isin([7, 8, 9, 10]).astype(int)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    min_ym = df["ym_timestamp"].min()
    df["month_index"] = ((df["ym_timestamp"] - min_ym).dt.days / 30.44).astype(int)

    # ── 8. SIZE POSITION FEATURES ──
    print("[M5]   Computing size position features...")

    # Compute size rank per Reference
    size_rank_data = []
    for ref, grp_df in df.groupby("Reference"):
        sizes = grp_df["Taille"].unique()
        ordered = determine_size_order(sizes)
        rank_map = {s: i + 1 for i, s in enumerate(ordered)}
        count = len(ordered)
        for taille in sizes:
            rank = rank_map.get(str(taille).strip().upper(), count // 2)
            size_rank_data.append({
                "Reference": ref,
                "Taille": taille,
                "size_rank": rank,
                "size_count": count,
                "size_is_extreme": int(rank == 1 or rank == count),
                "size_relative_pos": rank / max(count, 1),
            })

    size_rank_df = pd.DataFrame(size_rank_data).drop_duplicates(
        subset=["Reference", "Taille"]
    )
    df = df.merge(size_rank_df, on=["Reference", "Taille"], how="left")

    # Historical size share from KPIs
    if "size_kpis" in kpis:
        size_share = kpis["size_kpis"][
            ["Reference", "Couleur", "Taille", "size_share"]
        ].copy()
        df = df.merge(
            size_share, on=["Reference", "Couleur", "Taille"], how="left"
        )
        df["size_share"] = df["size_share"].fillna(0)
    else:
        df["size_share"] = 0

    # ── 9. FILL NAs ──
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)

    # Fill string columns
    str_fill_cols = ["Rayon", "Famille", "Theme", "Modele", "Matiere",
                     "Fournisseur", "Designation", "product_status"]
    for col in str_fill_cols:
        if col in df.columns:
            df[col] = df[col].fillna("UNKNOWN").astype(str)

    # ── 10. CLEAN UP temp columns ──
    drop_cols = ["ym_timestamp", "group_key"]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")

    gc.collect()

    print(f"[M5] ✓ Feature matrix: {df.shape[0]} rows × {df.shape[1]} columns")
    print(f"[M5]   Memory usage: {df.memory_usage(deep=True).sum() / 1e6:.1f} MB")

    return df


def prepare_train_test(df_features, profiles, fallback_list=None):
    """
    Prepare training and prediction data.
    Memory-efficient: no unnecessary copies.
    """
    if df_features.empty:
        print("[M5] No data for CatBoost. Skipping.")
        return None

    print("[M5] Preparing train/test splits...")

    df = df_features

    # ── Define feature columns ──
    categorical_features = []
    for col in ["Rayon", "Famille", "Theme", "Modele", "Matiere",
                "Fournisseur", "Couleur", "Taille", "product_status"]:
        if col in df.columns:
            categorical_features.append(col)

    numeric_features = []
    candidate_numeric = [
        "Prix", "product_age_months",
        "demand_lag_1", "demand_lag_2", "demand_lag_3",
        "demand_rolling_mean_3", "demand_rolling_sum_3", "demand_rolling_std_3",
        "cumulative_demand", "nonzero_months_so_far",
        "clients_lag_1",
        "diffusion_rate", "depth_per_client", "reorder_rate",
        "fill_rate", "backorder_rate",
        "category_demand",
        "year", "month", "quarter",
        "is_hiver_campaign", "is_printemps_campaign",
        "month_sin", "month_cos", "month_index",
        "size_rank", "size_count", "size_is_extreme",
        "size_relative_pos", "size_share",
    ]
    for col in candidate_numeric:
        if col in df.columns:
            numeric_features.append(col)

    feature_columns = numeric_features + categorical_features
    target_column = "true_demand"

    # ── Time-based split ──
    all_months_sorted = sorted(df["year_month"].unique())

    if len(all_months_sorted) < 4:
        print("[M5] Not enough temporal data for train/test split")
        return None

    # Last 3 months for validation
    val_months = set(all_months_sorted[-3:])
    train_months = set(all_months_sorted[:-3])

    # Drop rows without lag data (first observation per group)
    df_valid = df[df["demand_lag_1"].notna()].copy()

    if df_valid.empty:
        print("[M5] No valid rows after lag filtering")
        return None

    train_mask = df_valid["year_month"].isin(train_months)
    val_mask = df_valid["year_month"].isin(val_months)

    # Ensure categorical columns are strings
    for col in categorical_features:
        df_valid[col] = df_valid[col].astype(str)

    X_train = df_valid.loc[train_mask, feature_columns]
    y_train = df_valid.loc[train_mask, target_column]
    X_val = df_valid.loc[val_mask, feature_columns]
    y_val = df_valid.loc[val_mask, target_column]

    # Store identifiers for validation tracking
    val_ids = df_valid.loc[
        val_mask, ["Reference", "Couleur", "Taille", "year_month"]
    ]

    print(f"[M5] Training: {X_train.shape[0]} rows")
    print(f"[M5] Validation: {X_val.shape[0]} rows")
    print(f"[M5] Features: {len(feature_columns)} "
          f"({len(numeric_features)} numeric + "
          f"{len(categorical_features)} categorical)")

    split_data = {
        "X_train": X_train,
        "y_train": y_train,
        "X_val": X_val,
        "y_val": y_val,
        "val_ids": val_ids,
        "feature_columns": feature_columns,
        "categorical_features": categorical_features,
        "numeric_features": numeric_features,
        "target_column": target_column,
        "df_valid": df_valid,
        "all_months_sorted": all_months_sorted,
    }

    return split_data


def train_catboost_models(split_data):
    """Train 3 quantile CatBoost models."""
    if split_data is None or not CATBOOST_AVAILABLE:
        print("[M5] Cannot train CatBoost. Skipping.")
        return None, None

    print("[M5] Training CatBoost models...")

    X_train = split_data["X_train"]
    y_train = split_data["y_train"]
    X_val = split_data["X_val"]
    y_val = split_data["y_val"]
    cat_features = split_data["categorical_features"]
    feature_columns = split_data["feature_columns"]

    cat_indices = [feature_columns.index(c) for c in cat_features]

    models = {}
    quantiles = {
        "conservative": QUANTILE_CONSERVATIVE,
        "base": QUANTILE_BASE,
        "optimistic": QUANTILE_OPTIMISTIC,
    }

    for scenario, quantile in quantiles.items():
        print(f"[M5]   Training {scenario} model (quantile={quantile})...")

        model = CatBoostRegressor(
            iterations=CATBOOST_ITERATIONS,
            depth=CATBOOST_DEPTH,
            learning_rate=CATBOOST_LEARNING_RATE,
            l2_leaf_reg=CATBOOST_L2_REG,
            loss_function=f"Quantile:alpha={quantile}",
            cat_features=cat_indices,
            verbose=0,
            random_seed=42,
            early_stopping_rounds=CATBOOST_EARLY_STOPPING,
        )

        train_pool = Pool(X_train, y_train, cat_features=cat_indices)
        val_pool = Pool(X_val, y_val, cat_features=cat_indices)

        model.fit(train_pool, eval_set=val_pool, verbose=0)

        # Validation metrics
        val_pred = np.maximum(np.round(model.predict(X_val)), 0)
        non_zero = y_val > 0
        if non_zero.sum() > 0:
            mape = np.mean(
                np.abs(y_val[non_zero] - val_pred[non_zero]) / y_val[non_zero]
            ) * 100
        else:
            mape = None
        mae = np.mean(np.abs(y_val - val_pred))

        models[scenario] = {
            "model": model,
            "val_mape": mape,
            "val_mae": mae,
            "best_iteration": model.get_best_iteration(),
        }

        mape_str = f"{mape:.1f}%" if mape is not None else "N/A"
        print(f"[M5]     MAE={mae:.2f}, MAPE={mape_str}")

    # Feature importance
    base_model = models["base"]["model"]
    feature_importance = pd.DataFrame({
        "feature": feature_columns,
        "importance": base_model.get_feature_importance(),
    }).sort_values("importance", ascending=False)

    print(f"\n[M5] Top 10 features:")
    for _, row in feature_importance.head(10).iterrows():
        print(f"      {row['feature']}: {row['importance']:.1f}")

    return models, feature_importance


def generate_catboost_forecasts(models, split_data):
    """Generate forecasts for the next N months."""
    if models is None or split_data is None:
        return pd.DataFrame()

    print("[M5] Generating CatBoost forecasts...")

    df = split_data["df_valid"]
    feature_columns = split_data["feature_columns"]
    cat_features = split_data["categorical_features"]

    # Get last known features for each product
    last_features = (
        df.sort_values("year_month")
        .groupby(["Reference", "Couleur", "Taille"])
        .last()
        .reset_index()
    )

    print(f"[M5] Generating forecasts for {last_features.shape[0]} "
          f"SKU-Color-Size combos × {FORECAST_HORIZON_MONTHS} months")

    # Build forecast month range
    last_month_global = df["year_month"].max()
    forecast_periods = pd.period_range(
        start=last_month_global + 1,
        periods=FORECAST_HORIZON_MONTHS,
        freq="M"
    )

    # Build forecast feature matrix in batch (not row by row)
    forecast_rows = []
    meta_rows = []

    for _, row in last_features.iterrows():
        for i, fm in enumerate(forecast_periods):
            fm_ts = fm.to_timestamp()

            feat = {}
            # Copy all features from last known
            for col in feature_columns:
                if col in row.index:
                    feat[col] = row[col]
                else:
                    feat[col] = 0

            # Update temporal features
            feat["year"] = fm_ts.year
            feat["month"] = fm_ts.month
            feat["quarter"] = (fm_ts.month - 1) // 3 + 1
            feat["is_hiver_campaign"] = int(fm_ts.month in [1, 2, 3, 4])
            feat["is_printemps_campaign"] = int(fm_ts.month in [7, 8, 9, 10])
            feat["month_sin"] = np.sin(2 * np.pi * fm_ts.month / 12)
            feat["month_cos"] = np.cos(2 * np.pi * fm_ts.month / 12)

            if "month_index" in feat:
                feat["month_index"] = int(feat["month_index"]) + i + 1
            if "product_age_months" in feat:
                feat["product_age_months"] = int(feat["product_age_months"]) + i + 1

            forecast_rows.append(feat)
            meta_rows.append({
                "Reference": row["Reference"],
                "Couleur": row["Couleur"],
                "Taille": row["Taille"],
                "forecast_month": fm,
            })

    if not forecast_rows:
        return pd.DataFrame()

    X_forecast = pd.DataFrame(forecast_rows)[feature_columns]

    # Ensure categorical types
    for col in cat_features:
        if col in X_forecast.columns:
            X_forecast[col] = X_forecast[col].astype(str)

    # Predict with all 3 models
    meta_df = pd.DataFrame(meta_rows)

    for scenario, model_data in models.items():
        preds = model_data["model"].predict(X_forecast)
        preds = np.maximum(np.round(preds), 0).astype(int)
        meta_df[f"forecast_{scenario}"] = preds

    meta_df["model_type"] = "CATBOOST"

    print(f"[M5] ✓ CatBoost forecasts: {meta_df.shape[0]} rows")

    # Clean up
    del X_forecast, forecast_rows
    gc.collect()

    return meta_df


def run_module5(monthly_sku_color_size, monthly_sku_color, df_raw,
                kpis, profiles, sarima_output):
    """Execute Module 5."""
    print("\n" + "=" * 60)
    print("MODULE 5: CATBOOST FORECASTING")
    print("=" * 60)

    fallback_list = sarima_output.get("fallback_to_catboost", [])
    print(f"[M5] SARIMA fallbacks to absorb: {len(fallback_list)}")

    # Build features (filtered + memory-optimized)
    df_features = build_catboost_features(
        monthly_sku_color_size, monthly_sku_color,
        df_raw, kpis, profiles, fallback_list
    )

    if df_features.empty:
        print("[M5] No CatBoost products to process")
        output = {
            "catboost_models": None,
            "feature_importance": None,
            "catboost_forecasts": pd.DataFrame(),
            "shap_explanations": None,
            "df_features": df_features,
        }
        print(f"\n[M5] ✓ Module 5 complete (no CatBoost products)")
        return output

    # Prepare splits
    split_data = prepare_train_test(df_features, profiles, fallback_list)

    # Train
    if split_data is not None:
        models, feature_importance = train_catboost_models(split_data)
    else:
        models, feature_importance = None, None

    # Forecast
    catboost_forecasts = generate_catboost_forecasts(models, split_data)

    output = {
        "catboost_models": models,
        "feature_importance": feature_importance,
        "catboost_forecasts": catboost_forecasts,
        "shap_explanations": None,  # skip SHAP for now (memory)
        "df_features": pd.DataFrame(),  # don't store 15M rows
    }

    # Force garbage collection
    del df_features
    gc.collect()

    print(f"\n[M5] ✓ Module 5 complete")
    return output