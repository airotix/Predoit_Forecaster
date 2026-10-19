"""
============================================================
MODULE 6: SIZE CURVE ENGINE
- Compute historical size distribution per SKU-Color
- Correct for stock-out distortions
- Apply to SARIMA forecasts (disaggregate to size level)
- Validate CatBoost size-level forecasts
- Apply business rules
============================================================
"""

import pandas as pd
import numpy as np
from .config import *


def determine_size_order(sizes):
    """Determine natural ordering of sizes."""
    alpha_order = {s: i for i, s in enumerate(SIZE_ORDER_ALPHA)}
    sizes_clean = [str(s).strip().upper() for s in sizes if pd.notna(s)]

    # Try alpha ordering
    if all(s in alpha_order for s in sizes_clean):
        return sorted(sizes_clean, key=lambda s: alpha_order[s])

    # Try numeric
    try:
        return sorted(sizes_clean, key=lambda s: float(s))
    except (ValueError, TypeError):
        pass

    # Mixed: known alpha first, then unknown sorted
    known = [s for s in sizes_clean if s in alpha_order]
    unknown = [s for s in sizes_clean if s not in alpha_order]
    return sorted(known, key=lambda s: alpha_order[s]) + sorted(unknown)


def compute_product_size_curves(df_raw, size_kpis):
    """
    Compute size distribution curves per Reference × Couleur.

    Level 1: Product-specific curve (if enough data)
    Level 2: Category fallback (Famille level)
    """
    print("[M6] Computing size curves...")

    curves = {}

    # ── Level 1: Product-specific curves ──
    for (ref, color), group in size_kpis.groupby(["Reference", "Couleur"]):
        total_demand = group["size_total_demand"].sum()

        if total_demand >= MIN_UNITS_FOR_PRODUCT_SIZE_CURVE:
            # Sufficient data for product-specific curve
            curve = group[["Taille", "size_share"]].copy()
            curve["curve_source"] = "PRODUCT_SPECIFIC"
        else:
            # Use category fallback (will be overwritten below)
            curve = group[["Taille", "size_share"]].copy()
            curve["curve_source"] = "PRODUCT_SPARSE"

        curves[(ref, color)] = curve

    # ── Level 2: Category (Famille) fallback curves ──
    # Get Famille for each Reference
    ref_famille = (
        df_raw.drop_duplicates(subset=["Reference"])[["Reference", "Famille"]]
    )

    # Compute category-level size distribution
    cat_size_dist = (
        df_raw.groupby(["Famille", "Taille"])
        .agg({"true_demand": "sum"})
        .reset_index()
    )
    cat_totals = (
        cat_size_dist.groupby("Famille")["true_demand"]
        .sum()
        .reset_index()
        .rename(columns={"true_demand": "famille_total"})
    )
    cat_size_dist = cat_size_dist.merge(cat_totals, on="Famille")
    cat_size_dist["cat_size_share"] = (
        cat_size_dist["true_demand"] / cat_size_dist["famille_total"]
    )

    # Apply category fallback where product data is sparse
    for (ref, color), curve_df in curves.items():
        if curve_df["curve_source"].iloc[0] == "PRODUCT_SPARSE":
            # Get this product's famille
            ref_fam = ref_famille[ref_famille["Reference"] == ref]
            if not ref_fam.empty:
                famille = ref_fam["Famille"].iloc[0]
                cat_curve = cat_size_dist[cat_size_dist["Famille"] == famille]

                if not cat_curve.empty:
                    # Merge category curve onto product's sizes
                    product_sizes = curve_df["Taille"].unique()
                    new_curve = []
                    for taille in product_sizes:
                        cat_match = cat_curve[cat_curve["Taille"] == taille]
                        share = cat_match["cat_size_share"].iloc[0] if not cat_match.empty else 0
                        new_curve.append({
                            "Taille": taille,
                            "size_share": share,
                            "curve_source": "CATEGORY_FALLBACK",
                        })
                    new_curve_df = pd.DataFrame(new_curve)
                    # Re-normalize
                    total_share = new_curve_df["size_share"].sum()
                    if total_share > 0:
                        new_curve_df["size_share"] = (
                            new_curve_df["size_share"] / total_share
                        )
                    curves[(ref, color)] = new_curve_df

    print(f"[M6] Size curves computed for {len(curves)} Reference-Couleur combos")

    return curves, cat_size_dist


