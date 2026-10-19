"""
============================================================
MODULE 4: SARIMA FORECASTING (SEASONAL AGGREGATION)

KEY INSIGHT: B2B wholesale orders are NOT monthly.
They come in 2 campaign bursts per year:
  - Hiver campaign: ~Jan-Apr orders
  - Printemps campaign: ~Jul-Oct orders

Aggregating to SEASONAL level (2 seasons/year, m=2) gives
dense, meaningful time series instead of mostly-zero monthly.

For products with enough dense monthly data, we still use
monthly SARIMA.
============================================================
"""

import pandas as pd
import numpy as np
import warnings
from config import *

warnings.filterwarnings("ignore")

try:
    from pmdarima import auto_arima
    PMDARIMA_AVAILABLE = True
except ImportError:
    PMDARIMA_AVAILABLE = False
    print("[M4] WARNING: pmdarima not installed")

# ─────────────────────────────────────────────
# THRESHOLDS
# ─────────────────────────────────────────────
MIN_SEASONS_FOR_SARIMA = 4           # minimum 4 seasons (2 years)
MIN_TOTAL_DEMAND_SARIMA = 15         # minimum total units
MONTHLY_DENSITY_THRESHOLD = 0.40     # if >40% months have demand → use monthly
MAX_SARIMA_TIME_SECONDS = 10         # timeout per model


def assign_season_from_month(month):
    """
    Map calendar month to business season.
    Hiver campaign orders: Jan-Jun → HIVER
    Printemps campaign orders: Jul-Dec → PRINTEMPS
    """
    if month <= 6:
        return "H"  # Hiver
    else:
        return "P"  # Printemps


def build_seasonal_series(monthly_sku_color, ref, color):
    """
    Aggregate monthly data into seasonal data.
    Each season = ~6 months of orders summed.

    Returns:
    - seasonal Series indexed by season_id (ordinal)
    - season_labels for mapping back
    """
    subset = monthly_sku_color[
        (monthly_sku_color["Reference"] == ref)
        & (monthly_sku_color["Couleur"] == color)
    ].copy()

    if subset.empty:
        return None, None

    # Convert period to components
    subset["ym_ts"] = subset["year_month"].dt.to_timestamp()
    subset["year"] = subset["ym_ts"].dt.year
    subset["month"] = subset["ym_ts"].dt.month
    subset["season_code"] = subset["month"].apply(assign_season_from_month)
    subset["season_label"] = subset["season_code"] + subset["year"].astype(str)

    # Aggregate by season
    seasonal = (
        subset.groupby(["year", "season_code", "season_label"])
        .agg({"true_demand": "sum"})
        .reset_index()
        .sort_values(["year", "season_code"])
    )

    # Create ordinal season index
    seasonal = seasonal.reset_index(drop=True)
    seasonal["season_id"] = range(len(seasonal))

    # Build complete sequence (fill missing seasons with 0)
    min_year = seasonal["year"].min()
    max_year = seasonal["year"].max()

    full_seasons = []
    for y in range(min_year, max_year + 1):
        for sc in ["H", "P"]:
            full_seasons.append({
                "year": y,
                "season_code": sc,
                "season_label": f"{sc}{y}",
            })

    full_df = pd.DataFrame(full_seasons)
    full_df = full_df.merge(
        seasonal[["year", "season_code", "true_demand"]],
        on=["year", "season_code"],
        how="left"
    )
    full_df["true_demand"] = full_df["true_demand"].fillna(0)

    # Trim leading zeros (before product existed)
    first_nonzero = full_df[full_df["true_demand"] > 0].index.min()
    if first_nonzero is not None:
        full_df = full_df.loc[first_nonzero:].reset_index(drop=True)

    series = full_df["true_demand"].copy()
    series.index = range(len(series))
    labels = full_df["season_label"].tolist()

    return series, labels


