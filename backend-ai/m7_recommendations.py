"""
============================================================
MODULE 7: RECOMMENDATION ASSEMBLY (WITH SANITY CHECKS)
- Combines SARIMA + CatBoost forecasts
- Applies recency dampening (kills forecasts for dead products)
- Sanity checks against historical demand
- Generates financial overlay + explanations
============================================================
"""

import pandas as pd
import numpy as np
from config import *


def combine_forecasts(sarima_by_size, catboost_validated):
    """Combine SARIMA and CatBoost forecasts."""
    print("[M7] Combining forecasts...")

    frames = []

    if not sarima_by_size.empty:
        sarima_clean = sarima_by_size[
            ["Reference", "Couleur", "Taille", "forecast_month",
             "forecast_conservative", "forecast_base", "forecast_optimistic",
             "model_type"]
        ].copy()
        frames.append(sarima_clean)

    if not catboost_validated.empty:
        # The validated engine also supplies statistical predictions, booking
        # floors and interval provenance. Keep them through persistence.
        catboost_clean = catboost_validated.copy()
        frames.append(catboost_clean)

    if not frames:
        print("[M7] WARNING: No forecasts to combine")
        return pd.DataFrame(), pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Aggregate across forecast months
    total_forecast = (
        combined.groupby(["Reference", "Couleur", "Taille", "model_type"])
        .agg({
            "forecast_conservative": "sum",
            "forecast_base": "sum",
            "forecast_optimistic": "sum",
        })
        .reset_index()
    )

    print(f"[M7] Combined: {total_forecast.shape[0]} Reference-Couleur-Taille combos")
    return combined, total_forecast


def apply_sanity_checks(total_forecast, sku_kpis, df_raw):
    """
    CRITICAL: Apply sanity checks to prevent absurd forecasts.

    Rules:
    1. RECENCY: If product had 0 demand in last 12 months -> dampen by 80%
    2. MAX CAP: Forecast cannot exceed 3× historical seasonal average
    3. MIN FLOOR: If product is active and has history, don't forecast 0
    4. NEW PRODUCT CAP: Products with <6 months history -> cap at category avg
    """
    print("[M7] Applying sanity checks...")

    n_before = total_forecast["forecast_base"].sum()
    adjustments = {"recency_dampened": 0, "max_capped": 0, "new_product_capped": 0}

    # ── Get last activity date per Reference × Couleur ──
    last_activity = (
        df_raw[df_raw["true_demand"] > 0]
        .groupby(["Reference", "Couleur"])["Date_Commande"]
        .max()
        .reset_index()
        .rename(columns={"Date_Commande": "last_demand_date"})
    )

    total_forecast = total_forecast.merge(
        last_activity, on=["Reference", "Couleur"], how="left"
    )

    max_date = df_raw["Date_Commande"].max()

    # ── Get historical seasonal average per Reference × Couleur ──
    # Average demand per 6-month window
    historical_avg = (
        sku_kpis[["Reference", "Couleur", "total_true_demand", "span_months"]]
        .copy()
    )
    historical_avg["avg_6month_demand"] = np.where(
        historical_avg["span_months"] > 0,
        historical_avg["total_true_demand"] / (historical_avg["span_months"] / 6),
        0
    )
    total_forecast = total_forecast.merge(
        historical_avg[["Reference", "Couleur", "avg_6month_demand",
                        "total_true_demand", "span_months"]],
        on=["Reference", "Couleur"],
        how="left"
    )

    # ── RULE 1: RECENCY DAMPENING ──
    # If no demand in last 12 months -> product is likely dead/discontinued
    months_since_last = np.where(
        total_forecast["last_demand_date"].notna(),
        (max_date - total_forecast["last_demand_date"]).dt.days / 30.44,
        999
    )
    total_forecast["months_since_last_demand"] = months_since_last

    # Dampening schedule
    # 0-12 months: no dampening
    # 12-18 months: 50% dampening
    # 18-24 months: 80% dampening
    # >24 months: 95% dampening
    dampening_factor = np.where(
        months_since_last <= 12, 1.0,
        np.where(
            months_since_last <= 18, 0.5,
            np.where(
                months_since_last <= 24, 0.2,
                0.05
            )
        )
    )

    for scenario in ["forecast_conservative", "forecast_base", "forecast_optimistic"]:
        original = total_forecast[scenario].copy()
        total_forecast[scenario] = (
            total_forecast[scenario] * dampening_factor
        ).round().astype(int)

        changed = (original != total_forecast[scenario]).sum()
        if scenario == "forecast_base":
            adjustments["recency_dampened"] = changed

    # ── RULE 2: MAX CAP ──
    # Forecast cannot exceed 3× historical 6-month average (per size)
    # First get size-level proportions
    avg_6m = total_forecast["avg_6month_demand"].fillna(0)

    for scenario in ["forecast_conservative", "forecast_base", "forecast_optimistic"]:
        max_allowed = (avg_6m * 3).clip(lower=5)  # at least 5 units allowed
        exceeded = total_forecast[scenario] > max_allowed
        total_forecast.loc[exceeded, scenario] = max_allowed[exceeded].astype(int)

        if scenario == "forecast_base":
            adjustments["max_capped"] = exceeded.sum()

    # ── RULE 3: NEW PRODUCT CAP ──
    # Products with very short history (<6 months span) -> cap more aggressively
    new_mask = total_forecast["span_months"].fillna(0) < 6
    for scenario in ["forecast_conservative", "forecast_base", "forecast_optimistic"]:
        # Cap new products at 2× their total historical demand (as 6-month forecast)
        new_cap = (total_forecast["total_true_demand"].fillna(0) * 2).clip(lower=3)
        exceeded = new_mask & (total_forecast[scenario] > new_cap)
        total_forecast.loc[exceeded, scenario] = new_cap[exceeded].astype(int)

        if scenario == "forecast_base":
            adjustments["new_product_capped"] = exceeded.sum()

    n_after = total_forecast["forecast_base"].sum()

    print(f"[M7] Sanity checks applied:")
    print(f"      Recency dampened: {adjustments['recency_dampened']} SKU-Color-Sizes")
    print(f"      Max capped: {adjustments['max_capped']} SKU-Color-Sizes")
    print(f"      New product capped: {adjustments['new_product_capped']} SKU-Color-Sizes")
    print(f"      Total forecast: {n_before:,.0f} -> {n_after:,.0f} "
          f"({(n_after/n_before - 1)*100:+.1f}%)")

    # Clean up temp columns
    drop_cols = ["last_demand_date", "months_since_last_demand",
                 "avg_6month_demand", "total_true_demand_merge"]
    total_forecast = total_forecast.drop(
        columns=[c for c in drop_cols if c in total_forecast.columns],
        errors="ignore"
    )

    return total_forecast


