"""
Walk-forward backtesting for forecast accuracy (WMAPE, bias, interval coverage).

Scores model-level monthly forecasts before M7 business transforms.
Reuses M2 model assignment and M4 SARIMA; CatBoost SKUs use lag/rolling baselines
with quantile bands derived from historical residuals when full retrain is too costly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import (
    BACKTEST_HOLDOUT_MONTHS,
    BACKTEST_MAX_SKUS,
    BACKTEST_MIN_ACTUALS,
    COL_TRUE_DEMAND,
    COL_YEAR_MONTH,
)
from .database import get_connection, save_backtest_results
from .m2_model_assignment import run_module2
from .m4_sarima import forecast_single_product


@dataclass
class BacktestResult:
    summary: Dict[str, Any]
    fold_metrics: List[Dict[str, Any]]
    breakdowns: List[Dict[str, Any]]


def compute_wmape(actuals: np.ndarray, forecasts: np.ndarray) -> Optional[float]:
    actuals = np.asarray(actuals, dtype=float)
    forecasts = np.asarray(forecasts, dtype=float)
    denom = np.sum(actuals)
    if denom < BACKTEST_MIN_ACTUALS:
        return None
    return float(np.sum(np.abs(actuals - forecasts)) / denom * 100)


def compute_bias(actuals: np.ndarray, forecasts: np.ndarray) -> Optional[float]:
    actuals = np.asarray(actuals, dtype=float)
    forecasts = np.asarray(forecasts, dtype=float)
    denom = np.sum(actuals)
    if denom < BACKTEST_MIN_ACTUALS:
        return None
    return float(np.sum(forecasts - actuals) / denom * 100)


def compute_interval_coverage(
    actuals: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> Optional[float]:
    actuals = np.asarray(actuals, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    if len(actuals) == 0:
        return None
    inside = (actuals >= lower) & (actuals <= upper)
    return float(np.mean(inside) * 100)


def _load_history_from_db(conn) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load size-level history and famille map from SQLite."""
    hd = pd.read_sql_query(
        """
        SELECT reference, couleur, taille, year_month, true_demand
        FROM historical_demand
        ORDER BY year_month
        """,
        conn,
    )
    if hd.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    hd["year_month"] = pd.PeriodIndex(hd["year_month"], freq="M")
    hd["Reference"] = hd["reference"]
    hd["Couleur"] = hd["couleur"]
    hd["Taille"] = hd["taille"]
    hd[COL_TRUE_DEMAND] = hd["true_demand"].astype(float)

    monthly_size = hd[
        ["Reference", "Couleur", "Taille", COL_YEAR_MONTH, COL_TRUE_DEMAND]
    ].copy()

    monthly_color = (
        monthly_size.groupby(["Reference", "Couleur", COL_YEAR_MONTH], as_index=False)[
            COL_TRUE_DEMAND
        ].sum()
    )

    famille_map = pd.read_sql_query(
        """
        SELECT DISTINCT reference, couleur, famille
        FROM recommendations
        WHERE famille IS NOT NULL AND famille != ''
        """,
        conn,
    )
    if not famille_map.empty:
        famille_map = famille_map.rename(
            columns={"reference": "Reference", "couleur": "Couleur", "famille": "Famille"}
        )
    else:
        famille_map = pd.DataFrame(columns=["Reference", "Couleur", "Famille"])

    return monthly_size, monthly_color, famille_map


