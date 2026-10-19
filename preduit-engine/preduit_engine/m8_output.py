"""
============================================================
MODULE 8: OUTPUT & REPORTING
- Export recommendations to CSV/Excel
- Generate summary reports
- Model performance report
- Print key insights
============================================================
"""

import pandas as pd
import numpy as np
import os
from .config import *


def export_recommendations(recommendations, output_dir=OUTPUT_DIR):
    """Export full recommendation table to CSV."""
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, OUTPUT_RECOMMENDATIONS_FILE)

    # Select and order columns for output
    output_cols = [
        "Reference", "Couleur", "Taille", "model_type",
        # Product & season meta
        "Fournisseur", "Famille", "Theme", "Modele", "Client", "Saison",
        "Critere", "season_type", "product_status", "confidence",
        # Forecasts
        "forecast_conservative", "forecast_base", "forecast_optimistic",
        # Orders & stock
        "confirmed_orders", "current_stock", "pipeline_stock",
        "available_inventory",
        # Net to order
        "net_to_order_conservative", "net_to_order_base", "net_to_order_optimistic",
        # KPIs
        "diffusion_rate", "total_buying_clients", "depth_per_client",
        "reorder_rate", "fill_rate", "backorder_rate",
        "size_share", "size_had_stockout",
        # Financials
        "avg_price",
        "expected_revenue_base", "estimated_cost_base",
        "estimated_margin_base", "margin_rate_base",
        "financial_note",
        # History
        "span_months", "total_true_demand",
        # Explanation
        "explanation",
    ]

    available_cols = [c for c in output_cols if c in recommendations.columns]
    output_df = recommendations[available_cols].copy()

    output_df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"[M8] Recommendations exported to {filepath}")

    # Also export to Excel if openpyxl is available
    try:
        excel_path = filepath.replace(".csv", ".xlsx")
        output_df.to_excel(excel_path, index=False, sheet_name="Recommendations")
        print(f"[M8] Excel export: {excel_path}")
    except ImportError:
        print("[M8] openpyxl not installed — Excel export skipped")

    return output_df


def generate_summary_report(recommendations, sku_kpis, output_dir=OUTPUT_DIR):
    """Generate aggregated summary reports."""
    os.makedirs(output_dir, exist_ok=True)

    print("[M8] Generating summary reports...")

    if recommendations.empty:
        print("[M8] No recommendations to summarize.")
        return

    # ── 1. By Reference × Couleur (aggregated across sizes) ──
    sku_summary = (
        recommendations.groupby(["Reference", "Couleur", "model_type"])
        .agg({
            "forecast_base": "sum",
            "forecast_conservative": "sum",
            "forecast_optimistic": "sum",
            "net_to_order_base": "sum",
            "net_to_order_conservative": "sum",
            "net_to_order_optimistic": "sum",
            "confirmed_orders": "sum",
            "current_stock": "sum",
            "pipeline_stock": "sum",
            "expected_revenue_base": "sum",
            "estimated_cost_base": "sum",
            "estimated_margin_base": "sum",
            "diffusion_rate": "first",
            "total_buying_clients": "first",
            "depth_per_client": "first",
            "reorder_rate": "first",
            "confidence": "first",
            "Taille": "count",  # number of sizes
        })
        .reset_index()
        .rename(columns={"Taille": "num_sizes"})
    )

    sku_summary["margin_rate"] = np.where(
        sku_summary["expected_revenue_base"] > 0,
        sku_summary["estimated_margin_base"] / sku_summary["expected_revenue_base"],
        0
    )

    sku_path = os.path.join(output_dir, "summary_by_sku.csv")
    sku_summary.to_csv(sku_path, index=False, encoding="utf-8-sig")
    print(f"[M8] SKU summary: {sku_path}")

    # ── 2. By Model Type ──
    model_summary = (
        recommendations.groupby("model_type")
        .agg({
            "Reference": "nunique",
            "forecast_base": "sum",
            "net_to_order_base": "sum",
            "expected_revenue_base": "sum",
            "estimated_margin_base": "sum",
        })
        .reset_index()
        .rename(columns={"Reference": "num_skus"})
    )
    print("\n[M8] Summary by Model Type:")
    print(model_summary.to_string(index=False))

    # ── 3. Grand Totals ──
    print("\n[M8] Grand Totals:")
    print(f"      Total SKU-Color-Size combinations: {recommendations.shape[0]}")
    print(f"      Total forecast (base): "
          f"{recommendations['forecast_base'].sum():,.0f} units")
    print(f"      Total net-to-order (base): "
          f"{recommendations['net_to_order_base'].sum():,.0f} units")
    print(f"      Total expected revenue (base): "
          f"€{recommendations['expected_revenue_base'].sum():,.0f}")
    print(f"      Total estimated margin (base): "
          f"€{recommendations['estimated_margin_base'].sum():,.0f}")

    # ── 4. Scenario Comparison ──
    print("\n[M8] Scenario Comparison:")
    for scenario in ["conservative", "base", "optimistic"]:
        total_nto = recommendations[f"net_to_order_{scenario}"].sum()
        total_rev = recommendations[f"expected_revenue_{scenario}"].sum()
        print(f"      {scenario.upper():>15s}: "
              f"{total_nto:>8,.0f} units | €{total_rev:>12,.0f} revenue")

    # ── 5. Confidence Distribution ──
    if "confidence" in recommendations.columns:
        conf_dist = recommendations["confidence"].value_counts()
        print("\n[M8] Confidence Distribution:")
        for conf, count in conf_dist.items():
            print(f"      {conf}: {count} SKU-Color-Size combinations")


