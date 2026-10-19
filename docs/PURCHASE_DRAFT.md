# Projection and shared purchase draft

Implemented 13 October 2026 for the current Joolan deployment.

## Buyer workflow

1. Open Demand Projection, choose a scenario, and expand an article. Every recorded colour and size is available, including numeric and one-size labels. Demand, available stock, incoming supply and net purchase quantity are distinct measures. Missing values remain unknown.
2. Open Budget Tracker. A new draft starts from the forecast rounded up per size. This is a buying assumption before inventory deductions, not a validated replenishment recommendation. Catalogue prices provide defaults; missing selling prices require input.
3. Edit article/colour/size quantities, purchase prices, selling prices and sell-through assumptions. Select articles for review. **Save & recalculate draft** persists the edits and selection. Save before leaving the page or switching scenarios; unsaved edits are not automatically persisted.
4. Saved recommendation quantity edits update this same draft. Locks prevent changing the corresponding article/colour assumptions from either screen. A stale draft must first be recalculated and saved in Budget Tracker.
5. Open Order Validation (page title: Order review). It loads the same draft and selection. Download a clearly labelled draft CSV or validate the saved version after financial checks pass. A local financial review does not create a supplier order or send anything to Joolan.

## Storage and consistency

- Database: `backend-ai/data/joolan_live.db`, persistent `planning_state` table.
- `purchase_draft:<context hash>` stores season, forecast run, source run, scope revision, scenario, version, explicit edits, selection and the resolved inputs from the last save.
- `purchase_draft:<context hash>:version:<n>` retains superseded saved versions. A newly published forecast uses a different context and does not overwrite the earlier draft.
- `buying_review:<id>` retains the financial review's source, draft version, selected rows, quantities, prices and financial results.
- Optimistic version checks reject stale saves from another page; writes run in a database transaction. Season/source/forecast guards remain active.
- Budget/price/source changes trigger a review warning. Explicit edits remain; removed variants are reported as excluded. A currency change clears old currency price/quote assumptions from the proposed new version rather than relabelling amounts.
- Recommendations show the last saved draft's quantities and resolved financial inputs; Budget Tracker previews recalculated values if prices/settings changed, and requires saving before review. Before any draft is saved, Recommendations still exposes its original net purchase calculation.
- Historical recommendation overrides seed an initial draft. Catalogue manual prices remain independent: editing a draft never changes the permanent catalogue.

## Calculation and projection changes

Purchase cost = order quantity × unit purchase cost. Expected turnover = order quantity × sell-through × selling price excluding VAT. Gross margin subtracts the purchase cost of units expected to sell; unsold units remain inventory. Money is rounded consistently with the budget calculations. Unknown inputs are not filled with zero.

Projection detail uses the selected scenario, retains fractional demand, includes actual sizes and returns 404 for an absent article / 400 for an invalid scenario. Stock plus incoming supply no longer subtracts historical delivered quantities. Recorded open order balances are labelled as source-history balances, not verified delivery commitments for the forecast period. Separate reorder and non-visited customer models remain unimplemented.

## Verification and limitations

Regression coverage includes persistence, scope/run/scenario separation, conflicts, locks, currency changes, rounding, explicit unknowns, immutable review snapshots, recommendation-to-budget edits, and projection sizes/scenarios. Verification passed: **193 backend tests**, the frontend production build including type/lint checks, and HTTP 200 responses for Projection, Budget, Recommendations and Order Validation. Live verification uses local HTTP and source inspection; interactive browser QA has not been performed in this environment.

The live check found 631 articles / 4,041 positive-demand variants in the buying view, 4,018 with known stock and no known selling prices. It uses the four approved brand codes and CENTRAL only. The initial draft request after backend restart took approximately 52 seconds: source loading remains a performance concern. No production quantities or prices were changed during the read-only check.

Missing selling prices, incomplete supplier commitments and other financial/supply checks still prevent purchase validation. This stage does not establish forecast accuracy, implement customer-visit clustering or production MOQ rules, provide multi-user authentication, or enable ERP purchase orders. Consignment-store management is outside the current delivery scope per the user's clarification.
