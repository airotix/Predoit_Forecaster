# Delivery readiness review — 19 October 2026

> Follow-up: the supplier selection and reviewed-price override mechanism from blocker 1 has now been implemented and tested on isolated data. See [Financial price review](FINANCIAL_PRICE_REVIEW.md) for the workflow and limits. The findings below preserve the audit snapshot; live input reconciliation and the other release gates remain outstanding.

## Verdict

**Ready for a supervised local pilot; not ready for production client handover.** The application has substantial working functionality, but its current buying workflow cannot complete financial validation, important inputs remain unresolved, forecast performance does not yet support a production accuracy claim, and the deployed runtime needs security and operational consolidation.

This review supersedes the current-state findings in the 12 October [delivery review](DELIVERY_READINESS.md). It assesses the [client requirements](../CLIENT_DELIVERABLES.md), including the later clarification that consignment-store management is outside this delivery. It does not impose autonomous ordering or consignment functionality as release requirements.

No business data, forecasts, exports, prices, statuses, purchase orders or drafts were changed during this review. Application code was not changed. The running local app was left available.

## Verified current state

- The live publication is `6607cd83dfb84acc8f6ab2ac8cedcb8d`, using engine `calendar-validation-v2` and fresh source export `b078409b17de4eeaaf147dfdc9e67e0f`.
- Source history runs through 19 October 2026. Statistical training stops at September 2026; the forecast covers October 2026–March 2027. Later eligible bookings are handled separately. These dates are not interchangeable.
- The four approved brand codes are DAYTONA73, D73, IRON AND RESIN and IRON&RESIN. CENTRAL is the normal warehouse; DESTOCK_VD and DEFECTUEUX have separate clearance/faulty roles. The old all-brand/all-warehouse review is no longer the current state.
- The automatic fresh export and forecast job completed today in approximately 49 minutes. Existing durable progress and resume support are valuable, but this duration is a background-workflow consideration, not a page response time.
- Current lineage reports no changed inputs, source generation, operating scope or history relative to the publication.
- There are 42,486 recommendation rows: 42,481 LOW confidence and 5 MEDIUM. These labels are not probabilities of being correct.

## What is already implemented

1. Fresh Joolan ingestion, saved raw/source records, resumable export, validation and controlled publication.
2. Scoped brand and warehouse planning, with secondary/faulty stock kept separate.
3. Persistent Catalogue purchase/selling prices, source provenance, initial Joolan activity flags and local active/inactive overrides. Inactive purchasing checks are implemented.
4. Customer coverage, original order articles with colour/size detail, product KPIs, demand projections, seasonal allocation and scenario recommendations.
5. Editable article → colour → size budget drafts, financial calculations, allocation explanations and review gates.
6. Editable local supplier PO drafts, supplier grouping, history/duplicate protection and CSV/print output. Creating or downloading a draft does not send an order to Joolan.
7. Source-aware caches, response compression, shared change notifications, stale-input detection and backend/frontend CI checks.

These features should be tested and completed, rather than replaced or listed as absent.

## Release blockers, in delivery order

### 1. Complete the financial review workflow

The current base draft contains 4,478 variants, including 4,433 positive-quantity variants. **Zero are ready for financial validation.** All 4,433 positive lines carry `Select a Joolan supplier price`.

This is partly a software workflow issue: `backend-ai/buying.py` requires a matching `quoteId`, while the rendered `ArticlePlanner` / `ColourPlanner` editor exposes quantity, purchase price, selling price and sell-through, but no supplier-quote selection. Accepting a traceable Catalogue price still does not satisfy that gate. Also, edited purchase or selling prices always add `Price assumptions are simulation only`; there is no completed buyer approval path for those assumptions.

**Required work:** expose supplier and source-price confirmation, clearly distinguish an order-backed price from an estimate, and implement an explicit reviewed-price override policy with reason, currency, actor and audit history. Preserve the user's ability to edit prices. A missing source must remain unknown until resolved or explicitly approved under the agreed policy.