def correct_stockout_distortions(curves, size_kpis, cat_size_dist, df_raw):
    """
    Correct size curves where stock-outs have distorted the distribution.

    If a size had high backorder rate, its true demand was higher than recorded.
    Use category curve to impute what the share should have been.
    """
    print("[M6] Correcting stock-out distortions...")

    corrections_made = 0

    ref_famille = (
        df_raw.drop_duplicates(subset=["Reference"])[["Reference", "Famille"]]
    )

    for (ref, color), curve_df in curves.items():
        # Check if any sizes had stock-outs
        stockout_sizes = size_kpis[
            (size_kpis["Reference"] == ref)
            & (size_kpis["Couleur"] == color)
            & (size_kpis["size_had_stockout"])
        ]["Taille"].values

        if len(stockout_sizes) == 0:
            continue

        # Get category curve for reference
        ref_fam = ref_famille[ref_famille["Reference"] == ref]
        if ref_fam.empty:
            continue
        famille = ref_fam["Famille"].iloc[0]
        cat_curve = cat_size_dist[cat_size_dist["Famille"] == famille]

        # Blend: for stock-out sizes, use category share (weighted blend)
        adjusted_shares = []
        for _, row in curve_df.iterrows():
            taille = row["Taille"]
            original_share = row["size_share"]

            if taille in stockout_sizes:
                cat_match = cat_curve[cat_curve["Taille"] == taille]
                cat_share = cat_match["cat_size_share"].iloc[0] if not cat_match.empty else original_share
                # Blend: 60% category (more trusted) + 40% product (stock-out distorted)
                adjusted_share = 0.6 * cat_share + 0.4 * original_share
                corrections_made += 1
            else:
                adjusted_share = original_share

            adjusted_shares.append(adjusted_share)

        # Re-normalize
        total = sum(adjusted_shares)
        if total > 0:
            adjusted_shares = [s / total for s in adjusted_shares]

        curve_df["size_share"] = adjusted_shares
        curve_df["curve_source"] = curve_df["curve_source"].where(
            ~curve_df["Taille"].isin(stockout_sizes),
            "STOCKOUT_CORRECTED"
        )
        curves[(ref, color)] = curve_df

    print(f"[M6] Stock-out corrections applied to {corrections_made} size entries")

    return curves


def apply_size_curve_to_sarima(sarima_forecasts, curves):
    """
    Disaggregate SARIMA forecasts (at Reference × Couleur level)
    to Reference × Couleur × Taille using size curves.
    """
    print("[M6] Applying size curves to SARIMA forecasts...")

    if sarima_forecasts.empty:
        return pd.DataFrame()

    disaggregated_rows = []

    for _, row in sarima_forecasts.iterrows():
        ref = row["Reference"]
        color = row["Couleur"]
        key = (ref, color)

        if key not in curves:
            # No size curve available — cannot disaggregate
            print(f"[M6] WARNING: No size curve for {ref}-{color}. Skipping.")
            continue

        curve_df = curves[key]

        # Order sizes properly
        ordered_sizes = determine_size_order(curve_df["Taille"].values)

        for _, size_row in curve_df.iterrows():
            taille = size_row["Taille"]
            share = size_row["size_share"]

            disaggregated_rows.append({
                "Reference": ref,
                "Couleur": color,
                "Taille": taille,
                "forecast_month": row["forecast_month"],
                "forecast_conservative": max(int(round(row["forecast_conservative"] * share)), 0),
                "forecast_base": max(int(round(row["forecast_base"] * share)), 0),
                "forecast_optimistic": max(int(round(row["forecast_optimistic"] * share)), 0),
                "model_type": "SARIMA",
                "size_share": share,
                "curve_source": size_row["curve_source"],
            })

    result = pd.DataFrame(disaggregated_rows)

    if not result.empty:
        print(f"[M6] Disaggregated {result.shape[0]} SARIMA forecast rows to size level")

    return result


