# Forecast engine review — 15 October 2026

Verdict: a working, recoverable demand-planning prototype, with useful forecasting safeguards, but its current quantities and confidence labels are not sufficient evidence for automatic purchase approval. Correct demand/order semantics and evaluation before replacing models.

This review reads the local `backend-ai` implementation and published Joolan-only run `89b7e4a1cff1442994ea9f6dec82c2c2`, exported source `e036a2ae0ad149669a2896c1309ba26f`. It does not review the different implementation on GitHub `main`. No training, source activation, published forecast or engine code was changed by this review.

## Current workflow and strengths

`automatic_forecast.execute` downloads and reconciles a fresh Joolan generation, validates joins and quantities, retains the agreed catalogue prices, then calls `main.run_phase1`. Failures can preserve the previous published source and season. These safeguards are improvements over the older manual workflow.

`m1_data_preparation` turns eligible Joolan ordered-minus-known-cancelled quantities into monthly demand by order creation date. `forecasting.forecast` produces one series per article/colour/size. It compares dormant-zero, intermittent, recent-mean and seasonal baselines with a pooled CatBoost model on a past-only holdout, refits where needed, and produces monthly scenarios. `m7_recommendations` adds order/stock context. `main` and `database` save lineage, prediction artifacts and an atomic serving publication.

Training ends September 2026; the current prediction period is October 2026–March 2027. Partial October observations are excluded from monthly training. The ledger covers February 2006–October 2026; that does not mean every model uses the full span. For example, the recent-mean baseline uses six months and CatBoost candidate rows come from up to 48 months.

Observed publication facts, not accuracy scores:

- 42,429 forecast variants; 59,184.489 base units.
- 38,456 variants (90.6%) have zero season forecast. Old and discontinued variants may legitimately be zero; lifecycle and upcoming-assortment checks are required before interpreting this percentage.
- 601 variants select CatBoost; 3,240 select recent mean; 37,875 select dormant zero. Recent mean contributes 47,442.711 units, about 80.2% of base demand. A simple model winning is not itself a defect.
- 3,140 variants have no model-selection validation window.
- All 39,289 variants with six validation points are labelled MEDIUM, regardless of measured error.
- Of 270 articles with positive bookings in the selected season, 90 have a season forecast below their booked units. Article 104864 has 90 booked units against a base forecast of 0.082 units.
- 44 of 1,366 variants booked in this season have no prediction row; they account for 82 booked units. Entirely unobserved future assortment is an additional, unmeasured exposure.

## Priority 1 — fix correctness and measurement

### 1. Closed balances are reconstructed as open orders

Evidence: `m7_recommendations.py:187` recomputes `max(CDE_qte - LIV_qte - ANN_qte, 0)` over all historical lines. `fresh_joolan.order_quantities` correctly sets the open remainder to zero for closed orders, but that validated `RELIQUAT_qte` is ignored by the recommendation calculation. Across raw closed lines, this reconstruction creates 282,258.6 units of apparent open balances even though their validated remaining quantity is zero. The recommendation aggregation also has no requested-season or delivery-window filter.

For the identical modelled variant universe, persisted `confirmed_orders` totals 328,461.6 units against 46,203 validated open units: the same 282,258.6-unit excess. These are all-history balances, not season-specific commitments.

Reproduction: an order with 10 ordered, 2 delivered, status closed and validated remainder zero becomes 8 confirmed units in `add_current_orders_and_stock`.

Change: consume the validated current balance, retain customer/order/status lineage, and filter commitments by their applicable delivery period. Keep historical booked sales, delivered units and current open commitments as separate measures.

Acceptance: closed/cancelled orders contribute zero open units; the same variant universe reconciles exactly to validated ERP open balances. Historical deliveries are not labelled as current-season commitments.

### 2. Full-season predictions can fall below known season bookings

Evidence: `main.py:61` excludes the incomplete month from training; `main.py:89` calls a historical-only model. `m7_recommendations.compute_net_to_order` subtracts inventory without updating the demand prediction for observed season bookings. The 90/270 article comparison above is a diagnostic of this inconsistency, not an out-of-sample accuracy score.

Change: keep the statistical forecast intact for evaluation and add a separately labelled operational season projection. Use eligible, cancellation-adjusted booked demand to date plus predicted additional bookings. Reconcile it to known demand once, avoiding both double-counting and subtraction of all historical deliveries from future demand.

Agree two separate targets: order-booking demand for sales planning, and delivery-period requirements for purchasing. Joolan order creation dates and requested/planned delivery dates can differ by several months. Do not silently move one target onto the other date axis.

Acceptance: a total eligible-booked-demand projection cannot be less than its known eligible bookings. Delivery requirements and available supply use consistent dates and allocation rules. Current-month adjustments never leak future observations into historical evaluation.

### 3. The standard backtest omits new variants

Evidence: `forecasting.py:159` loops only over prediction keys, so test-period variants absent from training are never scored. Synthetic reproduction: 6 units from a known item plus 600 units from a new item yield reported actual units of 6 and WAPE of 0%. The missing 600 units are omitted.

Change: outer-join predictions and actuals over the eligible test assortment; record missing predictions, new-item coverage and their missed units. Use independent rolling origins after model selection, at 1-, 3- and 6-month horizons, with per-brand/category/article/variant metrics, bias, positive-demand errors and cost/service outcomes. Score any operational order-book adjustment with only information available at that historical cutoff.

`audit_forecast.py:20` currently hardcodes the old `data/forecast.db`; this deployment serves `data/joolan_live.db`. Parameterize and verify database path, source generation and forecast run. The older October 7 review uses another source/universe and is not current accuracy evidence.

