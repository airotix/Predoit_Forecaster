# Forecaster product and implementation plan

Prepared 5 October 2026 from the current working tree. This is a proposed roadmap, not an implementation or a promise of forecast accuracy. Confirmed first customer: Daytona 73. The user reports access to all Joolan data, but its column meanings have not been mapped. Begin with Daytona 73's actual buying workflow and verified schema before generalizing to other apparel brands.

## Product objective

Help a buyer decide what to buy, when it must arrive, what it costs, and which decisions require attention. Learn demand patterns from historical observations; take operational facts from Joolan. Every recommendation must identify its forecast version, ERP snapshot, policy version, and manual adjustments.

## Current implementation and gaps

- `backend-ai/forecasting.py` already implements monthly baselines and optional pooled CatBoost selected on past-only validation.
- `backend-ai/joolan.py:fetch_trade_rows` retrieves `negoce_entetes` and `negoce_lignes`. It does not retrieve a verified inventory or supplier-order source.
- The Joolan pipeline explicitly leaves stock, incoming quantity and price unknown. Separate uploaded planning inputs currently supply these values.
- `main.py` merges those inputs into historical rows, then publishes forecasts and recommendations together. Stock changes require another forecast run today.
- `m7_recommendations.py` treats available inventory as current stock plus incoming quantity, without arrival timing. `planning.py` uses those published values for final decisions.
- Existing tests and frontend build pass, but approval without lineage, shared SSE state, repeated locking, and stale frontend state need correction.
- The backend README reports a historical benchmark worse than predicting zero overall. That benchmark was not rerun for this plan; independent live-data evaluation is a prerequisite for accuracy claims.

## 1. Establish the Joolan data contract

Inventory discovery is the first dependency. With customer authorization, inspect the available read-only API schema and reconcile sample records against Joolan screens/exports. The connector's referenced Swagger page was inaccessible through the research tool, so inventory table names and field availability remain unverified.

First deliverable for Daytona 73: a data dictionary linking each planning concept to its exact Joolan table, column, join keys, units, date meaning, status filter and reconciliation example. The user does not need to know the column names in advance.

Proposed discovery procedure:

1. Confirm the Daytona 73 enseigne/account identifier. The app defaults to `legend73`; do not assume that identifier represents Daytona 73.
2. Try read-only schema metadata queries through the existing connector, subject to Joolan's query permissions:

