"""
============================================================
MODULE 2: MODEL ASSIGNMENT
- For each Reference × Couleur, determine data span
- Assign SARIMA (≥36 months span) or CatBoost (<36 months)
- New products (≤3 months) → CatBoost analogy mode
============================================================
"""

import pandas as pd
import numpy as np
from .config import *


def compute_history_profile(monthly_sku_color):
    """
    For each Reference × Couleur, compute:
    - first_month, last_month
    - span in months
    - number of months with non-zero demand
    - total demand
    """
    print("[M2] Computing history profiles...")

    profiles = (
        monthly_sku_color.groupby(["Reference", "Couleur"])
        .agg({
            "year_month": ["min", "max", "nunique"],
            "true_demand": ["sum", "mean", "std"],
            "num_clients": "sum",
        })
        .reset_index()
    )

    # Flatten columns
    profiles.columns = [
        "Reference", "Couleur",
        "first_month", "last_month", "months_with_data",
        "total_demand", "avg_monthly_demand", "std_monthly_demand",
        "total_client_orders"
    ]

    # Calculate span in months
    profiles["first_month"] = profiles["first_month"].dt.to_timestamp()
    profiles["last_month"] = profiles["last_month"].dt.to_timestamp()
    profiles["span_months"] = (
        (profiles["last_month"].dt.year - profiles["first_month"].dt.year) * 12
        + (profiles["last_month"].dt.month - profiles["first_month"].dt.month)
        + 1  # inclusive
    )

    # Fill NaN std with 0
    profiles["std_monthly_demand"] = profiles["std_monthly_demand"].fillna(0)

    # Coefficient of variation
    profiles["cv"] = np.where(
        profiles["avg_monthly_demand"] > 0,
        profiles["std_monthly_demand"] / profiles["avg_monthly_demand"],
        0
    )

    print(f"[M2] History profiles computed for "
          f"{profiles.shape[0]} Reference-Couleur combinations")

    return profiles


def assign_models(profiles):
    """
    Assign forecasting model based on history length.

    Rules:
    - span >= 36 months (3 years) → SARIMA
    - span >= 3 months but < 36 months → CatBoost
    - span < 3 months or very few data points → CatBoost (analogy mode)
    """
    print("[M2] Assigning models...")

    conditions = [
        (profiles["span_months"] >= SARIMA_MIN_MONTHS_SPAN)
        & (profiles["months_with_data"] >= 6),    # at least 6 non-zero months too
        (profiles["span_months"] >= CATBOOST_MIN_MONTHS)
        & (profiles["months_with_data"] >= 2),
    ]
    choices = ["SARIMA", "CATBOOST"]

    profiles["model_assignment"] = np.select(
        conditions, choices, default="CATBOOST_ANALOGY"
    )

    # Print summary
    model_counts = profiles["model_assignment"].value_counts()
    print("[M2] Model assignment summary:")
    for model, count in model_counts.items():
        total_demand = profiles.loc[
            profiles["model_assignment"] == model, "total_demand"
        ].sum()
        print(f"      {model}: {count} SKU-Colors "
              f"({total_demand:.0f} total historical units)")

    return profiles


def run_module2(monthly_sku_color):
    """Execute Module 2."""
    print("\n" + "=" * 60)
    print("MODULE 2: MODEL ASSIGNMENT")
    print("=" * 60)

    profiles = compute_history_profile(monthly_sku_color)
    profiles = assign_models(profiles)

    print(f"\n[M2] ✓ Module 2 complete")
    return profiles


if __name__ == "__main__":
    from .m1_data_preparation import run_module1
    data = run_module1()
    profiles = run_module2(data["monthly_sku_color"])
    print(profiles.head(10))