**Acceptance:** on an isolated representative dataset, a buyer can open a recommendation, confirm supplier, edit a quantity/price, save, review all financial effects, approve eligible lines, create a PO and export it. Quantities, currency, costs and totals must reconcile across every step. Missing-data and over-budget cases must remain visible and follow the agreed approval rules.

### 2. Reconcile the inputs needed for purchasing

Current draft evidence, with denominators kept separate:

- Purchase costs are missing for **1,982 of 4,478 budget variants**; 1,964 positive lines carry the corresponding purchase-cost blocker.
- Selling prices are missing for **58 variants**.
- Explicit stock is missing for **20 budget variants**. The broader source warning of 68,605 missing-stock catalogue variants is a different population; it does not mean 68,605 current purchase lines are missing stock.
- Incoming supply is unresolved for **786 budget variants**.
- **1,500 positive draft variants** have customer delivery commitments needing reconciliation.
- Source validation says it is ready to forecast, but **not ready for purchasing**. Forecast readiness is not buying readiness.

Known proposed purchase cost is **EUR 468,520.61**, plus **EUR 120,994.68** in known existing commitments. Their known subtotal is **EUR 589,515.29**, exceeding the saved **EUR 555,555.50** budget by **EUR 33,959.79**. This is a partial calculation: full purchase cost, turnover, gross margin and final budget balance remain unknown because required inputs are missing. Do not present the subtotal as a complete payable amount.

**Required work:** reconcile active, in-scope articles against supplier orders and the supplying warehouse; confirm ordered/received/cancelled quantities and dates, reservations and whether old open supplier orders are genuinely outstanding. Validate cancellation semantics: 169,718 confirmed/closed source lines lack explicit partial-cancellation quantities. Booked demand is not certified net sales.

The current default order quantity deliberately starts from the full forecast, following the user's earlier request. Net purchasing need is separate. Before live buying, agree and label whether each PO is a gross demand plan or replenishment after usable stock and eligible receipts; do not silently switch policies.

**Acceptance:** every selected purchase line has a confirmed supplier, valid currency and usable price, agreed stock/receipt treatment, and explained quantities. Excluded/unresolved articles remain visible with reasons. The buyer approves the commitment and budget treatment.

### 3. Demonstrate forecast quality, not just successful execution

Saved six-month, three-origin backtests report article-period WAPE of approximately **130.3%, 146.7% and 149.2%** for Apr–Sep 2025, Oct 2025–Mar 2026 and Apr–Sep 2026. Latest variant-month WAPE is approximately **168.6%**; aggregate monthly WAPE is approximately **41.6%**. Aggregating demand hides substantial article/variant error.

These are saved evaluation results from an earlier source snapshot, not a new backtest of today's export. The current `forecasting.py` hash matches the saved backtest engine fingerprint. Historical snapshots can contain later revisions, and the current operational booking floor and launch handling still need independent, point-in-time evaluation. The latest saved positive-demand interval coverage is approximately 23.7%; summed monthly quantiles are not calibrated seasonal intervals.

There is no defensible single accuracy percentage for the current forecast. In particular, do not calculate accuracy as `100 - WAPE`.

**Required work:** agree a target and horizon, then evaluate rolling 1-, 3- and 6-month origins using data actually available at each decision date. Report article/category/variant WAPE, bias, launch coverage, interval coverage and business outcomes. Compare against seasonal/recent baselines and the buyer's current method. Treat active/new/core articles separately and account for discontinuations and sparse demand. Calibrate uncertainty on independent holdouts.

**Acceptance:** the client agrees measurable tolerance for bias, service level, overstock and decision usefulness, and the model meets those goals on unseen periods. Do not promise an arbitrary 90–95% accuracy target.

### 4. Finish the client's remaining demand and production requirements