def _baseline_size_forecast(history: pd.Series, target_month: pd.Period) -> Tuple[float, float, float]:
    """Lag/rolling baseline with simple quantile bands for short-history SKUs."""
    hist = history.sort_index()
    if hist.empty:
        return 0.0, 0.0, 0.0

    target_ts = target_month.to_timestamp()
    lag12_key = target_month - 12
    lag1_key = target_month - 1

    base = 0.0
    if lag12_key in hist.index:
        base = float(hist.loc[lag12_key])
    elif len(hist) >= 3:
        base = float(hist.iloc[-3:].mean())
    elif lag1_key in hist.index:
        base = float(hist.loc[lag1_key])
    else:
        base = float(hist.iloc[-1])

    base = max(base, 0.0)
    residuals = []
    months = sorted(hist.index)
    for i, m in enumerate(months):
        if i == 0:
            continue
        pred = float(hist.iloc[i - 1])
        residuals.append(float(hist.loc[m]) - pred)

    if len(residuals) >= 5:
        low_adj = float(np.quantile(residuals, 0.20))
        high_adj = float(np.quantile(residuals, 0.80))
    else:
        low_adj = -0.2 * base
        high_adj = 0.2 * base

    conservative = max(base + low_adj, 0.0)
    optimistic = max(base + high_adj, 0.0)
    return conservative, base, optimistic


def _sarima_forecast_for_month(
    monthly_color: pd.DataFrame,
    ref: str,
    color: str,
    target_month: pd.Period,
) -> Optional[Tuple[float, float, float, str]]:
    truncated = monthly_color[monthly_color[COL_YEAR_MONTH] < target_month]
    result = forecast_single_product(truncated, ref, color)
    if not result.get("success"):
        return None

    model_type = result.get("model_type", "SARIMA")
    for fc in result.get("forecasts", []):
        fm = fc.get("forecast_month")
        if fm is None:
            continue
        if pd.Period(fm, freq="M") == target_month:
            return (
                float(fc.get("forecast_conservative", 0)),
                float(fc.get("forecast_base", 0)),
                float(fc.get("forecast_optimistic", 0)),
                model_type,
            )
    return None


