# Supplier purchase orders

Open **Buying → Purchase Orders** (`/purchase-orders`). This module creates editable, local supplier PO drafts. It never sends an order to Joolan or a supplier.

## Workflow

1. Publish the season forecast. In Budget Tracker, adjust the forecast-based quantities and prices and select the articles to order. Click **Create PO from selected articles**. This saves/recalculates the draft and creates the selected supplier PO drafts, then opens the PO editor. Missing inputs on unrelated recommendations do not block draft creation.
2. Alternatively, open Purchase Orders and choose **Only articles selected for review** (the default), **Only articles fitting the buying budget**, or **All positive budget draft quantities**, then click **Create supplier POs**. The all-quantity option is an explicit choice; it may include articles outside the budget allocation.
3. A separate PO is saved per supplier and native supplier currency. Assignment uses an explicitly selected supplier quote first, a traceable supplier-price source second, then an unambiguous catalogue supplier. Unknown suppliers remain unassigned for review.
4. Open a PO and expand **article → colour → size**. The original forecast and saved budget quantity remain visible beside the editable PO quantity. Select the supplier using the PO supplier dropdown. Edit purchase cost, selling price, sell-through, dates, delivery instructions and notes. Explain quantity/price amendments. **Save PO changes** retains an editable draft. **Save & send to Order Validation** saves the edits, marks the PO `pending_validation`, and opens its final review.
5. In **Order Validation**, review the PO totals and current source/budget checks. The approval budget includes active POs for the season/scenario and validated POs from other scenarios, plus current known Joolan commitments. It excludes recommendations that have never been turned into POs. Unknown commitments, missing required inputs, margin/quantity/rule failures and excess budget still block finalization.
6. Enter the reviewer name and reason, explicitly confirm the supplier, quantities, prices and totals, then **Validate & finalize PO**. The PO becomes immutable with a versioned approval snapshot. Download **final PO CSV** or **Print / save final PDF** here. Draft exports stay marked `DRAFT - NOT SENT`; final exports are marked `VALIDATED - NOT SENT`. Neither action transmits an order. Reviewer identity remains a user-entered local label until backend authentication is completed.

All-positive import includes articles left out of the budget allocation, with their original decision reasons. Use the budget-fitting option when you intend to restrict import to the allocator's included articles. Unknown prices and quantities remain unknown; draft generation is not financial approval.

## Financial scope

- Verified foreign supplier prices retain the native unit cost alongside the converted budget unit cost. Financial checks use the buying-budget currency; supplier CSV and print documents use the original supplier currency. Editing either price recalculates the other using the saved order rate. That historical rate is shown and does not promise a current settlement rate. Existing PO snapshots are not migrated or silently repriced.

- Purchase cost = ordered quantity × purchase price; expected turnover = quantity × expected sell-through × selling price excluding VAT.
- Gross margin subtracts the purchase cost of expected sold units. Unsold units remain inventory. Unmapped transport, duty and tax charges are not added.
- Final budget checks include active local POs for the same season/scenario and validated POs from other scenarios, across forecast publications. They use current Joolan commitments and settings, rather than the whole unselected Budget Tracker draft. Unknown commitment totals and conflicting budget currencies require reconciliation. This is not a real-time ERP commitment or cash-flow report.
- PO amendments update only the PO. Catalogue prices, the published forecast and Budget Tracker remain separate. Later source changes flag the saved PO for comparison instead of silently rewriting it.
- The current runtime's shared-host authentication/authorization migration remains separate; see [branch integration](BRANCH_INTEGRATION.md).

## Persistence and duplicate protection

The serving SQLite database (`backend-ai/data/joolan_live.db` by default) stores `supplier_purchase_orders`, `supplier_po_versions`, `supplier_po_claims` and `supplier_po_sequences`. These tables survive forecast publication.

PO numbers are allocated transactionally (`PO-YYYY-000001`). Saves require the current PO version and preserve the previous payload. Import claims prevent a variant being generated twice for the same forecast and scenario, including after a later budget draft version. Repeated import returns existing PO references. It does not overwrite edited POs or add quantity deltas automatically.

Cancelling an editable draft preserves its document/history, makes it read-only and releases its line claims. It also removes that document from active draft budget totals. A subsequent explicit import can create a replacement. Pending POs can be edited; saving returns them to draft and they must be submitted again. Validated POs are immutable and their claims are retained. Currency changes require cancellation/reconciliation of active drafts before new orders are generated in another currency.

## API

- `GET /api/purchase-orders?season_id=...&scenario=base`: saved summaries and supplier choices.
- `POST /api/purchase-orders`: create drafts from a matching, saved budget revision/version/forecast and selection mode.
- `GET /api/purchase-orders/{id}`: saved document, calculated finances, batch totals, checks and version history.
- `PUT /api/purchase-orders/{id}`: versioned amendments or cancellation; prices are finite/nonnegative and quantities are whole units or unknown.
- `GET /api/purchase-orders/{id}/export`: supplier-facing CSV text and filename. Formula-looking text cells are escaped.
- `POST /api/purchase-orders/{id}/submit`: version-checked transition to pending validation.
- `GET /api/purchase-orders/{id}/validation`: current source, financial and cumulative budget checks.
- `POST /api/purchase-orders/{id}/validate`: version-checked local finalization with reviewer, reason and explicit confirmation.
- `GET /api/purchase-orders/{id}/final-export`: final CSV, rejected until the PO is validated.

Local finalization records the buyer's financial review and unlocks the final document. It does not post an ERP purchase order, email a supplier or mark a document sent. Named-user backend authorization and any external submission remain separate delivery work.
