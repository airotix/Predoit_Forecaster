# Client requirements and delivery scope

**Project:** AI-driven order planning, budgeting and decision support system\
**Recorded:** 13 October 2026\
**Working brands:** Daytona 73 and Iron and Resin\
**Purpose:** A client requirements baseline and acceptance checklist. This document records requested deliverables; it does not certify that they have all been implemented or accepted.

**Current delivery clarification — 13 October 2026:** The user excluded management of other consignment stores from this delivery. Focus on Daytona 73 and Iron and Resin (the four approved brand codes), with CENTRAL as normal supplying warehouse. Consignment-specific workflows and acceptance checks below are deferred; their absence does not block this delivery. Retain warehouse ownership facts and keep secondary/faulty stock separate. Brand names are not warehouse codes.

## 1. Sources and authority

The client specification is visible in these two supplied screenshots:

- `C:/Users/FBC/Desktop/WhatsApp Image 2026-10-13 at 9.08.50 AM.jpeg`: project specification, sections 1–6.
- `C:/Users/FBC/Desktop/WhatsApp Image 2026-10-13 at 9.08.50 AM (1).jpeg`: sections 7–10.

The client’s brand/warehouse clarification supplied in this conversation is incorporated below. The screenshots and clarification establish the business requirements. Acceptance checks, implementation sequencing and proposed safeguards in this document are delivery interpretations that require client sign-off; they are not additional quotations from the client.

The current software review in [docs/DELIVERY_READINESS_2026-10-19.md](docs/DELIVERY_READINESS_2026-10-19.md) records implementation gaps as of 19 October 2026; the [12 October review](docs/DELIVERY_READINESS.md) is historical. These reviews are separate from the client's required scope.

## 2. Business context and objective

**REQ-01 — Business context.** The specification describes a B2B wholesale network of approximately 500 active retail doors. Orders arrive progressively during the selling season, while production decisions may be required when only 40–50% of customers have been visited. These figures are business context, not fixed database counts or automatic forecast multipliers.

**REQ-02 — Human-controlled decision support.** Analyze orders, stock, financial constraints and sales objectives; project future demand; recommend production/order quantities; explain the recommendations; allow users to adjust and validate decisions. The system is a decision-support tool, not an autonomous decision engine.

Acceptance: a buyer can trace a recommendation to source data and assumptions, modify it, inspect the resulting quantities and financial impact, and explicitly approve a version. A prediction alone does not place an order.

## 3. Confirmed brand, warehouse and ownership rules

**REQ-03 — Current brand scope.** Daytona 73 and Iron and Resin are the currently relevant brands. Most other brands are legacy or private-label activity. Preserve their records for traceability, but exclude them from the current planning scope unless a user deliberately selects another agreed plan.

On 13 October 2026, the user explicitly selected all four exported codes: `DAYTONA73`, `D73`, `IRON AND RESIN` and `IRON&RESIN`. Include each in current planning while preserving its original product identities. No alias/SKU merging is authorized by this selection.

**REQ-04 — Warehouse roles.** Apply the client-confirmed meanings:

- **CENTRAL:** primary warehouse for the company's normal inventory.
- **DESTOCK_VD:** secondary warehouse for end-of-life products.
- **DEFECTUEUX:** faulty products whose flaws prevent sale through standard channels.
- **Customer consignment virtual stores:** company-owned merchandise held at customer locations. Customers pay for what they sell and do not own the merchandise merely because it has been sent to them.

Delivery interpretation: report central sellable stock, end-of-life/clearance stock, faulty stock and consignment stock separately. Faulty stock cannot satisfy a standard sales replenishment recommendation. End-of-life stock requires a distinct clearance/lifecycle policy. Consignment inventory belongs in owned-inventory visibility, but availability for another customer's order depends on verified transfer/recovery rules.

**REQ-05 — Consignment demand (deferred, outside current delivery).** If added later, distinguish merchandise transfers into consignment from the customer's actual sales. Confirm relevant Joolan document/status mappings before calculating consignment demand or turnover. Prevent counting a transfer and the subsequent sale as two demand events.

Future acceptance only: a consignment shipment, partial customer sale, return and remaining balance reconcile by SKU and location. Current forecasting continues to disclose its booked wholesale order basis; it does not claim to measure consignment sell-through.

## 4. Mandatory inputs and source contract

**REQ-06 — Product inputs:** SKU identity; category; season; price; available sizes; product status (new, carry-over, core); historical units sold; historical buying-customer counts; historical size distribution.