def _score_fold(
    monthly_size: pd.DataFrame,
    monthly_color: pd.DataFrame,
    famille_map: pd.DataFrame,
    target_month: pd.Period,
) -> pd.DataFrame:
    """Generate one-step forecasts for target_month and return scored rows."""
    actuals = monthly_size[monthly_size[COL_YEAR_MONTH] == target_month].copy()
    if actuals.empty:
        return pd.DataFrame()

    truncated_color = monthly_color[monthly_color[COL_YEAR_MONTH] < target_month]
    profiles = run_module2(truncated_color) if not truncated_color.empty else pd.DataFrame()

    rows: List[Dict[str, Any]] = []
    keys = actuals[["Reference", "Couleur", "Taille"]].drop_duplicates()

    if BACKTEST_MAX_SKUS > 0 and len(keys) > BACKTEST_MAX_SKUS:
        keys = keys.sample(BACKTEST_MAX_SKUS, random_state=42)

    sarima_assignments = set()
    if not profiles.empty:
        sarima_mask = profiles["model_assignment"].astype(str).str.startswith("SARIMA")
        for _, p in profiles[sarima_mask].iterrows():
            sarima_assignments.add((p["Reference"], p["Couleur"]))

    color_forecasts: Dict[Tuple[str, str], Tuple[float, float, float, str]] = {}

    for _, key in keys.iterrows():
        ref, color, taille = key["Reference"], key["Couleur"], key["Taille"]
        act_row = actuals[
            (actuals["Reference"] == ref)
            & (actuals["Couleur"] == color)
            & (actuals["Taille"] == taille)
        ]
        if act_row.empty:
            continue
        actual = float(act_row[COL_TRUE_DEMAND].iloc[0])

        model_type = "CATBOOST"
        if (ref, color) in sarima_assignments:
            if (ref, color) not in color_forecasts:
                sarima_fc = _sarima_forecast_for_month(
                    monthly_color, ref, color, target_month
                )
                if sarima_fc:
                    color_forecasts[(ref, color)] = sarima_fc

            if (ref, color) in color_forecasts:
                cons_c, base_c, opt_c, mt = color_forecasts[(ref, color)]
                model_type = mt
                hist_size = monthly_size[
                    (monthly_size["Reference"] == ref)
                    & (monthly_size["Couleur"] == color)
                    & (monthly_size["Taille"] == taille)
                    & (monthly_size[COL_YEAR_MONTH] < target_month)
                ].set_index(COL_YEAR_MONTH)[COL_TRUE_DEMAND]

                if hist_size.sum() > 0 and base_c > 0:
                    share = float(hist_size.sum()) / max(
                        float(
                            monthly_size[
                                (monthly_size["Reference"] == ref)
                                & (monthly_size["Couleur"] == color)
                                & (monthly_size[COL_YEAR_MONTH] < target_month)
                            ][COL_TRUE_DEMAND].sum()
                        ),
                        1.0,
                    )
                    conservative = cons_c * share
                    base = base_c * share
                    optimistic = opt_c * share
                else:
                    conservative, base, optimistic = _baseline_size_forecast(
                        hist_size, target_month
                    )
            else:
                hist_size = monthly_size[
                    (monthly_size["Reference"] == ref)
                    & (monthly_size["Couleur"] == color)
                    & (monthly_size["Taille"] == taille)
                    & (monthly_size[COL_YEAR_MONTH] < target_month)
                ].set_index(COL_YEAR_MONTH)[COL_TRUE_DEMAND]
                conservative, base, optimistic = _baseline_size_forecast(
                    hist_size, target_month
                )
                model_type = "CATBOOST"
        else:
            hist_size = monthly_size[
                (monthly_size["Reference"] == ref)
                & (monthly_size["Couleur"] == color)
                & (monthly_size["Taille"] == taille)
                & (monthly_size[COL_YEAR_MONTH] < target_month)
            ].set_index(COL_YEAR_MONTH)[COL_TRUE_DEMAND]
            conservative, base, optimistic = _baseline_size_forecast(
                hist_size, target_month
            )
            model_type = "CATBOOST"

        famille = "UNKNOWN"
        if not famille_map.empty:
            match = famille_map[
                (famille_map["Reference"] == ref) & (famille_map["Couleur"] == color)
            ]
            if not match.empty:
                famille = str(match["Famille"].iloc[0])

        rows.append(
            {
                "Reference": ref,
                "Couleur": color,
                "Taille": taille,
                "Famille": famille,
                "model_type": model_type,
                "actual": actual,
                "forecast_base": base,
                "forecast_conservative": conservative,
                "forecast_optimistic": optimistic,
            }
        )

    return pd.DataFrame(rows)


def _aggregate_metrics(scored: pd.DataFrame) -> Dict[str, Optional[float]]:
    if scored.empty:
        return {"wmape": None, "bias": None, "coverage_80": None, "total_actual": 0.0}

    actuals = scored["actual"].values
    base = scored["forecast_base"].values
    cons = scored["forecast_conservative"].values
    opt = scored["forecast_optimistic"].values

    return {
        "wmape": compute_wmape(actuals, base),
        "bias": compute_bias(actuals, base),
        "coverage_80": compute_interval_coverage(actuals, cons, opt),
        "total_actual": float(np.sum(actuals)),
    }


