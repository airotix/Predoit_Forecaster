# Delivery review — 12 October 2026

> Historical review. See [the 19 October readiness review](DELIVERY_READINESS_2026-10-19.md) for the current runtime, approved brand scope, published v2 forecast and remaining delivery blockers.

## Verdict

Suitable for a supervised local pilot and demonstration, with demand forecasts and buying simulations explicitly treated as drafts. **Not ready for a production client handover or autonomous purchasing.** Passing tests establishes implementation checks, not forecast accuracy or complete financial data.

The review covered application source, saved Joolan data and forecast lineage, backend tests, frontend build/lint, live local HTTP routes, catalogue pricing, customer/KPI reconciliation, recommendation totals, budget simulation and export gates. All nine page routes responded successfully. Browser interaction, responsive layout, accessibility, fresh credentialed Joolan export, disaster recovery and multi-user load were not independently verified in this review. The live forecast was not retrained or replaced. Mutating price and forecast tests used isolated fixtures.

## What currently works

- Fresh Joolan export has durable progress and resume support; incomplete exports are not silently activated.
- Source and serving databases are separate. Forecast publication and failure rollback have regression coverage.
- The catalogue persists 132,177 current SKUs, with 114,385 purchase prices in EUR. Articles contain colours and sizes; manual prices survive source refresh and forecast table rebuilds.
- Customer coverage reconciled: 2,256 customers, 770 active in the defined observation period and 48 ordering this season through 7 October. Coverage means ordering activity, not visits.
- Product KPIs: 11,332 article/colour groups; rate bounds, filters and historical size totals passed. There are 4,705 groups with positive cross-season reorder rates.
- Recommendation demand, per-size quantities and purchase totals reconciled to the database. Unknown net purchase quantities remain unknown.
- Budget simulations support editable quantities/prices and whole-article allocation explanations. Catalogue defaults and simulation overrides are separate.
- Draft CSV download returned successfully. Empty financial-review selections and approved purchase export were rejected as intended.
- Serving database `PRAGMA quick_check` returned `ok`.

## Corrections made during this review

1. Order Validation no longer converts unresolved purchase quantities, cost, margin and budget usage into zero. It displays Unavailable instead.
2. Removed the invented `overrides + 36` SKU count and old default season name. The count now comes from the backend.
3. Removed misleading claims that downloading a CSV automatically sends orders to an ERP and locks the season. The approved-download button now respects the current deployment's disabled approval state.
4. Added visible validation load failures, retry/loading state and stale-response protection when scenario/season changes.
5. A price deliberately cleared in the catalogue now remains unknown when preparing future forecasts, even if an older planning input or source row has a price.
6. Validation reuses each scenario's calculated rows instead of reading/calculating them repeatedly.

Verification after fixes: **169 backend tests passed**; frontend production build passed; subsequent lint completed without warnings. Live validation returned the actual 54,158 variant count, null financial values and disabled approval. Invalid scenarios returned 400; approved export returned 409; draft export returned a nonempty CSV.

## Blockers and the work required

### 1. Establish Daytona 73's operating scope and reliable inputs

The active source includes **33 brands and 23 warehouses**, including brands outside Daytona 73. Training history spans February 2006 to October 2026, with training through September 2026. This is not a narrowly scoped Daytona 73 buying plan. A budget filter alone does not retrain or scope every insight page.

The source validation says `readyForForecast=true` and `readyForPurchasing=false`. It records 73,037 inventory rows, but no catalogue variant has a complete row across all 23 selected warehouses. It also reports 199,846 confirmed/closed lines without explicit partial-cancellation quantities. Missing warehouse rows cannot automatically mean zero.

**Work:** agree the Daytona brand codes and supplying warehouses with the buyer; verify available stock, reservations, supplier ordered/received/cancelled quantities and receipt dates against Joolan screens. Validate cancellation semantics and distinguish booked customer orders from net sales. Activate the intended scope and publish a new forecast. Keep all-brand catalogue browsing if useful, but make the planning scope consistent across pages.

**Acceptance:** reconcile a representative set of articles across colours/sizes and at least several real customer and supplier orders, including cancelled, partially delivered and overdue cases. Every purchase decision must have resolved required inputs or be explicitly excluded.

### 2. Complete catalogue prices and financial reconciliation

There are **zero usable selling prices in the saved EUR catalogue** under the selected tariff. The current Budget Tracker includes 4,291 positive-demand variants across 658 articles, with no variant ready for final validation.

The simulation reports a known proposed purchase subtotal of EUR 545,992.70 and known commitments of EUR 120,867.50 against EUR 555,555.50. Those known amounts already exceed the budget by EUR 111,304.70. Other inputs are incomplete; this is not a complete payable amount. The covered supplier subtotal includes 206 lines, while 5,366 lines are excluded by its eligibility rules.

**Work:** select the correct verified wholesale selling tariff or save approved selling prices in the catalogue. Resolve missing purchase prices and supplier identity/quotes. Reconcile outstanding commitments rather than treating excluded lines as free budget. Confirm tax and currency basis and agreed margin definition. Recalculate and review the resulting allocation with the buyer.

**Acceptance:** for each included purchase, quantity × unit cost, expected units sold × selling price, cost of sold units, gross margin and remaining allowance reconcile to a hand-worked example. No unknown values are counted as zero.

### 3. Prove forecasting value on the current Joolan source

The current published forecast is run `45e2cb0b896d4e9e8479ada39046e536`, October 2026–March 2027, trained through September 2026. It contains 54,158 variants and about 59,816 forecast units; 4,291 variants have positive demand. Current catalogue inputs differ from that publication's recorded inputs.