def add_current_orders_and_stock(total_forecast, df_raw, stock_info):
    raw=df_raw.copy()
    # Joolan's validated remainder already incorporates terminal order statuses.
    # Reconstructing ordered minus delivered reopens closed, unfulfilled lines.
    if 'RELIQUAT_qte' in raw:
        raw['open_quantity']=pd.to_numeric(raw.RELIQUAT_qte,errors='coerce')
    elif 'Data_Source' in raw and raw.Data_Source.eq('joolan').any():
        raise ValueError('Validated Joolan remaining quantities are required.')
    else:
        raw['open_quantity']=(raw.CDE_qte-raw.LIV_qte-raw.ANN_qte).clip(lower=0)
    if raw.open_quantity.isna().any() or (raw.open_quantity<0).any() or not np.isfinite(raw.open_quantity).all():
        raise ValueError('Open quantities must be known, finite and nonnegative.')
    if 'Order_Status' in raw:
        status=pd.to_numeric(raw.Order_Status,errors='coerce')
        supplied=raw.Order_Status.notna() & raw.Order_Status.astype(str).str.strip().ne('')
        if (supplied & ~status.isin([0,1,2,3])).any():raise ValueError('Unknown order status.')
        raw.loc[status.isin([0,2,3]),'open_quantity']=0.
    keys=['Reference','Couleur','Taille']
    orders=raw.groupby(keys).agg(confirmed_orders=('open_quantity','sum'),confirmed_delivered=('LIV_qte','sum')).reset_index()
    clients=raw[raw.open_quantity>0].groupby(keys).Client.nunique().rename('confirmed_clients').reset_index()
    orders=orders.merge(clients,on=keys,how='left');orders['confirmed_clients']=orders.confirmed_clients.fillna(0)
    result=total_forecast.merge(orders,on=['Reference','Couleur','Taille'],how='left')
    result=result.merge(stock_info[['Reference','Couleur','Taille','STOCK','CDE_four_qte']],on=['Reference','Couleur','Taille'],how='left')
    result['current_stock']=result.STOCK
    result['pipeline_stock']=result.CDE_four_qte
    result['available_inventory']=result.current_stock+result.pipeline_stock
    return result.drop(columns=['STOCK','CDE_four_qte'])