def validate_catboost_size_distribution(catboost_forecasts, curves):
    """
    Check if CatBoost's size-level forecasts produce a reasonable size curve.
    If deviation from historical curve is too large, blend.
    """
    print("[M6] Validating CatBoost size distributions...")

    if catboost_forecasts.empty:
        return catboost_forecasts

    adjustments = 0

    for (ref, color), group in catboost_forecasts.groupby(["Reference", "Couleur"]):
        key = (ref, color)
        if key not in curves:
            continue

        historical_curve = curves[key].set_index("Taille")["size_share"]

        for month in group["forecast_month"].unique():
            month_data = group[group["forecast_month"] == month]
            total_base = month_data["forecast_base"].sum()

            if total_base == 0:
                continue

            # Compute implied size curve from CatBoost
            for _, row in month_data.iterrows():
                taille = row["Taille"]
                implied_share = row["forecast_base"] / total_base

                if taille in historical_curve.index:
                    hist_share = historical_curve.loc[taille]

                    # If deviation > 20 percentage points, blend
                    if abs(implied_share - hist_share) > 0.20:
                        blended_base = int(round(
                            total_base * (0.7 * implied_share + 0.3 * hist_share)
                        ))
                        # Update in the original dataframe
                        mask = (
                            (catboost_forecasts["Reference"] == ref)
                            & (catboost_forecasts["Couleur"] == color)
                            & (catboost_forecasts["Taille"] == taille)
                            & (catboost_forecasts["forecast_month"] == month)
                        )
                        catboost_forecasts.loc[mask, "forecast_base"] = blended_base
                        adjustments += 1

    print(f"[M6] CatBoost size distribution adjustments: {adjustments}")

    return catboost_forecasts


def apply_business_rules(forecast_df):
    """
    Apply size curve business rules:
    - Max share cap
    - Min quantity per size
    - Round to integers
    """
    print("[M6] Applying business rules...")

    if forecast_df.empty:
        return forecast_df

    for scenario in ["forecast_conservative", "forecast_base", "forecast_optimistic"]:
        # Ensure non-negative integers
        forecast_df[scenario] = forecast_df[scenario].clip(lower=0).round().astype(int)

    # Cap maximum share per size within each product-color-month
    for (ref, color, month), group in forecast_df.groupby(
        ["Reference", "Couleur", "forecast_month"]
    ):
        for scenario in ["forecast_conservative", "forecast_base", "forecast_optimistic"]:
            total = group[scenario].sum()
            if total == 0:
                continue

            shares = group[scenario] / total
            capped = shares.clip(upper=SIZE_MAX_SHARE_CAP)

            # Re-normalize if any were capped
            if (capped != shares).any():
                capped_total = capped.sum()
                if capped_total > 0:
                    new_values = (capped / capped_total * total).round().astype(int)
                    forecast_df.loc[group.index, scenario] = new_values.values

    print(f"[M6] Business rules applied")

    return forecast_df


def run_module6(df_raw, size_kpis, sarima_forecasts, catboost_forecasts):
    """Execute Module 6."""
    print("\n" + "=" * 60)
    print("MODULE 6: SIZE CURVE ENGINE")
    print("=" * 60)

    # Compute curves
    curves, cat_size_dist = compute_product_size_curves(df_raw, size_kpis)

    # Correct stock-out distortions
    curves = correct_stockout_distortions(curves, size_kpis, cat_size_dist, df_raw)

    # Apply to SARIMA forecasts
    sarima_by_size = apply_size_curve_to_sarima(sarima_forecasts, curves)

    # Validate CatBoost forecasts
    catboost_validated = validate_catboost_size_distribution(
        catboost_forecasts.copy(), curves
    )

    # Apply business rules to both
    sarima_by_size = apply_business_rules(sarima_by_size)
    catboost_validated = apply_business_rules(catboost_validated)

    output = {
        "size_curves": curves,
        "category_size_curves": cat_size_dist,
        "sarima_forecasts_by_size": sarima_by_size,
        "catboost_forecasts_validated": catboost_validated,
    }

    print(f"\n[M6] ✓ Module 6 complete")
    return output