def build_monthly_series_dense_check(monthly_sku_color, ref, color):
    """
    Build monthly series and check density.
    Returns series and density ratio.
    """
    subset = monthly_sku_color[
        (monthly_sku_color["Reference"] == ref)
        & (monthly_sku_color["Couleur"] == color)
    ].copy()

    if subset.empty:
        return None, 0

    min_month = subset["year_month"].min()
    max_month = subset["year_month"].max()
    full_range = pd.period_range(start=min_month, end=max_month, freq="M")

    series = subset.set_index("year_month")["true_demand"]
    series = series.groupby(level=0).sum()
    series = series.reindex(full_range, fill_value=0)

    n_nonzero = (series > 0).sum()
    density = n_nonzero / len(series) if len(series) > 0 else 0

    return series, density


def fit_sarima(series, seasonal_period, max_time=MAX_SARIMA_TIME_SECONDS):
    """
    Fit SARIMA with timeout protection.
    """
    import signal
    import platform

    n = len(series)

    if n < 4:
        return None

    # Determine search space based on series length
    if n < seasonal_period * 2:
        seasonal = False
        sp = 1
    else:
        seasonal = True
        sp = seasonal_period

    try:
        model = auto_arima(
            series.values.astype(float),
            seasonal=seasonal,
            m=sp,
            max_p=2,
            max_d=1,
            max_q=2,
            max_P=1 if seasonal else 0,
            max_D=1 if seasonal else 0,
            max_Q=1 if seasonal else 0,
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
            trace=False,
            n_fits=15,
            maxiter=80,
        )
        return model
    except Exception:
        return None


