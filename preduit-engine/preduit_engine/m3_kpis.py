"""
============================================================
MODULE 3: KPI COMPUTATION ENGINE
- SKU-level KPIs
- Client-level KPIs
- Category-level KPIs
- Financial KPIs (with placeholders)
============================================================
"""

import pandas as pd
import numpy as np
from .config import *


def compute_sku_kpis(df_raw, monthly_sku_color, profiles):
    """
    Compute SKU-level KPIs per Reference × Couleur.
    Both overall and per-season.
    """
    print("[M3] Computing SKU-level KPIs...")

    # ── Overall KPIs per Reference × Couleur ──
    sku_kpis = (
        df_raw.groupby(["Reference", "Couleur"])
        .agg({
            "true_demand": "sum",
            "CDE_qte": "sum",
            "LIV_qte": "sum",
            "RELIQUAT_qte": "sum",
            "ANN_qte": "sum",
            "Client": "nunique",
            "Prix": "mean",
            "Reference_CDE": "nunique",
        })
        .reset_index()
        .rename(columns={
            "true_demand": "total_true_demand",
            "CDE_qte": "total_ordered",
            "LIV_qte": "total_delivered",
            "RELIQUAT_qte": "total_backorder",
            "ANN_qte": "total_cancelled",
            "Client": "total_buying_clients",
            "Prix": "avg_price",
            "Reference_CDE": "total_orders",
        })
    )

    # ── Compute active client base ──
    # Active = any client who ordered anything in last 24 months
    max_date = df_raw["Date_Commande"].max()
    cutoff_date = max_date - pd.DateOffset(months=ACTIVE_CLIENT_LOOKBACK_MONTHS)
    active_clients = df_raw.loc[
        df_raw["Date_Commande"] >= cutoff_date, "Client"
    ].nunique()

    print(f"[M3] Active client base (last {ACTIVE_CLIENT_LOOKBACK_MONTHS} months): "
          f"{active_clients}")

    # ── Derived KPIs ──
    sku_kpis["diffusion_rate"] = (
        sku_kpis["total_buying_clients"] / active_clients
    )
    sku_kpis["depth_per_client"] = np.where(
        sku_kpis["total_buying_clients"] > 0,
        sku_kpis["total_true_demand"] / sku_kpis["total_buying_clients"],
        0
    )
    sku_kpis["fill_rate"] = np.where(
        sku_kpis["total_ordered"] > 0,
        sku_kpis["total_delivered"] / sku_kpis["total_ordered"],
        0
    )
    sku_kpis["cancellation_rate"] = np.where(
        sku_kpis["total_ordered"] > 0,
        sku_kpis["total_cancelled"] / sku_kpis["total_ordered"],
        0
    )
    sku_kpis["backorder_rate"] = np.where(
        sku_kpis["total_ordered"] > 0,
        sku_kpis["total_backorder"] / sku_kpis["total_ordered"],
        0
    )

    # ── Reorder Rate ──
    # Clients who bought this SKU-Color in 2+ distinct seasons
    client_season_counts = (
        df_raw[df_raw["true_demand"] > 0]
        .groupby(["Reference", "Couleur", "Client"])["season_type"]
        .nunique()
        .reset_index()
        .rename(columns={"season_type": "seasons_purchased"})
    )
    reorder_clients = (
        client_season_counts[client_season_counts["seasons_purchased"] >= 2]
        .groupby(["Reference", "Couleur"])["Client"]
        .nunique()
        .reset_index()
        .rename(columns={"Client": "reorder_clients"})
    )
    sku_kpis = sku_kpis.merge(reorder_clients, on=["Reference", "Couleur"], how="left")
    sku_kpis["reorder_clients"] = sku_kpis["reorder_clients"].fillna(0)
    sku_kpis["reorder_rate"] = np.where(
        sku_kpis["total_buying_clients"] > 0,
        sku_kpis["reorder_clients"] / sku_kpis["total_buying_clients"],
        0
    )

    # ── Merge with profiles for history info ──
    sku_kpis = sku_kpis.merge(
        profiles[["Reference", "Couleur", "span_months", "months_with_data",
                  "model_assignment", "cv"]],
        on=["Reference", "Couleur"],
        how="left"
    )

    # ── Financial KPIs (placeholder) ──
    sku_kpis["expected_revenue_per_unit"] = sku_kpis["avg_price"]
    sku_kpis["estimated_cost_per_unit"] = sku_kpis["avg_price"] * DEFAULT_COST_RATIO
    sku_kpis["estimated_margin_per_unit"] = (
        sku_kpis["expected_revenue_per_unit"] - sku_kpis["estimated_cost_per_unit"]
    )
    sku_kpis["estimated_margin_rate"] = np.where(
        sku_kpis["expected_revenue_per_unit"] > 0,
        sku_kpis["estimated_margin_per_unit"] / sku_kpis["expected_revenue_per_unit"],
        0
    )

    print(f"[M3] SKU KPIs computed for {sku_kpis.shape[0]} Reference-Couleur combos")

    return sku_kpis, active_clients