**REQ-07 — Customer inputs:** customer ID; typology; geography; purchase history; reorder frequency; average basket; visited/not-visited status.

**REQ-08 — Supply-chain inputs:** physical stock; theoretical stock; work in progress; lead times; minimum order quantities (MOQs); industrial constraints.

**REQ-09 — Financial inputs:** supplier purchase price per SKU; currency; transport and duty costs where applicable; target margin; seasonal buying budget. Selling prices or an agreed sales-price assumption are also needed to calculate the requested expected turnover and margin.

**REQ-10 — Software data policy agreed in this conversation:** use newly exported Joolan API data as the operational source, save it in the software database, and keep source versions traceable. Previous CSV/workbook history is excluded from the current forecast workflow. Saved catalogue prices are permanent defaults for later forecasts and Budget Tracker calculations; budget simulation edits remain editable draft assumptions.

Delivery interpretation: maintain a field dictionary mapping each requirement to its actual Joolan table/endpoint, column, unit, tax/currency basis, status meaning and refresh time. Record unavailable fields explicitly. A missing value is not zero, and an order is not proof of a customer visit. If a mandatory field cannot be supplied by Joolan, agree an explicit supplemental input process with the client before representing that capability as complete.

Acceptance: identifiers, prices, quantities and dates reconcile to selected Joolan records; interrupted exports resume safely; incomplete data cannot replace a validated source without a visible decision; repeated imports do not duplicate demand.

## 5. Mandatory KPI deliverables

**REQ-11 — Sales KPIs:** total units sold; number of buying customers; diffusion rate; depth per customer.

**REQ-12 — Operational KPIs:** stock coverage; reorder rate; client coverage.

**REQ-13 — Financial KPIs:** purchase cost; expected turnover; gross margin; margin rate; budget consumption.

Delivery interpretation: agree the observation window and denominator for every metric. Specify whether units represent ordered, delivered, net sold or consignment sell-through quantities. Define diffusion against an eligible customer population, and depth against buying customers. Show ordering coverage separately from visit coverage. Define stock coverage against a forecast period or consumption rate and disclose unknown inputs. Distinguish repeat orders within a season from reorders across seasons if both are shown.

Acceptance: every KPI has a readable definition, source period and scope; a sample can be recalculated manually; changing brand, season or channel scope changes both numerator and denominator consistently.

## 6. Demand projection and size distribution

**REQ-14 — Non-visited customer projection.** Project demand from non-visited customers using statistical similarity/clustering with visited customers. The specification states that a SKU sold to many customers has a higher reorder probability than a SKU sold in large volume to a few customers.

Delivery interpretation: use actual visit status and agreed customer features; explain the relevant peer group and evidence. Customer ordering status cannot be substituted for visit status. Validate the specified relationship using observed reorder outcomes rather than displaying an unsupported probability. Distinguish this customer-based projection from aggregate time-series forecasting; an aggregate model alone does not fulfil this requirement.

**REQ-15 — Size distribution.** Analyze historical size sales, calculate size curves, correct distortions caused by stockouts, and apply configurable minimums, maximums and blocked-size rules.

Delivery interpretation: size curves operate by agreed article/colour/lifecycle grouping. Use stock availability evidence to distinguish zero sales from lack of stock. Preserve numeric, letter and one-size labels. Reconcile rounded size allocations to the article total and apply MOQ/pack/production constraints explicitly.

Acceptance: backtesting uses past-only information and agreed baseline comparisons. The system handles sparse/new products transparently. A size allocation example shows historical evidence, stockout adjustment, rules, rounding and final totals. Required inputs that are absent are disclosed rather than claimed as modelled.

## 7. Order recommendations

**REQ-16 — Recommendation content.** For each SKU, display total recommended quantity and size breakdown, with a split between confirmed orders, probable reorders and projected demand.

**REQ-17 — Three scenarios.** Provide conservative, base and optimistic scenarios.

**REQ-18 — Article navigation requested in this conversation.** Present articles containing colour groups, with size/SKU detail inside each colour. Keep quantity and pricing edits available at SKU level.

Delivery interpretation: define the time period and mutually exclusive components of the demand split. Explain how already confirmed orders are included so they are not added twice to a model that already predicts total demand. Distinguish forecast demand, production requirement and net purchase quantity after eligible stock/incoming supply. Scenario changes must update summaries and detail views consistently.