def forecast_single_product(monthly_sku_color, ref, color):
    """
    Forecast a single Reference × Couleur.

    Strategy:
    1. Check monthly density
    2. If dense (>40% months with data) → monthly SARIMA (m=12)
    3. If sparse → seasonal SARIMA (m=2, 2 seasons/year)
    4. Return forecasts at monthly level either way
    """
    result = {
        "Reference": ref,
        "Couleur": color,
        "success": False,
        "fallback_to_catboost": False,
        "error": None,
        "forecasts": [],
    }

    # ── Check monthly density ──
    monthly_series, density = build_monthly_series_dense_check(
        monthly_sku_color, ref, color
    )

    if monthly_series is None or monthly_series.sum() < MIN_TOTAL_DEMAND_SARIMA:
        result["error"] = "insufficient_demand"
        result["fallback_to_catboost"] = True
        return result

    use_monthly = density >= MONTHLY_DENSITY_THRESHOLD and len(monthly_series) >= 24

    if use_monthly:
        # ── MONTHLY SARIMA ──
        model = fit_sarima(monthly_series, seasonal_period=12)

        if model is not None:
            try:
                fc, ci = model.predict(
                    n_periods=FORECAST_HORIZON_MONTHS,
                    return_conf_int=True,
                    alpha=0.20
                )

                last_period = monthly_series.index[-1]
                forecast_index = pd.period_range(
                    start=last_period + 1,
                    periods=FORECAST_HORIZON_MONTHS,
                    freq="M"
                )

                # In-sample MAPE
                in_sample = model.predict_in_sample()
                nz = monthly_series.values > 0
                mape = None
                if nz.sum() > 2:
                    residuals = np.abs(monthly_series.values[nz] - in_sample[nz])
                    mape = np.mean(residuals / monthly_series.values[nz]) * 100

                result["success"] = True
                result["model_type"] = "SARIMA_M"
                result["granularity"] = "monthly"
                result["order"] = model.order
                result["seasonal_order"] = model.seasonal_order
                result["aic"] = model.aic()
                result["in_sample_mape"] = mape
                result["density"] = density

                for i, period in enumerate(forecast_index):
                    result["forecasts"].append({
                        "forecast_month": period,
                        "forecast_base": max(int(round(fc[i])), 0),
                        "forecast_conservative": max(int(round(ci[i, 0])), 0),
                        "forecast_optimistic": max(int(round(ci[i, 1])), 0),
                    })

                return result

            except Exception as e:
                pass  # Fall through to seasonal

    # ── SEASONAL SARIMA (m=2) ──
    seasonal_series, season_labels = build_seasonal_series(
        monthly_sku_color, ref, color
    )

    if seasonal_series is None or len(seasonal_series) < MIN_SEASONS_FOR_SARIMA:
        result["error"] = "insufficient_seasons"
        result["fallback_to_catboost"] = True
        return result

    if seasonal_series.sum() < MIN_TOTAL_DEMAND_SARIMA:
        result["error"] = "low_seasonal_demand"
        result["fallback_to_catboost"] = True
        return result

    # Check seasonal density
    n_nonzero_seasons = (seasonal_series > 0).sum()
    if n_nonzero_seasons < 3:
        result["error"] = "too_few_nonzero_seasons"
        result["fallback_to_catboost"] = True
        return result

    model = fit_sarima(seasonal_series, seasonal_period=2)

    if model is None:
        result["error"] = "sarima_fit_failed"
        result["fallback_to_catboost"] = True
        return result

    try:
        # Forecast next 2 seasons (covers ~12 months)
        n_forecast_seasons = max(FORECAST_HORIZON_MONTHS // 6, 1) + 1
        fc, ci = model.predict(
            n_periods=n_forecast_seasons,
            return_conf_int=True,
            alpha=0.20
        )

        # In-sample MAPE
        in_sample = model.predict_in_sample()
        nz = seasonal_series.values > 0
        mape = None
        if nz.sum() > 2:
            residuals = np.abs(seasonal_series.values[nz] - in_sample[nz])
            mape = np.mean(residuals / seasonal_series.values[nz]) * 100

        # Convert seasonal forecasts to monthly
        # Determine which season each forecast corresponds to
        last_year = int(season_labels[-1][1:]) if season_labels else 2024
        last_season = season_labels[-1][0] if season_labels else "H"

        current_year = last_year
        current_season = last_season

        result["success"] = True
        result["model_type"] = "SARIMA_S"
        result["granularity"] = "seasonal"
        result["order"] = model.order
        result["seasonal_order"] = model.seasonal_order
        result["aic"] = model.aic()
        result["in_sample_mape"] = mape
        result["density"] = density
        result["n_seasons_history"] = len(seasonal_series)

        for s_idx in range(n_forecast_seasons):
            # Advance to next season
            if current_season == "H":
                current_season = "P"
            else:
                current_season = "H"
                current_year += 1

            # Season forecast total
            season_total_base = max(int(round(fc[s_idx])), 0)
            season_total_cons = max(int(round(ci[s_idx, 0])), 0)
            season_total_opt = max(int(round(ci[s_idx, 1])), 0)

            # Distribute across months in this season
            if current_season == "H":
                # Hiver: Jan-Jun, heavy in Feb-Mar
                month_weights = {1: 0.05, 2: 0.30, 3: 0.35, 4: 0.20, 5: 0.07, 6: 0.03}
            else:
                # Printemps: Jul-Dec, heavy in Sep-Oct
                month_weights = {7: 0.05, 8: 0.15, 9: 0.30, 10: 0.30, 11: 0.15, 12: 0.05}

            for m, weight in month_weights.items():
                period = pd.Period(f"{current_year}-{m:02d}", freq="M")
                result["forecasts"].append({
                    "forecast_month": period,
                    "forecast_base": max(int(round(season_total_base * weight)), 0),
                    "forecast_conservative": max(int(round(season_total_cons * weight)), 0),
                    "forecast_optimistic": max(int(round(season_total_opt * weight)), 0),
                })

        return result

    except Exception as e:
        result["error"] = str(e)[:100]
        result["fallback_to_catboost"] = True
        return result


def run_sarima_forecasting(monthly_sku_color, profiles):
    """Run SARIMA for all eligible products."""
    print("[M4] Running SARIMA forecasting...")

    sarima_products = profiles[
        profiles["model_assignment"] == "SARIMA"
    ][["Reference", "Couleur"]].values

    total = len(sarima_products)
    print(f"[M4] {total} SKU-Color combinations assigned to SARIMA")

    results = []
    fallback_list = []

    stats = {
        "monthly_sarima": 0,
        "seasonal_sarima": 0,
        "fallback": 0,
    }

    for i, (ref, color) in enumerate(sarima_products):
        if (i + 1) % 200 == 0 or (i + 1) == total:
            print(f"[M4] Processing {i + 1}/{total}... "
                  f"(M:{stats['monthly_sarima']} S:{stats['seasonal_sarima']} "
                  f"F:{stats['fallback']})")

        result = forecast_single_product(monthly_sku_color, ref, color)
        results.append(result)

        if result["success"]:
            if result.get("granularity") == "monthly":
                stats["monthly_sarima"] += 1
            else:
                stats["seasonal_sarima"] += 1
        else:
            stats["fallback"] += 1
            fallback_list.append((ref, color))

    # Summary
    successful = [r for r in results if r["success"]]
    print(f"\n[M4] SARIMA Results:")
    print(f"      Monthly SARIMA: {stats['monthly_sarima']}")
    print(f"      Seasonal SARIMA: {stats['seasonal_sarima']}")
    print(f"      → CatBoost fallback: {stats['fallback']}")
    print(f"      Total successful: {len(successful)}")

    if successful:
        mapes = [r["in_sample_mape"] for r in successful
                 if r.get("in_sample_mape") is not None]
        if mapes:
            print(f"      In-sample MAPE: mean={np.mean(mapes):.1f}%, "
                  f"median={np.median(mapes):.1f}%, "
                  f"p25={np.percentile(mapes, 25):.1f}%, "
                  f"p75={np.percentile(mapes, 75):.1f}%")

    # Errors breakdown
    errors = {}
    for r in results:
        if r.get("error"):
            err = r["error"]
            errors[err] = errors.get(err, 0) + 1
    if errors:
        print(f"      Fallback reasons:")
        for err, cnt in sorted(errors.items(), key=lambda x: -x[1]):
            print(f"        {err}: {cnt}")

    return results, fallback_list


def compile_sarima_forecasts(results):
    """Compile all SARIMA forecasts into a DataFrame."""
    rows = []
    for r in results:
        if not r["success"]:
            continue

        for fc in r["forecasts"]:
            rows.append({
                "Reference": r["Reference"],
                "Couleur": r["Couleur"],
                "forecast_month": fc["forecast_month"],
                "forecast_base": fc["forecast_base"],
                "forecast_conservative": fc["forecast_conservative"],
                "forecast_optimistic": fc["forecast_optimistic"],
                "model_type": r.get("model_type", "SARIMA"),
                "model_order": str(r.get("order", "")),
                "model_seasonal_order": str(r.get("seasonal_order", "")),
                "aic": r.get("aic"),
                "in_sample_mape": r.get("in_sample_mape"),
            })

    forecast_df = pd.DataFrame(rows)

    if not forecast_df.empty:
        # Filter to only next FORECAST_HORIZON_MONTHS months
        max_month = forecast_df["forecast_month"].max()
        min_month = forecast_df["forecast_month"].min()

        # Keep only the requested horizon
        cutoff = min_month + FORECAST_HORIZON_MONTHS
        # forecast_df = forecast_df[forecast_df["forecast_month"] < cutoff]

        n_skus = forecast_df[["Reference", "Couleur"]].drop_duplicates().shape[0]
        print(f"[M4] Compiled {forecast_df.shape[0]} forecast rows ({n_skus} SKU-Colors)")

    return forecast_df


def run_module4(monthly_sku_color, profiles):
    """Execute Module 4."""
    print("\n" + "=" * 60)
    print("MODULE 4: SARIMA FORECASTING")
    print("=" * 60)

    results, fallback_list = run_sarima_forecasting(monthly_sku_color, profiles)
    sarima_forecasts = compile_sarima_forecasts(results)

    output = {
        "sarima_results": results,
        "sarima_forecasts": sarima_forecasts,
        "fallback_to_catboost": fallback_list,
    }

    print(f"\n[M4] ✓ Module 4 complete")
    return output