def generate_model_performance_report(sarima_results, catboost_models,
                                       output_dir=OUTPUT_DIR):
    """Report on model fitting quality."""
    os.makedirs(output_dir, exist_ok=True)

    print("\n[M8] Model Performance Report:")

    # SARIMA
    if sarima_results:
        successful = [r for r in sarima_results if r["success"]]
        failed = [r for r in sarima_results if not r["success"]]

        print(f"\n  SARIMA:")
        print(f"    Successful fits: {len(successful)}")
        print(f"    Failed (→ fallback): {len(failed)}")

        if successful:
            mapes = [r["in_sample_mape"] for r in successful
                     if r.get("in_sample_mape") is not None]
            if mapes:
                print(f"    In-sample MAPE: "
                      f"mean={np.mean(mapes):.1f}%, "
                      f"median={np.median(mapes):.1f}%, "
                      f"min={np.min(mapes):.1f}%, "
                      f"max={np.max(mapes):.1f}%")

    # CatBoost
    if catboost_models:
        print(f"\n  CatBoost:")
        for scenario, model_data in catboost_models.items():
            mape = model_data.get("val_mape")
            mae = model_data.get("val_mae")
            iters = model_data.get("best_iteration")
            mape_str = f"{mape:.1f}%" if mape is not None else "N/A"
            print(f"    {scenario}: "
                  f"Validation MAPE={mape_str}, "
                  f"MAE={mae:.2f}, "
                  f"Best iteration={iters}")


def print_top_recommendations(recommendations, top_n=20):
    """Print the top N recommendations by forecast volume."""
    print(f"\n[M8] Top {top_n} Recommendations by Forecast Volume (Base):")
    print("-" * 100)

    # Aggregate to SKU-Color level
    sku_level = (
        recommendations.groupby(["Reference", "Couleur"])
        .agg({
            "forecast_base": "sum",
            "net_to_order_base": "sum",
            "confirmed_orders": "sum",
            "current_stock": "sum",
            "expected_revenue_base": "sum",
            "model_type": "first",
            "confidence": "first",
        })
        .reset_index()
        .sort_values("forecast_base", ascending=False)
        .head(top_n)
    )

    for _, row in sku_level.iterrows():
        print(f"  {row['Reference']:>10s} | {row['Couleur']:>10s} | "
              f"Forecast: {row['forecast_base']:>5.0f} | "
              f"Net order: {row['net_to_order_base']:>5.0f} | "
              f"Confirmed: {row['confirmed_orders']:>4.0f} | "
              f"Stock: {row['current_stock']:>4.0f} | "
              f"Revenue: €{row['expected_revenue_base']:>8,.0f} | "
              f"{row['model_type']} | {row['confidence']}")


def run_module8(recommendations, monthly_detail, sarima_results,
                catboost_models, sku_kpis):
    """Execute Module 8."""
    print("\n" + "=" * 60)
    print("MODULE 8: OUTPUT & REPORTING")
    print("=" * 60)

    if recommendations.empty:
        print("[M8] No recommendations to output.")
        return

    # Export
    output_df = export_recommendations(recommendations)

    # Summary
    generate_summary_report(recommendations, sku_kpis)

    # Model performance
    generate_model_performance_report(sarima_results, catboost_models)

    # Top recommendations
    print_top_recommendations(recommendations)

    # Export monthly detail
    if not monthly_detail.empty:
        # TODO: Use OUTPUT_MONTHLY_DETAIL_FILE from config instead of hardcoding this filename
        # (duplicates client_config / REFACTOR_PLAN.md — fix post-refactor.)
        monthly_path = os.path.join(OUTPUT_DIR, "forecast_monthly_detail.csv")
        monthly_detail.to_csv(monthly_path, index=False, encoding="utf-8-sig")
        print(f"\n[M8] Monthly detail exported to {monthly_path}")

    print(f"\n[M8] ✓ Module 8 complete — all outputs generated")