- **Visited/non-visited customer projection:** the current customer page measures ordering activity. Actual visit status and customer-similarity projection required by the brief are not implemented end to end. An aggregate article time-series forecast is not a substitute for this requirement.
- **Upcoming assortment:** article season filters exist, but cannot create evidence for products never observed in orders. Current publication has 57 new variants, with only 1 using an analogue and 56 relying on bookings. Establish an explicit launch assortment, analogue/manual review and launch-demand evaluation.
- **Size curves and stock-outs:** historical size logic exists, but historical availability is not sufficiently established for verified stock-out distortion correction. Open/backorder proxies should not be described as observed stock-outs.
- **Industrial/landed-cost inputs:** the system supports configurable ordering rules, but the current budget has zero configured rules. Validate/map actual MOQ, pack, lead time, blocked-size/max rules, WIP and freight/duty where applicable. Raw source columns are not equivalent to validated business inputs.

**Acceptance:** implement these requirements with confirmed source mappings, or obtain explicit client agreement to a smaller MVP and document the deferred scope. The already-deferred consignment workflow need not be added back.

### 5. Secure and consolidate the production runtime

- The current `backend-ai` service uses localhost restrictions and an optional shared static token. The frontend's MSAL login/role filtering does not provide named-user backend authorization. Current `/api/auth/config` and `/api/auth/me` are not implemented by this runtime.
- The root Dockerfile starts the older `preduit_app.api_server:app`, rather than the service serving the fresh Joolan, Catalogue, Budget and PO workflows. Authentication in that other package does not secure today's service automatically.
- Current `npm audit --omit=dev` reports **11 affected dependency entries: 1 critical, 9 high and 1 moderate**. This includes Next.js 14.2.35. An advisory is not proof every vulnerability is reachable, but supported-version upgrades and exposure review are required before deployment.
- Python dependencies are not frozen to a reproducible release runtime. The working branch has substantial uncommitted functionality, so the checked working tree is not yet a reviewed, reproducible release artifact.

**Required work:** choose one canonical runtime; wire named authentication, server-enforced permissions and audit identity; match Docker, proxy, environment settings and startup instructions to it. Upgrade affected dependencies with compatibility tests, pin the supported runtime and produce a reviewed release/CI result. Keep credentials server-side.

**Acceptance:** a clean machine/container starts the same app; unauthorized API reads/writes are rejected; buyer/admin permissions are enforced by the backend; current endpoints and data volumes work through the intended production URL.

### 6. Prove operational handover and the real buyer journey

The serving and source databases are separate (`backend-ai/data/joolan_live.db` and `joolan_source.db`). The source database is approximately 2.2 GB. Older backup helpers/documentation for a packaged single-database runtime do not demonstrate recovery of this current workflow.

**Required work:** back up both databases consistently with SQLite/WAL handling, retention and a real restore test covering source generation, prices, statuses, drafts, reviews and POs. Add job-failure/run monitoring and an operator recovery runbook. Reconcile the two Quick Start documents and release branch references. Test browser navigation, keyboard/accessibility, responsive layout, concurrent buyers and the complete forecast-to-PO workflow. Agree whether handover means a reviewed CSV/PDF or an actual ERP submission; automatic Joolan order creation is not assumed to be mandatory.

**Acceptance:** a second operator installs from the release, restores a backup, resumes a failed export, runs a forecast and completes an approved purchase workflow without developer intervention or duplicate ordering.

## Performance and verification evidence