The saved accuracy report belongs to an **older combined CSV/Joolan run**, not this fresh-source forecast. It reported 167.95% variant-month WAPE and 42.49% aggregate monthly WAPE. Those figures cannot be presented as today's model accuracy, and `100 − WAPE` is not a valid general accuracy percentage. A Medium confidence badge currently reflects validation-history length, not a calibrated probability of correctness.

**Work:** run an independent, rolling historical evaluation on the agreed fresh Joolan scope. Compare seasonal-naive, recent-mean, intermittent and selected-model forecasts, including a zero baseline for sparse demand. Report bias and error by article, category, colour/size and new versus carry-over products. Prefer forecasting at a level with enough observations, then validate colour/size allocation. Add lifecycle and new-product handling; evaluate stockouts and wholesale order timing. Agree acceptable purchasing/business outcomes with Daytona 73 before choosing a release threshold.

**Acceptance:** repeatable results on held-out periods, better business performance than the agreed baseline and planner process, with clearly documented weak segments and manual review rules. Retain forecast versions and later compare them to actual outcomes.

### 4. Unify forecast, purchase plan and approval workflow

Budget Tracker edits are browser draft assumptions. SKU Recommendations saves separate per-season quantity overrides. Budget financial review records are a third local snapshot. Order Validation uses the recommendation path; it does not automatically submit the Budget Tracker's selected article plan. Fresh-source approved CSV export is deliberately disabled, and no Joolan purchase orders are created.

Demand Projection also needs a focused correction before handover: its detail endpoint always uses the base scenario, replaces missing stock with zero, mixes historical delivered units into a stock arithmetic summary, and the table fixes its columns to 11 letter sizes. Numeric/one-size variants can therefore be hidden. Its summary truncates fractional article forecasts. These are substantive remaining data-presentation issues; they were not silently reinterpreted during this audit.

**Work:** define one persisted order draft with season, scenario, source/forecast version, SKU quantities, supplier, price provenance and revision. Use it consistently for Budget Tracker, review and final export. Display saved review history and approval state. Require a revision check before approval. Correct projection detail semantics, preserve unknowns, show actual size labels and use the selected scenario throughout.

**Acceptance:** one buyer journey from forecast to edited budget draft to review to exported order, with identical quantities and financial values at every step; duplicate submission prevention and complete change history. First deliver an explicit reviewed CSV workflow; ERP order creation can be a separate integration milestone.

### 5. Performance and operational reliability

During concurrent live checks, lineage took 25.74 seconds, dashboard 46.99 seconds and validation 73.97 seconds. After removing redundant validation calculations, one isolated request took 8.02 seconds; these are different load conditions, not a controlled speedup measurement. The frontend sends large product/recommendation datasets and the backend repeatedly scans/constructs full price maps and recommendation rows.

**Work:** profile representative requests; add server-side filtering/pagination, indexed aggregates and revision-aware cached results; avoid recalculating full catalogue fingerprints on routine navigation. Move long calculations to durable jobs with progress, cancellation/recovery and measurable timeouts. Check concurrent edits and source changes during calculation/publication. Provide a production startup/service configuration instead of developer terminals.

**Acceptance:** agree and measure a page-response target on the client's machine (for example ordinary navigation under two seconds after warm-up), plus a separate budget calculation target. Verify crash/restart recovery and that failed jobs preserve the previous published run.

### 6. Security, deployment and recoverability

`npm audit --omit=dev --json` reported **11 affected package entries: one critical, nine high and one moderate**. The installed Next.js version is 14.2.35. Registry findings are dependency advisories, not proof that every issue is exploitable in this app. Some suggested remediation requires framework/tooling major upgrades, so this was not treated as a small automatic patch.

The backend currently restricts requests to localhost by default; its optional shared bearer secret does not implement user accounts/roles, and the browser API client/event stream does not implement that shared-token login flow. CORS origins and the default API URL are localhost-specific. Python dependency versions are not locked. A client deployment requires a tested configuration, not just binding the server to the network.

**Work:** upgrade affected dependencies in a dedicated compatibility pass and re-audit; lock tested Python dependencies; implement authenticated sessions and buyer/reviewer/admin permissions for shared deployment; configure HTTPS and trusted origins; protect stored commercial/customer data; add structured logs, monitoring and backup retention. Use a database backup mechanism that handles SQLite WAL consistently and test restoring both source and serving/master stores. A database migration is a capacity/concurrency decision, not mandatory solely because SQLite is used.

**Acceptance:** clean or explicitly risk-accepted dependency audit, successful login/permission tests, reproducible install, production smoke test and an actual restore drill recovering catalogue prices, seasons, drafts, forecasts and audit records. Add CI for backend tests/build and browser tests of the buyer journey, including mobile/keyboard and error states.

## Recommended delivery sequence

1. Correct Daytona scope and Joolan mappings; finish catalogue price and supplier reconciliation.
2. Fix projection semantics and connect all modules to one durable purchase draft.
3. Independently evaluate and improve the scoped forecasting approach; agree pilot acceptance criteria.
4. Upgrade dependencies, implement deployment/auth/backup operations, and address measured performance.
5. Conduct a supervised buyer pilot with signed-off data reconciliations, full workflow acceptance and forecast-versus-actual review. Production handover follows these checks.

No blanket readiness percentage is assigned: one unresolved data, security or purchase-approval blocker can prevent delivery even when most screens work.