Acceptance: launch-only demand appears in the denominator and missing-forecast diagnostics; audit artifacts identify the exact data/run and outperform practical baselines on unseen periods. Software unit tests are not evidence of predictive accuracy.

## Priority 2 — improve the forecasting design

### 4. Forecast the planned assortment, including launches

`forecasting.calendar_series` builds histories only from observed variants. A catalogue entry with no pre-cutoff order history receives no forecast. Category, material, brand, collection, lifecycle, prices, customer penetration and visits are not present in `FEATURES`.

Introduce the eligible upcoming-season catalogue and launch/predecessor mappings. Separate carryover replenishment, returning seasonal lines, new styles and discontinued products. Test category/article forecasts with reconciled colour/size shares and analogue estimates for launches. Keep a review flag where evidence is weak; never fill every historical catalogue SKU with assumed demand.

Use customer segmentation, historical adoption and season order-taking progress where available. Visit/no-visit status must be mapped explicitly; no order does not establish that a customer has not been visited. Evaluate new features against the current baselines rather than assuming added complexity helps.

### 5. Improve sparse-series training and model selection

`forecasting.training_frame` divides a 200,000-row cap equally over all histories. At 42,429 series, an older series gets at most four sampled training targets, even though candidate history spans 48 months. A large dormant universe can therefore consume training capacity needed for active products. Independent size-level forecasts are also sparse.

Test lifecycle-aware training populations, category-shared models, recent/positive-demand-aware sampling with appropriate weights, richer product features and direct horizon-specific models. Compare against recursive prediction, existing intermittent/seasonal baselines and the planner process. Preserve calendar integrity and honest unseen launch tests.

The CatBoost loss is MAE. Choose the prediction target deliberately: a median-like point forecast for sparse demand can be near zero even when the expected total or inventory service target is positive. Test demand occurrence plus conditional size, appropriate count/continuous nonnegative objectives, and calibrated quantiles. Do not universally increase predictions or round every fractional expected demand up to one.

### 6. Replace heuristic confidence and scenario bands

`main.py:111` sets confidence from validation-point count alone. `forecasting.py:140` takes the 20th/80th percentiles of residuals from the same short interval that selected the winner. These are heuristic scenarios, not calibrated probabilities; their nominal quantile gap is not an 80% coverage claim. Summing monthly quantiles is not generally a calibrated season interval.

Use separate out-of-fold residuals or quantile models, calibration by horizon and product segment, and tests of interval coverage for positive-demand items and season totals. Display error, bias, validation dates, sample size and missing-assortment flags. Reserve a confidence label for a defined and measured criterion.

### 7. Improve size curves and inventory decisions

Current forecasts are generated independently for each observed size. The existing `size_had_stockout` flag in `m3_kpis.py:163` is a historical backorder-rate threshold; it is not observed inventory availability. Do not treat it as proven stockout correction.

Test pooled article/category size curves, exposure-aware availability history, assortment-specific allowed sizes and reconciled totals. Apply MOQ, pack multiples and blocked sizes in the order decision layer. Current stock and dated receipts should reduce purchase requirements, not suppress the underlying demand forecast. Missing costs, cancellations, supply dates and balances remain unknown and must block inappropriate approval.

## Priority 3 — make improvements measurable and repeatable

Persist fitted models, feature definitions, code revision, dependency versions, calibration artifacts and point-in-time data references alongside existing hashes and prediction files. Add frozen monthly forecast-versus-actual records and monitor errors, bias, missing forecasts, catalogue coverage and planner overrides. Archive source generations by capture time; a historical order date does not prove that the same status/value was known at an old forecast origin.

Avoid a larger model migration until corrected backtests show which business segments fail. Keep the current engine as the champion and compare replacements in shadow mode.

## Suggested implementation sequence and release gates

1. Correct open-order semantics and define booking versus delivery targets. Add a separately versioned projection that integrates current season bookings. Gate: exact balance reconciliation and no double-counting.
2. Repair and parameterize full-assortment backtests. Gate: reproducible metrics by horizon and business segment, explicitly including launches and missing forecasts.
3. Add lifecycle/launch handling and an article-to-colour-to-size challenger. Gate: demonstrated improvement over practical baselines on held-out seasons, including active and new articles.
4. Calibrate scenarios and confidence; connect demand to dated supply, pack rules and complete costs. Gate: measured coverage, explainable approvals and an agreed shadow-pilot inventory/service benefit.

No specific accuracy percentage or improvement is promised by this review. Agree acceptable bias, forecast skill, service level and overstock cost with Daytona 73 and Iron and Resin, then test those criteria independently.

## Verification and boundaries

Reviewed the active pipeline, Joolan validation/normalization, forecasting candidate selection, recommendation assembly, persisted outputs, backtest utilities, relevant KPIs and financial handoff. The 28 existing reliability tests passed. Two focused synthetic reproductions confirmed the closed-order and new-variant evaluation issues. Read-only SQL checked the current publication.

A new full historical accuracy evaluation of the current Joolan-only engine was not run in this review. The six-month future period is not yet complete. None of the publication statistics above is a percentage forecast accuracy.

Method references: [rolling-origin evaluation and prediction intervals](https://otexts.com/fpp3/toolbox.html), [hierarchical forecasting and reconciliation](https://otexts.com/fpp3/hierarchical-forecasting.html), [CatBoost regression objectives](https://catboost.ai/docs/en/concepts/loss-functions-regression).