Acceptance: article, colour and size quantities reconcile; all three scenario calculations are traceable; historical confirmed/delivered quantities are not presented as future confirmed demand without a valid period mapping. Excluded recommendations have explicit reasons.

## 8. Mandatory finance and budget control

**REQ-19 — Financial integration for every recommended order.** Calculate total purchase cost from supplier prices; expected sales turnover; gross margin and margin rate; compare purchase cost with a predefined buying budget; alert when budget or margin objectives are not met.

**REQ-20 — Simulation and validation.** Users can simulate scenarios, adjust quantities or assumptions, and validate orders with full financial visibility.

**REQ-21 — Permanent catalogue prices requested in this conversation.** Store purchase and selling prices per SKU/currency. Display these as Budget Tracker defaults and retain editable budget assumptions. Preserve manually maintained catalogue values across source refreshes and forecast runs.

Proposed calculation contract, to be signed off:

- Purchase cost = ordered quantity × agreed unit purchase cost, plus applicable transport/duty costs under the agreed allocation method.
- Expected turnover = expected units sold × agreed net selling price. Expected sell-through is an explicit scenario assumption; ordered quantity does not guarantee sales.
- Gross margin = expected turnover − cost of goods expected to be sold, using the agreed landed-cost basis. Unsold purchased units remain inventory and still consume the buying budget.
- Margin rate = gross margin ÷ expected turnover × 100; disclose an undefined rate where turnover is zero.
- Budget consumption = agreed eligible supplier commitments + proposed purchases, with overlap rules preventing double counting.
- Remaining budget = seasonal buying budget − budget consumption.

Do not add costs twice if supplier unit cost already includes freight/duty. Keep different currencies separate unless verified exchange rates and their dates are available. Establish consistent VAT treatment. Clearly distinguish known subtotals from complete plan totals.

Acceptance: hand-worked order and partial-sell-through examples reconcile; changing quantities/prices updates cost, turnover, margin and budget alerts; articles included or excluded by budget allocation have readable reasons; incomplete required values prevent final approval rather than being treated as zero.

## 9. Explainability and human control

**REQ-22 — Readable explanations.** Every recommendation is justified by readable explanations and underlying KPIs.

**REQ-23 — Manual decisions.** Users can override, adjust and validate decisions manually.

Delivery interpretation: retain original recommendation, adjusted values, reason, actor, timestamp, season, scenario, source version and forecast version. Persist one order draft through recommendation, budget review and validation. Recalculate and check source revisions before approval. Specify whether final delivery produces a reviewed export or creates an ERP order; client approval of this interface is still required.

Acceptance: an approved/exported order uses exactly the reviewed quantities and financial assumptions; stale data or revisions cannot silently change it; the user can inspect saved drafts and review history. ERP submission must be an explicit, separately agreed action.

## 10. Required delivery packages

The screenshot explicitly requests functional specifications, POC, MVP, documentation and roadmap. The packages below organize those deliverables into reviewable outputs.

### D1 — Functional specifications

Deliver the signed requirements baseline; brand/channel/warehouse rules; Joolan field dictionary; KPI definitions; demand and financial calculation contract; buyer workflow; exception rules; and acceptance examples. Resolve the open decisions listed below.

Completion evidence: the client confirms definitions and scope, and each mandatory requirement REQ-01–REQ-23 is mapped to a delivery and acceptance check.

### D2 — Proof of concept (POC)

Demonstrate a representative Joolan data pipeline, customer/demand analysis, initial projection and size allocation, and finance/budget simulation on reconciled examples. Demonstrate human overrides and explain limitations. Evaluate the required non-visited customer method using real visit data when available.

Completion evidence: source reconciliation, reproducible calculations and an evaluation report comparing predictions with actual outcomes/baselines. A working dashboard alone is insufficient evidence of forecast accuracy.

### D3 — Minimum viable product (MVP)

Deliver the end-to-end buyer workflow: export/validate/activate source → scoped catalogue and prices → season/KPIs → demand scenarios and size allocation → durable editable order draft → financial/budget review → manual validation and agreed order output. Include the mandatory capabilities above; any deferred requirement needs an explicit client-approved exception rather than being silently removed from scope.

Completion evidence: buyer acceptance of a complete season example, consistent values across modules, edge-case tests and disclosed data/model limitations. The current software is a starting implementation, not proof that the MVP is accepted.

### D4 — Documentation and handover

Deliver a user guide, setup/install guide, Joolan permissions and mapping guide, calculation/model explanations, database and catalogue persistence notes, export/resume procedures, backup/restore instructions, troubleshooting and known limitations.