def compute_net_to_order(total_forecast):
    for scenario in ('conservative','base','optimistic'):
        total_forecast['net_to_order_'+scenario]=(total_forecast['forecast_'+scenario]-total_forecast.available_inventory).clip(lower=0)
    total_forecast['probable_additional_base']=(total_forecast.forecast_base-total_forecast.confirmed_orders).clip(lower=0)
    return total_forecast


def add_financial_overlay(total_forecast, sku_kpis):
    """Add financial calculations."""
    print("[M7] Adding financial overlay...")

    price_data = sku_kpis[["Reference", "Couleur", "avg_price"]].copy()
    total_forecast = total_forecast.merge(
        price_data, on=["Reference", "Couleur"], how="left"
    )
    total_forecast["avg_price"] = pd.to_numeric(total_forecast["avg_price"],errors='coerce').astype(float)

    for scenario in ["conservative", "base", "optimistic"]:
        nto = f"net_to_order_{scenario}"
        total_forecast[nto]=pd.to_numeric(total_forecast[nto],errors='coerce').astype(float)
        total_forecast[f"expected_revenue_{scenario}"] = (
            total_forecast[nto] * total_forecast["avg_price"]
        ).round(2)
        total_forecast[f"estimated_cost_{scenario}"] = (
            total_forecast[f"expected_revenue_{scenario}"] * DEFAULT_COST_RATIO
        ).round(2)
        total_forecast[f"estimated_margin_{scenario}"] = (
            total_forecast[f"expected_revenue_{scenario}"]
            - total_forecast[f"estimated_cost_{scenario}"]
        ).round(2)

    revenue=total_forecast["expected_revenue_base"]
    total_forecast["margin_rate_base"] = (
        total_forecast["estimated_margin_base"] / revenue.where(revenue>0)
    ).round(4)

    total_forecast["financial_note"] = (
        "Cost estimated at 50% of Prix (placeholder)."
    )

    return total_forecast


def add_kpis_to_recommendations(total_forecast, sku_kpis, size_kpis):
    """Merge KPIs into recommendations."""
    print("[M7] Adding KPIs to recommendations...")

    kpi_cols = [
        "Reference", "Couleur", "diffusion_rate", "depth_per_client",
        "reorder_rate", "total_buying_clients", "total_true_demand",
        "fill_rate", "backorder_rate", "span_months", "model_assignment",
    ]
    available = [c for c in kpi_cols if c in sku_kpis.columns]
    total_forecast = total_forecast.merge(
        sku_kpis[available],
        on=["Reference", "Couleur"],
        how="left",
        suffixes=("", "_kpi")
    )

    size_cols = [
        "Reference", "Couleur", "Taille", "size_share",
        "size_had_stockout", "size_total_demand"
    ]
    available_size = [c for c in size_cols if c in size_kpis.columns]
    total_forecast = total_forecast.merge(
        size_kpis[available_size],
        on=["Reference", "Couleur", "Taille"],
        how="left",
        suffixes=("", "_sizekpi")
    )

    return total_forecast


def add_product_metadata(total_forecast, df_raw, critere_map):
    """Add product- and season-level metadata needed by the frontend/API."""
    print("[M7] Adding product metadata...")

    # Basic product meta per Reference
    meta_cols = ["Reference", "Fournisseur", "Famille", "Theme", "Modele", "Saison"]
    available_meta = [c for c in meta_cols if c in df_raw.columns]
    if available_meta:
        ref_meta = df_raw.drop_duplicates(subset=["Reference"])[available_meta]
        total_forecast = total_forecast.merge(ref_meta, on="Reference", how="left")

    total_forecast["Client"] = ""  # Product forecasts aggregate all customers.

    # Derive canonical Saison (e.g. SS2025 / FW2025) from critere_map if needed
    if "Saison" not in total_forecast.columns and critere_map is not None and not critere_map.empty:
        needed_cols = {"Reference", "season_type", "season_year"}
        if needed_cols.issubset(set(critere_map.columns)):
            season_map = (
                critere_map[["Reference", "season_type", "season_year"]]
                .drop_duplicates(subset=["Reference"])
                .copy()
            )

            def _to_season(row):
                st = str(row["season_type"]).upper() if pd.notna(row["season_type"]) else ""
                year = row["season_year"]
                if pd.isna(year):
                    return None
                try:
                    year_str = str(int(year))
                except Exception:
                    year_str = str(year)
                if st.startswith("HIV"):  # Hiver -> FW
                    prefix = "FW"
                elif st.startswith("ETE") or st.startswith("ÉTE"):
                    prefix = "SS"
                else:
                    return None
                return f"{prefix}{year_str}"

            season_map["Saison"] = season_map.apply(_to_season, axis=1)
            season_map = season_map[["Reference", "Saison"]]
            total_forecast = total_forecast.merge(season_map, on="Reference", how="left")

    return total_forecast