def run_walk_forward_backtest(
    holdout_months: Optional[int] = None,
    conn=None,
    run_id: Optional[int] = None,
) -> BacktestResult:
    """Execute rolling-origin backtest over the last N months in historical_demand."""
    holdout = holdout_months or BACKTEST_HOLDOUT_MONTHS
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        monthly_size, monthly_color, famille_map = _load_history_from_db(conn)
        if monthly_size.empty:
            return BacktestResult(
                summary={"wmape": None, "bias": None, "coverage80": None, "skuCount": 0},
                fold_metrics=[],
                breakdowns=[],
            )

        all_months = sorted(monthly_size[COL_YEAR_MONTH].unique())
        if len(all_months) <= holdout:
            fold_months = all_months[-max(1, len(all_months) // 2) :]
        else:
            fold_months = all_months[-holdout:]

        fold_metrics: List[Dict[str, Any]] = []
        all_scored: List[pd.DataFrame] = []

        for target_month in fold_months:
            scored = _score_fold(monthly_size, monthly_color, famille_map, target_month)
            if scored.empty:
                continue
            scored["fold_month"] = str(target_month)
            all_scored.append(scored)
            metrics = _aggregate_metrics(scored)
            fold_metrics.append(
                {
                    "fold_month": str(target_month),
                    "wmape": metrics["wmape"],
                    "bias": metrics["bias"],
                    "coverage_80": metrics["coverage_80"],
                    "total_actual": metrics["total_actual"],
                }
            )

        if not all_scored:
            return BacktestResult(
                summary={"wmape": None, "bias": None, "coverage80": None, "skuCount": 0},
                fold_metrics=[],
                breakdowns=[],
            )

        combined = pd.concat(all_scored, ignore_index=True)
        headline = _aggregate_metrics(combined)
        headline["skuCount"] = int(len(combined))
        headline["coverage80"] = headline.pop("coverage_80")

        breakdowns: List[Dict[str, Any]] = []

        for model_type, grp in combined.groupby("model_type"):
            m = _aggregate_metrics(grp)
            breakdowns.append(
                {
                    "dimension": "model_type",
                    "dimension_value": str(model_type),
                    "wmape": m["wmape"],
                    "bias": m["bias"],
                    "coverage_80": m["coverage_80"],
                    "sku_count": len(grp),
                }
            )

        for famille, grp in combined.groupby("Famille"):
            m = _aggregate_metrics(grp)
            breakdowns.append(
                {
                    "dimension": "famille",
                    "dimension_value": str(famille),
                    "wmape": m["wmape"],
                    "bias": m["bias"],
                    "coverage_80": m["coverage_80"],
                    "sku_count": len(grp),
                }
            )

        summary = {
            "wmape": headline.get("wmape"),
            "bias": headline.get("bias"),
            "coverage80": headline.get("coverage80"),
            "skuCount": headline.get("skuCount"),
            "holdoutMonths": holdout,
            "foldCount": len(fold_metrics),
        }

        save_backtest_results(conn, holdout, summary, fold_metrics, breakdowns, run_id=run_id)

        return BacktestResult(
            summary=summary,
            fold_metrics=fold_metrics,
            breakdowns=breakdowns,
        )
    finally:
        if close_conn:
            conn.close()


def format_accuracy_api_payload(latest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Shape DB row into API response for GET /api/forecast/accuracy."""
    if not latest:
        return {
            "headline": {
                "wmape": None,
                "bias": None,
                "coverage80": None,
                "lastRunAt": None,
                "skuCount": 0,
            },
            "byModelType": [],
            "byCategory": [],
            "trend": [],
        }

    summary = latest.get("summary") or {}
    by_model = []
    by_category = []
    for row in latest.get("breakdown", []):
        item = {
            "wmape": row.get("wmape"),
            "bias": row.get("bias"),
            "coverage80": row.get("coverage80"),
            "skuCount": row.get("skuCount"),
        }
        if row.get("dimension") == "model_type":
            by_model.append({"modelType": row.get("dimensionValue"), **item})
        elif row.get("dimension") == "famille":
            by_category.append({"famille": row.get("dimensionValue"), **item})

    by_model.sort(key=lambda x: x.get("skuCount") or 0, reverse=True)
    by_category.sort(key=lambda x: x.get("skuCount") or 0, reverse=True)

    return {
        "headline": {
            "wmape": summary.get("wmape"),
            "bias": summary.get("bias"),
            "coverage80": summary.get("coverage80"),
            "lastRunAt": latest.get("completedAt"),
            "skuCount": summary.get("skuCount", 0),
        },
        "byModelType": by_model[:20],
        "byCategory": by_category[:20],
        "trend": [
            {
                "foldMonth": f.get("foldMonth"),
                "wmape": f.get("wmape"),
                "bias": f.get("bias"),
                "coverage80": f.get("coverage80"),
            }
            for f in latest.get("folds", [])
        ],
    }