Completion evidence: a designated operator can install/run the agreed release, recover an interrupted import and restore a backup while preserving catalogue prices, seasons and approved/reviewed records.

### D5 — Roadmap and production release plan

Deliver prioritized remaining work with dependencies, owners, estimates and release acceptance gates. Include forecasting improvements, consignment reconciliation, supply constraints, unified drafts, performance, security/dependency upgrades, shared-user permissions and operational monitoring where required by the deployment model.

Completion evidence: the client agrees the POC/MVP/production milestones and any deferred scope. Delivery dates, hosting arrangements and service commitments are not yet agreed in the supplied material.

## 11. Success measures

**REQ-24 — Client-stated outcomes:** improved decision speed, margin control and reduced stock risk.

Agree baseline measurements and target thresholds before the pilot. Proposed measures:

- **Decision speed:** time required to prepare and review a seasonal article/order plan compared with the existing process.
- **Margin control:** visibility and compliance against the agreed gross-margin target; discrepancies between expected and realized margin where actual costs/sales are available.
- **Stock risk:** changes in stockouts, excess/end-of-life stock and unsold seasonal inventory, with comparable periods and channel scope.
- **Forecast support:** out-of-sample error/bias, performance against agreed baselines, and buyer usefulness by category/lifecycle. Do not advertise an accuracy percentage derived from a confidence badge.
- **Workflow reliability:** reconciled data, repeatable calculations, saved drafts/prices, successful recovery, and acceptable response times on the target installation.

These measures support acceptance; no numeric targets are invented here, and observed improvements must be distinguished from assumptions.

## 12. Open client/data decisions

1. Resolved for current inclusion: DAYTONA73, D73, IRON AND RESIN and IRON&RESIN. The four codes remain separate; any future alias consolidation needs its own mapping.
2. Deferred: exact consignment virtual-store list and customer/store associations.
3. Deferred: document mappings for consignment transfers, sales, billing and returns. Wholesale cancellations still require verification.
4. How CENTRAL availability/reservations and physical/theoretical stock should be defined. Recoverable consignment stock is outside current delivery.
5. Current product lifecycle classifications and clearance replenishment policy.
6. Source and dates of customer visits; eligible active-door definition; customer typology/geography and average basket definition. Reconcile the specification's approximate 500 doors with scoped database counts.
7. Verified wholesale selling tariff, purchase-price currency/tax basis, transport/duty allocation and currency conversion policy.
8. Supplier receipt dates, WIP, MOQ/pack constraints, lead times and industrial rules.
9. Forecast horizon, demand definition, success thresholds and agreed retrospective/pilot evaluation periods.
10. Final approval roles, order output/ERP interface, hosting, delivery dates and support expectations.

## 13. Current implementation gaps to track

Based on the 12 October review, the system has Joolan export/persistence, catalogue pricing, KPIs, aggregate demand scenarios, editable recommendations and budget simulation. The following remain material acceptance gaps:

- Stage 1 implemented on 13 October: persistent four-brand scope, primary-only normal supply, warehouse roles and forecast scope revision checks. See [docs/BUSINESS_SCOPE.md](docs/BUSINESS_SCOPE.md). Consignment-specific work is deferred by the subsequent scope clarification.
- Complete selling prices and stock/supply/financial reconciliation.
- Implement or verify actual visit-status inputs, customer similarity/non-visited projection and reorder-probability logic.
- Implement stockout-aware size curves and verified MOQ/production constraints.
- Stage 2 implements projection detail stock semantics, scenario propagation and actual size coverage; see [docs/PURCHASE_DRAFT.md](docs/PURCHASE_DRAFT.md).
- Stage 2 connects recommendation edits, budget planning and order review through saved versioned drafts. Financial review is local; production approval roles and ERP purchase-order output remain to be agreed.
- Stage 3 adds server env credentials and a date-only automatic workflow: fresh full Joolan extraction, schema/count/boundary reconciliation, quota/connection recovery, catalogue preparation and forecasting. Missing upstream data remains explicit. See [docs/AUTOMATIC_FORECAST.md](docs/AUTOMATIC_FORECAST.md).
- Validate forecast usefulness independently on the current scoped source.
- Complete deployment, security, performance, recovery and browser acceptance checks.

The status list is a delivery planning aid. It must be updated with dated evidence as work is completed; requirements are not marked delivered solely because a page exists.