def generate_explanations(total_forecast, critere_map):
    """Generate human-readable explanations."""
    print("[M7] Generating explanations...")

    # Merge Critère info
    if not critere_map.empty:
        total_forecast = total_forecast.merge(
            critere_map[["Reference", "Critere", "season_type", "product_status"]],
            on="Reference",
            how="left",
            suffixes=("", "_critere")
        )

    explanations = []
    for _, row in total_forecast.iterrows():
        parts = []

        model = row.get("model_type", "Unknown")
        span = row.get("span_months", 0)
        parts.append(f"Model: {model} | History: {span:.0f}m")

        critere = row.get("Critere", "")
        if critere and str(critere) != "nan":
            parts.append(f"Season: {critere}")

        diffusion = row.get("diffusion_rate", 0)
        clients = row.get("total_buying_clients", 0)
        if clients > 0:
            parts.append(f"Diffusion: {diffusion:.1%} ({clients:.0f} clients)")

        depth = row.get("depth_per_client", 0)
        reorder = row.get("reorder_rate", 0)
        if depth > 0:
            reorder_label=f'{reorder:.1%}' if reorder is not None and pd.notna(reorder) else 'unavailable'
            parts.append(f"Depth: {depth:.1f}/client | Reorder: {reorder_label}")

        stock = row.get("current_stock", 0)
        pipeline = row.get("pipeline_stock", 0)
        parts.append(f"Stock: {stock} | Pipeline: {pipeline}")

        explanations.append(" | ".join(parts))

    total_forecast["explanation"] = explanations

    # Confidence flag
    span = total_forecast.get("span_months", pd.Series(dtype=float)).fillna(0)
    clients = total_forecast.get("total_buying_clients", pd.Series(dtype=float)).fillna(0)
    confirmed = total_forecast.get("confirmed_orders", pd.Series(dtype=float)).fillna(0)

    total_forecast["confidence"] = np.select(
        [
            (span >= 48) & (clients >= 10) & (confirmed > 0),
            (span >= 24) & (clients >= 5),
            (span >= 12) & (clients >= 2),
        ],
        ["HIGH", "MEDIUM", "MEDIUM-LOW"],
        default="LOW"
    )

    # Boost confidence if confirmed orders exist
    has_confirmed = confirmed > 0
    total_forecast.loc[
        has_confirmed & (total_forecast["confidence"] == "LOW"),
        "confidence"
    ] = "MEDIUM-LOW"

    return total_forecast


def run_module7(sarima_by_size, catboost_validated, df_raw, stock_info,
                sku_kpis, size_kpis, critere_map, validated=False):
    """Execute Module 7."""
    print("\n" + "=" * 60)
    print("MODULE 7: RECOMMENDATION ASSEMBLY")
    print("=" * 60)

    # Combine forecasts
    combined_monthly, total_forecast = combine_forecasts(
        sarima_by_size, catboost_validated
    )

    if total_forecast.empty:
        print("[M7] No forecasts to process.")
        return {"recommendations": pd.DataFrame(), "monthly_detail": pd.DataFrame()}

    # ── SANITY CHECKS (new) ──
    if not validated:
        total_forecast = apply_sanity_checks(total_forecast, sku_kpis, df_raw)

    # Add orders & stock
    total_forecast = add_current_orders_and_stock(total_forecast, df_raw, stock_info)

    # Net-to-order
    total_forecast = compute_net_to_order(total_forecast)

    # Financial overlay
    total_forecast = add_financial_overlay(total_forecast, sku_kpis)

    # KPIs
    total_forecast = add_kpis_to_recommendations(total_forecast, sku_kpis, size_kpis)

    # Product & season metadata (for API / frontend)
    total_forecast = add_product_metadata(total_forecast, df_raw, critere_map)

    # Explanations
    total_forecast = generate_explanations(total_forecast, critere_map)

    output = {
        "recommendations": total_forecast,
        "monthly_detail": combined_monthly,
    }

    print(f"\n[M7] OK Module 7 complete")
    print(f"[M7] Final recommendations: {total_forecast.shape[0]} rows")

    return output