def compute_size_kpis(df_raw):
    """
    Compute size-level KPIs per Reference × Couleur × Taille.
    Used for size curve and for CatBoost features.
    """
    print("[M3] Computing size-level KPIs...")

    size_kpis = (
        df_raw.groupby(["Reference", "Couleur", "Taille"])
        .agg({
            "true_demand": "sum",
            "CDE_qte": "sum",
            "LIV_qte": "sum",
            "RELIQUAT_qte": "sum",
            "Client": "nunique",
        })
        .reset_index()
        .rename(columns={
            "true_demand": "size_total_demand",
            "CDE_qte": "size_total_ordered",
            "LIV_qte": "size_total_delivered",
            "RELIQUAT_qte": "size_total_backorder",
            "Client": "size_buying_clients",
        })
    )

    # Compute size share within each Reference × Couleur
    ref_totals = (
        size_kpis.groupby(["Reference", "Couleur"])["size_total_demand"]
        .sum()
        .reset_index()
        .rename(columns={"size_total_demand": "ref_total_demand"})
    )
    size_kpis = size_kpis.merge(ref_totals, on=["Reference", "Couleur"])
    size_kpis["size_share"] = np.where(
        size_kpis["ref_total_demand"] > 0,
        size_kpis["size_total_demand"] / size_kpis["ref_total_demand"],
        0
    )

    # Flag stock-out sizes (high backorder rate)
    size_kpis["size_backorder_rate"] = np.where(
        size_kpis["size_total_ordered"] > 0,
        size_kpis["size_total_backorder"] / size_kpis["size_total_ordered"],
        0
    )
    size_kpis["size_had_stockout"] = size_kpis["size_backorder_rate"] > 0.3

    print(f"[M3] Size KPIs computed for {size_kpis.shape[0]} "
          f"Reference-Couleur-Taille combos")

    return size_kpis


def compute_category_kpis(df_raw):
    """Compute category (Famille) level KPIs."""
    print("[M3] Computing category-level KPIs...")

    cat_kpis = (
        df_raw.groupby(["Famille", "year_month"])
        .agg({
            "true_demand": "sum",
            "Client": "nunique",
            "Reference": "nunique",
        })
        .reset_index()
        .rename(columns={
            "true_demand": "cat_monthly_demand",
            "Client": "cat_monthly_clients",
            "Reference": "cat_monthly_skus",
        })
    )

    # Overall category summary
    cat_summary = (
        df_raw.groupby("Famille")
        .agg({
            "true_demand": "sum",
            "Client": "nunique",
            "Reference": "nunique",
        })
        .reset_index()
        .rename(columns={
            "true_demand": "cat_total_demand",
            "Client": "cat_total_clients",
            "Reference": "cat_total_skus",
        })
    )

    print(f"[M3] Category KPIs: {cat_summary.shape[0]} categories")

    return cat_kpis, cat_summary


def compute_client_kpis(df_raw, active_clients_count):
    """
    Compute client-level KPIs.
    These feed into clustering (Phase 2) and into explainability.
    """
    print("[M3] Computing client-level KPIs...")

    client_kpis = (
        df_raw.groupby("Client")
        .agg({
            "true_demand": "sum",
            "CDE_net_ht": "sum",
            "LIV_net_ht": "sum",
            "Reference": "nunique",
            "Famille": "nunique",
            "year_month": "nunique",
            "Date_Commande": ["min", "max"],
            "Prix": "mean",
            "CDE_remise_ht": "sum",
            "CDE_brut_ht": "sum",
        })
        .reset_index()
    )

    # Flatten
    client_kpis.columns = [
        "Client", "total_units", "total_spend_ordered", "total_spend_delivered",
        "num_skus", "num_families", "active_months",
        "first_order", "last_order",
        "avg_price", "total_discount", "total_gross",
    ]

    # Derived
    client_kpis["avg_units_per_month"] = (
        client_kpis["total_units"] / client_kpis["active_months"].clip(lower=1)
    )
    client_kpis["discount_rate"] = np.where(
        client_kpis["total_gross"] > 0,
        client_kpis["total_discount"] / client_kpis["total_gross"],
        0
    )

    # Ordering frequency (what proportion of total months was client active)
    total_months = (
        (df_raw["Date_Commande"].max().year - df_raw["Date_Commande"].min().year) * 12
        + df_raw["Date_Commande"].max().month - df_raw["Date_Commande"].min().month + 1
    )
    client_kpis["ordering_frequency"] = (
        client_kpis["active_months"] / max(total_months, 1)
    )

    # Client metadata
    meta = df_raw.drop_duplicates(subset=["Client"])[
        ["Client", "Nom", "Famille_client", "Pays", "Secteur", "Localisation"]
    ]
    client_kpis = client_kpis.merge(meta, on="Client", how="left")

    print(f"[M3] Client KPIs computed for {client_kpis.shape[0]} clients")

    return client_kpis


def run_module3(df_raw, monthly_sku_color, profiles):
    """Execute Module 3."""
    print("\n" + "=" * 60)
    print("MODULE 3: KPI COMPUTATION ENGINE")
    print("=" * 60)

    sku_kpis, active_clients = compute_sku_kpis(df_raw, monthly_sku_color, profiles)
    size_kpis = compute_size_kpis(df_raw)
    cat_kpis_monthly, cat_summary = compute_category_kpis(df_raw)
    client_kpis = compute_client_kpis(df_raw, active_clients)

    kpis = {
        "sku_kpis": sku_kpis,
        "size_kpis": size_kpis,
        "cat_kpis_monthly": cat_kpis_monthly,
        "cat_summary": cat_summary,
        "client_kpis": client_kpis,
        "active_clients_count": active_clients,
    }

    print(f"\n[M3] ✓ Module 3 complete")
    return kpis