- **317 backend tests passed** in this review. Frontend production build, lint and 13 frontend tests passed immediately before this read-only review against the same application code. Passing tests are not a forecast-accuracy certificate.
- All **15 tested page shells** and **22 valid read-only APIs** returned HTTP 200. HTML success does not verify browser interaction, visual layout, accessibility or authorization under production settings. A separate probe of `/api/allocation` returned 404 because it is not an app route; the actual `/api/seasonal-allocation?scenario=base` returned 200.
- Serving database `PRAGMA quick_check` returned `ok`; this is not a restore test.
- First-observed local response times: Budget draft 13.612 s, recommendations 8.666 s, seasonal allocation 7.599 s and dashboard 4.406 s. Repeating the same cached routes returned approximately 0.043 s, 0.073 s, 0.006 s and 0.053 s respectively. An unparameterized recommendation request had a separate approximately 8.8 s initial computation. These measurements are individual API requests, not browser paint times, p95 measurements or a load test.
- Budget and recommendation payloads contain approximately **21.3 MB and 17.1 MB of decoded JSON**, respectively. Compression and caches help, but pagination, summary/detail endpoints and reduced first-request computation remain worthwhile. Measure user-visible performance on the intended client machine and under concurrent use.

Evidence JSON and the backend test log are saved locally under `backend-ai/output/readiness-2026-10-19/`. These files are ignored runtime evidence, not portable release fixtures. Saved forecast evaluations are under `backend-ai/output/engine-upgrade/`. Relevant implementation references include `backend-ai/buying.py`, `backend-ai/product_routes.py`, `frontend/src/components/budget/ColourPlanner.tsx`, the root `Dockerfile`, `.github/workflows/ci.yml`, and [branch integration notes](BRANCH_INTEGRATION.md).

## Recommended next delivery slice

First complete supplier/price confirmation and approved override handling, together with the in-scope missing-cost reconciliation. Then run one fully reconciled article through the complete financial review and PO journey. In parallel with subsequent delivery work, establish the forecast acceptance benchmark. Finish the agreed client requirements, secure the single production runtime, and pass clean-install/restore/browser acceptance before calling the system production ready.

## Step 2 follow-up — purchasing input reconciliation

The implementation now exposes `/budget/reconciliation`, source-specific missing
input reasons and reviewable historical supplier alternatives. Verified recorded
USD order rates supply traceable EUR planning costs; supplier POs and their
CSV/print documents preserve native currency. Overdue receipts are checked against
the export cutoff. Missing values remain unknown and existing snapshots survive.

On this plan, 718 missing purchase costs were recovered and 244 existing prices
updated. Nine inconsistent broader fallbacks were withdrawn, leaving 1,273
unresolved costs across 4,478 budget variants. This completes the implementation
slice, not source-data reconciliation or delivery acceptance. Supplier, stock,
receipt and delivery issues still require business/source resolution. See
[the reconciliation workflow and verification results](PURCHASING_INPUT_RECONCILIATION.md).

## Recheck after steps 1 and 2

**Verdict remains: suitable for a supervised local pilot, not production handover.**
This recheck used the running app after activation of the recorded-order FX policy.
No live draft, price, forecast, review, PO or Joolan record was edited or approved.
The existing publication and source export remain the ones listed above.

### Checks repeated

- 345 backend tests and 16 frontend tests passed. TypeScript and lint passed.
  The production build passed in the immediately preceding implementation turn;
  this recheck did not interrupt the app to repeat that unchanged build.
- All 15 main page shells and 22 read-only API routes returned HTTP 200.
  Browser spot checks verified the loaded reconciliation, article/colour Budget
  editor, supplier PO handoff and Product KPI page. Reorder rates are populated
  (for example, 67.9% for article 101126 / DARK COGNAC); no earlier runtime overlay
  appeared in those checked views. This is not exhaustive browser acceptance.
- The serving database's SQLite quick check returned `ok`. This is not a backup
  restore exercise. The automatic job remains complete.
- Current-season base draft version is 0, with no saved supplier POs or price/
  buying-review records. No live financial journey has been completed yet.

### Current purchasing blockers

There are 4,478 budget variants, with 4,433 positive quantities. Missing source/
Catalogue costs remain 1,273; 1,259 of those affect positive draft lines. Missing
selling prices: 58; stock: 20; incoming supply: 819; customer-delivery review:
1,510 variants (1,500 positive). These groups overlap.

