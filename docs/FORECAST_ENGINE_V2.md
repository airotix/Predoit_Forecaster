# Forecast engine v2: operating contract

This upgrade implements the six-stage improvement sequence. It is a shadow-tested demand-planning engine, not a certification of predictive accuracy or an autonomous purchase-order system.

## Data and dates

- The deployment uses the activated, validated Joolan generation. The legacy training CSV is not used by the deployment entry point.
- The four approved brand codes remain DAYTONA73, D73, IRON AND RESIN and IRON&RESIN. CENTRAL supplies normal orders. Clearance, faulty and consignment inventory are not pooled into CENTRAL.
- H26, FW27, P27, CORE and RECONDUIT are article attributes. They do not assign orders to a period. Booking demand uses the actual order date.
- Training stops at the last complete month in the source snapshot. A partial current month can contribute known bookings to the operational projection without being treated as a complete training month.
- Order booking dates and planned customer delivery dates have distinct roles. Missing or overdue open delivery commitments require reconciliation.

## Seasonal allocation

Open `/allocation` from Forecasting in the navigation. Choose one or more actual catalogue article season codes, including H26, FW27, P27, CORE and RECONDUIT, and a whole-month interval inside the published forecast. Apply the selection to see article totals, then open an article and colour for its size breakdown. Conservative, base and optimistic views use their corresponding saved monthly quantities. Quantities describe demand across all customers, not a selected customer's forecast or warehouse availability.

Save allocation stores this code/month selection against the active planning season. It does not retrain the model, change catalogue article codes, move order dates or modify the budget draft. Search and pagination preserve complete article breakdowns. Select a new forecast interval in Setup when dates fall outside the publication.

The page checks source generation, planning dates and business-scope revision before displaying quantities. Each variant must have every requested forecast month; missing or partial forecasts remain unknown, while a genuine zero remains zero. Covered subtotals are explicitly incomplete when some catalogue variants lack forecasts. Adding a season code does not manufacture predictions for never-ordered articles. The initial current-data check covered 9,923 of 19,629 variants across the five requested codes; 9,706 still needed estimates in the existing v1 publication.

## Forecasting and purchasing quantities

For each variant and month, the operational booking projection is the larger of the statistical prediction and known eligible booked units. Original model predictions are saved separately for evaluation. Bookings are not added a second time.

For purchasing, the remaining period requirement is:

`open customer deliveries due in the period + max(season booking projection - season booked units, 0)`

This includes orders booked earlier but due now. Delivered units already incorporated in the booking total are not purchased again. Additional unbooked forecast units explicitly assume supply is required within the planning period; they have no observed delivery appointment. Unknown delivery commitments remain unknown.

Net purchase need deducts known available stock and eligible scheduled supplier receipts. Budget Tracker retains the user's requested editable full-forecast quantity default, and shows net need separately. Prices and quantities can still be changed in the draft.

## Model selection, launches and uncertainty

Sparse and seasonal baselines compete with pooled CatBoost on an unseen selection window. Active histories retain more training capacity; dormant series do not consume an equal multi-year allocation. Product features include brand, category, material and collection where available.

An article-level baseline challenger must improve joint variant holdout error by at least 5%. Its colour/size allocations sum to the article forecast and use past-only shares.

New identities already observed in the as-of order book are included. New articles can use at least three active same-brand/category donor articles, with a material preference and pooled size curve. These estimates are uncalibrated, LOW confidence and require planner acknowledgement and a reason. Other new variants show known bookings only. Entirely unobserved future styles still require an explicit availability/launch contract; season codes alone are insufficient.

Monthly ranges use earlier held-out normalized residual pools when at least 30 comparable errors exist. Otherwise they are explicitly uncalibrated. Summing monthly bounds does not establish season-level interval coverage. MEDIUM confidence requires at least six earlier held-out points, WAPE no greater than 50%, and absolute bias no greater than 25%; all other cases remain LOW. These are evidence criteria, not probabilities.

## Prices, ordering constraints and review

Missing catalogue purchase costs may use confirmed/closed exact-variant supplier-order prices, after verified sequential discounts. The budget currency must match the recorded currency; no exchange rate is assumed. Latest conflicting quotes are excluded. Source generation, supplier, order, date, currency and calculation method are retained. Manual prices and explicitly cleared manual values remain protected. The agreed previous-season selling-price reference remains unchanged.

Configured pack multiples, variant minimums/maximums, article minimums, blocked variants and supplier lead times apply to order proposals and validation. Recorded product pack sizes require explicit verification. Forecast quantities are not rounded to pack sizes; proposed purchases are. Manual quantities remain editable, with violations displayed.

Missing MOQ, lead-time, transport, duty, cancellation and stock inputs are not invented. Unmapped landed charges are excluded from the displayed margin. Local financial review does not send orders to Joolan. The direct API enforces the same disabled approved-purchase-export policy as the page.

## Reproducible checks

From `backend-ai`:

```powershell
python -B -m unittest discover -s tests -v
python -B -u backtest.py --horizons 6 --folds 3 --iterations 250 --output output/engine-upgrade/full-six-month-backtest.json
python -B -u verify_engine_upgrade.py --target D:/Preduit-forecaster-verification/NEW-RUN/engine-v2.db
```

The verification target must be a new file, separate from the serving database. The runner takes a SQLite snapshot, runs the real pipeline there, checks quantity invariants and protected manual prices, and confirms that live publication remains unchanged. `--resume-snapshot` only accepts an interrupted snapshot that still has the same unpublished run as the live database.

Backtests read lineage and historical data in one read-only snapshot, include new variants in the denominator, report missing predictions, and compare practical baselines. Samples are explicitly labelled. Brand/category reporting and positive-demand error/coverage complement article and total-month metrics. Revised historical data are not proof of what the ERP contained at an earlier forecast origin. Operational booking adjustments and launch analogues need archived as-of snapshots for independent evaluation.

Each forecast run stores prediction CSVs, model selection, lineage, code hashes, dependency versions, a feature contract and a fitted CatBoost model when selected.

## Release boundary

Passing regression tests establishes calculation correctness, not forecast accuracy. Do not promote an engine merely because its code builds or its aggregate total looks plausible. Compare full-assortment held-out error, bias, positive-demand interval coverage and launch coverage with agreed business thresholds and practical baselines.

The completed full-assortment six-month evaluations had article season-total WAPE of 130.3% (April–September 2025), 146.7% (October 2025–March 2026) and 149.2% (April–September 2026). The latest fold's total bias was -6.6%, but this does not imply 93.4% accuracy: errors across articles cancel in the total. Positive-demand monthly band coverage was only 23.7% in that fold, and new variants without predictions accounted for 27,745 of 54,263 actual units. The baseline-only selector scored 152.5% article season-total WAPE versus 149.2% with CatBoost: this improvement is insufficient for production acceptance. A zero-demand forecast's 100% WAPE also underscores the need to control false demand on inactive articles, alongside serving real demand. This is a diagnostic comparison, not a recommendation to forecast zero.

These reports score statistical predictions over the full observed test universe. Operational booking floors and new launch analogues need archived as-of snapshots for independent scoring. Reports are in `backend-ai/output/engine-upgrade/full-six-month-backtest.json` and `baseline-period-control.json`; the current live v1 publication remains separate.

Before a production rollout: validate the upcoming assortment contract; archive point-in-time inputs and forecasts; reconcile missing costs, cancellations, stock and supply dates; verify supplier rules and landed charges; and run a buyer-reviewed shadow pilot measuring service, overstock and financial impact. Customer visit status is not inferred from absence of orders. A separate customer-adoption model and measured availability-based stockout correction remain future work.