```sql
SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;

SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_KEY
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

3. If schema metadata is unavailable, request the schema/data dictionary from Joolan support or use a schema export. Permission to read business data does not guarantee permission to read metadata.
4. Identify candidate inventory, product, supplier-order, shipment, receipt and price entities. Inspect small read-only samples and status distributions; column names alone are insufficient evidence.
5. Trace approximately 10 representative SKU variants against Joolan, including reserved stock, partial receipts, cancelled lines, multiple warehouses and zero stock. Verify join cardinality so product variants or quantities are not multiplied.
6. Obtain buyer confirmation of operational meanings, document mappings as configuration, and add reconciliation fixtures. Keep discovery bounded; a full database download is unnecessary.

Required business entities:

- Product variants: stable product/color/size identifiers, units, category, supplier, launch/discontinuation dates.
- Stock by warehouse: physical quantity, reserved/allocated quantity, blocked/damaged quantity, timestamp, and the exact meaning of any available-stock field.
- Customer order lines: stable line ID, creation date, required/promised shipment date, original quantity, delivered quantity, cancellations, remaining balance and status.
- Supplier order lines: original quantity, received quantity, cancelled quantity, outstanding quantity, expected receipt date and status.
- Receipts, shipments, returns and inventory adjustments: dated movements where accessible, with return disposition.
- Costs and prices: currency, tax basis, unit cost, supplier terms, effective dates and applicable selling price.
- Supplier policies: observed/entered lead times, minimum orders, pack multiples, order calendar and reliability.

Do not infer inaccessible values. Keep manual inputs as explicit, expiring exceptions with source, reason and author. Joolan facts take precedence unless an authorized override is intentionally applied.

Acceptance gate: SKU-level stock totals and outstanding order quantities reconcile to Joolan at the same timestamp. Define tolerances explicitly; quarantine unresolved mismatches and block approval for affected items.

## 2. Separate the data layers and run lifecycles

Recommended flow:

`Joolan -> versioned raw snapshots -> validated facts -> demand forecasts + current operational state -> replenishment plan -> buyer approval -> ERP-compatible export`

Suggested logical datasets: product_variants, order_lines, inventory_snapshots, supplier_order_lines, stock_movements, supplier_policies, forecast_runs, forecast_values, planning_runs, planning_lines and approval_records.

Use tenant/company, SKU variant and warehouse in operational keys. Preserve ERP line identifiers, revisions, sync timestamps and source coverage. Stage and validate a complete logical snapshot before publishing it. Use incremental ingestion only if stable IDs and update markers are verified; otherwise retain reconciled full snapshots.

Separate actions:

- Sync ERP: update current stock, commitments, prices and expected receipts.
- Generate demand forecast: use the approved history and registered model/configuration.
- Recalculate purchases: combine a forecast with the latest coherent ERP snapshot and policy settings.
- Approve: freeze the exact planning version and record the approving user.

Initial proposed cadence: operational sync nightly and on demand; forecasting weekly or after material history changes; purchase recalculation after each successful sync. Agree freshness limits with each pilot customer. No scheduler is being created by this plan.

## 3. Define the demand target before improving models

For replenishment, demand must be allocated to the period in which stock is needed. Monthly order-entry patterns alone cannot establish delivery-period demand. Capture requested/promised delivery dates where possible; otherwise label forecasts as order-intake forecasts and restrict timing claims.

For historical model features, use only information available at the forecast origin. Current stock is an operational input, not a historical training feature. Stock availability, prices, promotions and cancellations may be training features only when their dated history is reliable and reconstructed without future knowledge.

Distinguish a verified month with zero demand from an unobserved month. Record stockouts so low shipments are not automatically interpreted as low demand. Keep orders, shipments, returns and cancellations separate; define their effects on the selected target explicitly.

## 4. Make purchase calculations time-aware

Project stock by week or month:

`closing stock = opening usable stock + eligible receipts - planned demand`

Only count supplier receipts when they are expected to arrive and usable. Surface shortages before arrival and prioritize expedite/transfer decisions instead of allowing a later receipt to hide them. Use supplier lead time plus the review interval as the replenishment protection period, with validated safety stock or a demand quantile appropriate to the customer's service target.

Prevent double counting:

- If the forecast represents total demand, consume it with confirmed orders in the same SKU/location/time bucket; use a documented rule such as `max(total forecast, confirmed demand)` as an initial approximation.
- If the model predicts additional unbooked demand, add that to confirmed demand instead. These two forecast definitions cannot be mixed.
- Subtract reserved stock only for commitments excluded from the demand being deducted later. Reservations against orders already included in planned demand must not be subtracted twice.

Illustrative same-period calculation: total demand forecast 100, of which 40 units are booked; usable physical stock 50; eligible incoming stock 20; desired ending buffer 10. Purchase need is `100 + 10 - 50 - 20 = 40`. Do not add the booked 40 again. This example ignores within-period timing and assumes stock is not already net of the same reservations.

Apply minimum orders, pack multiples, supplier constraints and budget after calculating unconstrained need. Display both quantities and explain any remaining shortage. Prioritize constrained purchases by business impact and service requirements; do not silently cut all products by the same percentage.

## 5. Improve forecasting with evidence

Keep seasonal-naive, recent mean, intermittent TSB and zero demand as benchmarks. Compare the deployed approach with the customer's existing purchasing method as well.

Evaluate multiple chronological origins at the actual business horizon and lead time; reserve a final untouched future period. Use an outer evaluation period distinct from the inner model-selection period. Report MAE, WAPE where defined, bias and interval coverage by active/dormant status, category, demand volume, horizon and lifecycle. Evaluate products launched after the cutoff as a separate cold-start task, rather than omitting them.

Candidate improvements, promoted only if they help: category/color forecasts with validated size allocation, pooled CatBoost with reliable product and calendar features, product lifecycle handling, and new-product analogues selected without future data. Avoid beginning with a larger deep-learning model merely because it is more complex.

Tune policies with historical replay using stock/order snapshots available at each decision date. Measure shortages, fill rate, excess stock, inventory value and purchase-policy cost, not prediction error alone. Then validate prospectively in a pilot; replay cannot prove causal ROI where historical lost demand is unobserved.

Method reference: rolling-origin validation trains only on earlier observations and evaluates relevant multi-step horizons: https://otexts.com/fpp3/tscv.html

Acceptance gate: agree segment-specific forecasting and inventory-policy thresholds before evaluating the final holdout. Do not sell autonomous purchasing until those gates pass.

## 6. Build trust into the buyer workflow

Make each row answer: expected demand, booked demand, current usable stock, expected receipts by date, shortage date, recommended purchase, cost, uncertainty and reason for action.

Add warehouse filters, exception queues, dated stock projections, explicit unknown values, data freshness, source drill-down, override reasons and approval history. Freeze approved versions; invalidate or require reconfirmation when material stock/orders/policy inputs change. Use optimistic version checks so an approval cannot race with a recalculation.

Start with reviewed CSV exports compatible with the customer's ERP import. Add write-back only after confirming Joolan support, permissions and an idempotent submission/reconciliation design.

## 7. Package a saleable product

Start with a narrowly scoped assisted product for Joolan apparel buyers. Proposed value proposition: reduce spreadsheet preparation and help prevent avoidable stock shortages or excess purchases through explainable, reviewed recommendations. Treat this as a market hypothesis to test.

Pilot with 2–3 willing businesses. Agree a baseline, adoption measures and measurable outcomes before starting. Track buyer preparation time, recommendation acceptance, override causes, stock availability and excess inventory. Collect evidence across relevant buying cycles before making improvement claims.

Suggested commercial experiment: a paid onboarding/data-mapping fee plus a subscription scoped by company, warehouse count or active variants. Test willingness to pay against verified time savings and operational value; no price is recommended without customer interviews and support-cost estimates.

For an initial managed single-customer pilot, an isolated deployment can reduce migration scope. For shared SaaS, add authenticated users, roles, explicit tenant isolation, encrypted connector secrets, tenant-isolation tests, PostgreSQL, durable jobs, monitored syncs, backup restoration checks and per-tenant retention/export/deletion controls. Agree supported deployment, support expectations and data handling during onboarding.

Remove hardcoded `legend73` assumptions from tenant configuration. Centralize API access, split the large route module, align nullable types, pin reproducible dependencies and remove tracked dependency/generated artifacts in a separate reviewed cleanup.

## Proposed delivery sequence and release gates

1. Foundation and schema discovery: correct the four identified correctness defects, document quantity meanings, inventory fields and target demand. Gate: no approval without complete lineage; all subscribers refresh; Joolan facts reconcile.
2. Live Joolan replenishment MVP: sync stock and supplier orders; introduce operational snapshots and recalculation independent of training. Gate: one buyer can trace every purchase quantity to a dated source and reproduce it.
3. Forecast and policy validation: add better chronological evaluation, lifecycle handling, time-aware receipts and supplier constraints. Gate: untouched evaluation and prospective shadow operation meet agreed business thresholds.
4. Assisted commercial pilot: complete exception/approval/export workflows, onboarding and support procedures. Gate: buyer adoption and measured value justify a paid renewal.
5. Broader product release: choose isolated deployments or shared SaaS based on demand; implement the matching security, operations and billing requirements. Gate: tenant isolation, recovery, sync failure handling and approval concurrency have been verified.

Do not commit calendar estimates until source access, dataset size, delivery-date availability, warehouse complexity and engineering capacity are known. Weekly replenishment pilots may yield useful early evidence within weeks; seasonal-buying validation may require a full buying season.

## First implementation slice

Started: Setup now exposes a chunked historical CSV inspection and read-only Joolan schema discovery, with search and downloadable JSON metadata. The original CSV was inspected locally: 479,932 rows dated 2016-01-02 through 2026-02-26, 122 recorded months and zero invalid order dates. This establishes parsed date coverage only, not complete source coverage or validated demand. Live schema discovery still requires the customer's verified enseigne and API key in Setup. Actual inventory synchronization and combining historical/Joolan demand are not implemented yet; both depend on the verified mapping.

Build a read-only Joolan inventory/supplier-order adapter against verified fields, store a versioned operational snapshot, and expose a recalculation endpoint that reuses the existing demand forecast. Keep it behind reviewed exports. This addresses the user's requested stock/quantity split directly before changing the forecasting model.

Outstanding inputs: Daytona 73's verified enseigne and inventory/supplier-order schema; meaning of reservation/availability fields; delivery dates; supplier lead times; expected deployment model; acceptable data age; historical source coverage; Daytona 73's buying process and success measures.

### Implemented combined-history extension

Created `backend-ai/data/history.db` from the supplied CSV and the subsequently completed direct Joolan snapshot. It contains 479,932 CSV source rows plus 161,111 newer raw Joolan records (641,043 total source rows). 14,360 newer raw records are flagged for review; these are retained rather than silently removed. Customer-order forecast rows are a separate view populated only after type confirmation, avoiding duplication across orders, shipments and invoices.

Setup now provides a February 27, 2026 default start date, a local-current-date end date, selected-period server-side sync, persistent history build/summary, and a combined forecast-source option. The baseline remains authoritative through February 26. Refreshed Joolan scopes replace previous rows for that date/type; gap checks, scope-specific resumable downloads, and closed-month-only training are implemented. Older baseline-order revisions remain a separate reconciliation task.

A read-only January 1–February 26, 2026 comparison found 22,391 Joolan `COMMANDE` lines matching CSV date/customer/variant/quantity, versus 1,386 `BL EXPEDIE` and 271 `FACTURE` lines. This supports `COMMANDE` as the customer-order candidate; matching these attributes is not unique line identity. Since the user initially requested another type, automatic activation remains off and the UI allows explicit confirmation.

### Evidence from the saved Joolan export

Inspected `backend-ai/data/Joolan Trade Documents.xlsx` without changing it. Its report identifies enseigne `legend73`. The header export is count-verified (244,924 rows); line export is incomplete (566,000 of 2,741,625 rows) due to a connection failure/timeout. The derived trade sheet is therefore incomplete and must not replace a complete serving snapshot or establish demand coverage.

Verified column names, with business meanings still to reconcile:

- Header fields: `Entete`, `Magasin`, `Client`, `Nature`, `Date`, `Statut`, `Devise`, `Date_Livraison_Souhaitee`, `Date_Livraison_Prevue`.
- Line fields: `Ligne`, `Entete`, `Magasin`, `Client`, `Nature`, `Produit`, `Couleur`, `Taille`, `Quantite`, `Quantite_Livree`, `Prix_HT`, `Prix_HT_Devise`, `Ligne_BL`, `Ligne_Commande`, `Statut`.
- `COMMANDE` appears in the complete header document-type report (52,700 headers). It is a candidate for customer-order scope; the buyer must confirm classification.
- No explicit cancellation-quantity or physical-stock column appears in these two sheets. Do not derive either from an unverified status field. Stock and supplier orders require other verified Joolan entities.
- The derived Trade documents sheet omits the original `Ligne` ID, pricing and delivery-date columns. Future extraction should preserve the appropriate raw fields after their semantics and joins are verified.