All 4,433 positive lines still need supplier selection/confirmation. 3,535 have
at least one available source-price option; availability is not buyer acceptance.
The implemented controls now allow this work, so this is no longer the missing
supplier-selector bug described in the original snapshot.

Known draft order cost is EUR 597,293.32 and known existing commitments are
EUR 306,462.24. Their known sum is EUR 903,755.56, EUR 348,200.06 above the saved
EUR 555,555.50 budget. These are partial amounts, not a complete payable total;
full turnover, margin and final balance remain unknown. Historical FX is a
planning assumption and historical open commitments still need reconciliation.

**Next purchasing work:** resolve active/in-scope supplier, price, stock and
receipt issues; save and confirm a deliberate buying subset; reconcile old open
commitments; agree whether quantities represent gross forecast demand or net new
buying after usable stock and eligible receipts. Defaults currently use gross
forecast quantities. Validation applies whole-draft checks, so selecting one
complete article does not bypass unresolved or over-budget lines elsewhere.
Either complete/reduce the full draft or agree and implement a separately scoped
approval policy with cumulative budget protection. Do not simply remove gates.

### Remaining release work

1. **Forecast quality:** no model change or new backtest occurred during the price
   work. The current `forecasting.py` fingerprint still matches the saved six-month
   evaluation. Latest saved article-period WAPE is 149.2%, variant-month WAPE
   168.6%, and aggregate-month WAPE 41.6%. These are earlier-snapshot results, not
   a newly measured accuracy percentage for today's publication. Establish rolling
   holdouts, baseline comparisons, launch treatment and calibrated uncertainty.
2. **Client scope:** actual customer visit status and similarity-based projection
   remain incomplete. Finish new-assortment treatment and size/availability
   validation. There are still zero configured ordering-rule entries; map and
   validate the applicable MOQ, packs, lead times and landed costs. Consignment
   management remains outside the agreed scope.
3. **Runtime/security:** named backend identity/roles and authenticated review
   identity remain incomplete. The root Dockerfile still starts the other API
   package. A fresh production-dependency audit again reports 11 affected entries:
   1 critical, 9 high, 1 moderate. Review exposure, upgrade/test dependencies and
   release one reproducible canonical runtime.
4. **Operations:** demonstrate recovery of both current databases, failed-job
   recovery, concurrent-buyer/version handling and a clean-machine installation.
   Complete a representative real buyer browser journey through local PO export
   without approving or sending test purchases against live data.
5. **Performance and UI:** first-observed API requests in this recheck included
   customer coverage 17.9 s, recommendations 10.5 s, dashboard 6.8 s and allocation
   6.0 s. Cached repeats were much faster; these are not controlled cold-start or
   p95 measurements. The decoded budget draft is now 28.7 MB. Add summary/detail
   pagination and measure browser usability under concurrent use. The freshness
   banner includes financial-price changes in the same fingerprint as other
   inputs; distinguish financial refresh from demand-model rerun requirements.
   The reconciliation subpage also inherits an incorrect first-step footer
   (`Connect your data`) because its nested route has no navigation match.

Read-only evidence is under `backend-ai/output/recheck-2026-10-19/`; the test log
is `backend-ai/output/recheck-tests-2026-10-19.log`. These ignored local files
include actual timing/status results, the dependency audit and workflow counts.

## Subsequent workflow change — PO before final validation

Budget Tracker now saves selected articles and opens their editable supplier POs.
The PO editor supports supplier selection and submission to Order Validation.
Finalization checks the actual POs, current source inputs and cumulative season
budget, rather than all unselected forecast recommendations. Approval is versioned,
records explicit supplier/price/quantity confirmation and locks the local document;
final CSV/print output is available only after validation. Draft exports remain
clearly labelled. This implements the requested ordering of screens; it does not
resolve the source-data gaps, named-user identity or forecast-quality blockers
recorded above. No live PO was finalized while testing this change.
