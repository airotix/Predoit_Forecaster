# Supplier selection and financial price confirmation

> Workflow update: the current UI follows **Budget Tracker → supplier PO → Order
> Validation → final download**. Supplier selection and final price confirmation
> now happen on the PO and its validation page. The older Budget review APIs
> described below remain for compatibility; Budget Tracker no longer requires
> whole-draft validation before creating selected PO drafts. See
> [the current PO workflow](PURCHASE_ORDERS.md).

Implemented as the first follow-up to the 19 October delivery review. This completes the missing supplier-price selection and reviewed-override mechanism. It does not certify source completeness, forecast quality or production authentication.

## Buyer workflow

1. Open **Budget Tracker**, expand an article, then a colour.
2. Select a supplier-order price for each size. Options show supplier, order, date and the unit cost in the buying currency. **Use saved supplier-order prices for this article** applies the latest usable Catalogue order evidence where available, otherwise an available season supplier-order price. These are historical transaction prices, not new quotations.
3. Edit quantities, purchase prices, selling prices and sell-through as needed. The article-level reason control remains available for planning adjustments. Selecting a historical price records the standard source-confirmation reason automatically.
4. If using a negotiated/manual price without a usable order price, select a supplier under **Supplier for a reviewed price override** and enter both prices. Suppliers come from saved Joolan records; no supplier is invented.
5. Select the article for financial review and **Save & recalculate draft**.
6. Where edited/manual prices need confirmation, the selected-article panel shows **Confirm supplier and edited prices**. Enter the reviewer name and the reason for accepting those supplier prices, then confirm the exact saved values.
7. Resolve the remaining stock, receipt, delivery, launch, industrial-rule, budget and margin checks. **Validate selected articles** saves the financial review snapshot only when all applicable checks pass. Global whole-draft budget/completeness checks still apply.
8. Open **Purchase orders** to copy the saved plan into editable supplier PO drafts, then download the draft CSV or print it. No Joolan write or supplier communication occurs.

## Evidence and persistence

- Latest usable historical supplier-order evidence from Catalogue is selectable even when its order is outside the season's commitment period. It is not added to current commitments merely because its price is reused.
- Supplier choices use content-based identities containing the supplier, document, variant association, date, cost and currency. They do not depend on the ledger row position. Legacy positional selections are read for compatibility and new saves use stable identities.
- Choosing a quote replaces an earlier explicit cost override with that quote's price, including when the buyer selects the same quote again. Existing archived drafts retain their original values.
- Manual prices remain draft assumptions until explicitly confirmed. A confirmation is bound to the current calculation revision, buying currency, variant, supplier, selected price source and exact purchase/selling values. Different values, supplier, currency or source/settings cannot reuse it. A matching earlier confirmation can still describe exactly the same previously accepted values.
- Records are persisted in the serving database's `planning_state` under `price_review:<context hash>:<record id>`. They include immutable values, source labels, reviewer label, reason, server timestamp and saved draft version. Context includes the forecast run, source run, season, scope and scenario. They survive forecast-table rebuilds and do not overwrite Catalogue prices or Joolan records.
- The financial review and resulting PO retain the price-confirmation metadata. Later PO-only price or supplier changes invalidate its current confirmation display and retain the originating budget confirmation separately, with a warning. PO files remain drafts.
- Reviewer names are **user-entered local labels**, not authenticated identities. Named login, server-side roles and trusted approval identities remain part of the separate production-security workstream.

## API

`POST /api/budget/draft/prices/review` accepts `scenario`, `version`, `forecastRun`, `revision`, `selected` variant IDs, `reviewer` and `reason`. It requires a saved, non-stale, matching draft and finite prices, positive quantities and a selected supplier. It validates the complete request before writing and returns the updated draft. A caller cannot self-approve by adding an approval field to draft edits.

Price confirmation never removes financial/data/rule blockers. Missing values remain unknown, and price confirmation does not authorize overspending, low margin, inactive products or unknown stock. The existing full-forecast quantity default is preserved.

## Verification

Isolated API/database regression tests cover saving edited prices, rejection before confirmation, confirmation, financial review, PO creation and CSV reconciliation. They also cover stable quote IDs, historical evidence outside the commitment period, manual suppliers without quotes, stale versions, missing values, forged approval fields, supplier/currency/source changes, archived values, PO amendments and continued stock/budget/margin blocking. No live price confirmation or purchase order was created as part of these tests.

Verification on 19 October: **330 backend tests and 16 frontend tests passed; lint and the production build passed.** The updated local Budget page and health API returned 200. A read-only check found historical supplier-order choices for **2,496 of 4,478 budget variants**, with no choices in a different currency. An in-memory source-selection check for article 100233 used supplier AR YOUSAF at EUR 58.55 for the checked variant and cleared its supplier-price blocker. This did not save a live draft or waive global budget/data checks. The published forecast remained `6607cd83dfb84acc8f6ab2ac8cedcb8d` and the current live draft remained unsaved (version 0).
