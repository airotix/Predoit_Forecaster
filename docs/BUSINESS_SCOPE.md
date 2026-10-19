# Business scope — implementation stage 1

Implemented 13 October 2026. The four codes DAYTONA73, D73, IRON AND RESIN and IRON&RESIN were explicitly selected by the user. They remain separate product codes; no SKU or article identities are merged.

## Persistent configuration

`planning_state.operating_scope` in the serving database stores selected brand codes, warehouse roles, revision and update time. The Business Scope page at `/scope` displays these choices and recorded per-warehouse physical/available balances for the selected brands. Balances are explicit-record subtotals; absent SKU records remain unknown.

The client-confirmed roles are enforced: CENTRAL is primary, DESTOCK_VD clearance/end-of-life, DEFECTUEUX faulty. Other codes initially remain unclassified. A user can classify exact customer virtual-store codes as consignment after obtaining the client's mapping. Unclassified locations are never automatically declared consignment or pooled into primary stock.

## Forecast and budget behavior

- The next forecast is built from the activated validated Joolan API source, filtered by the saved business brands. Historical CSVs are not used.
- Wholesale training excludes COMMANDE records whose header warehouse is classified clearance, faulty or consignment. Their raw source records are retained. This exclusion does not claim to identify customer-held consignment shipments originating from CENTRAL; customer/store and actual-sales mappings are still needed.
- Unclassified-channel order records remain in booked-order history with an explicit readiness warning. They are not certified wholesale sell-through. This is an interim treatment requiring the client's channel mapping.
- Stock in the pipeline and Budget Tracker comes from primary supply warehouses only. Saved global brands/primary warehouses override old season-level brand/warehouse selections. Other financial settings remain per season.
- Clearance/faulty stock and confirmed consignment balances remain visible separately on Business Scope; consignment stock is not available for normal dispatch by default.
- Saved scope revisions are recorded in forecast lineage. Serving endpoints reject old-scope insights until a matching forecast is published. Scope/source changes during a run prevent publication and preserve the previous result.
- Catalogue master records and manual prices remain permanent across forecast builds; the all-brand catalogue is retained for browsing.

## Verification

Tests cover protected roles, persistent revisions, budget consistency, exclusion of legacy brands and classified consignment orders, primary-only stock, retention of previous forecasts when the scope changes during publication, stale API guards and unknown/duplicate stock balances. After the financial-overlay fix, the full backend suite passed 179 tests; the frontend build passed.

The first full scoped rebuild exposed a pre-existing numeric dtype error when the financial overlay mixed known purchase quantities with unknown values. The overlay now coerces numeric quantities/prices safely and preserves undefined margin rates. A new focused regression and the 28 reliability tests passed after this fix. Failed runs preserve previously published data.

## Published result

Run `4e01630319e0442b88af786d4a18e9e9` completed on 13 October 2026. It publishes October 2026–March 2027 forecasts trained through September 2026, with 42,543 forecast variants across 4,326 articles. Verification found only the four agreed brands in the published article set; Budget Tracker settings use CENTRAL as the sole normal supplying warehouse. Current-stock values are explicitly available for 31,005 forecast variants; this does not establish complete incoming supply, financial inputs or purchasing approval.

The scoped ledger contains 603,166 source order lines and 1,898 customers. The run took approximately 14 minutes including source preparation, model calculations and publication; publication performance remains an open implementation gap.

## Remaining scope work

The user clarified on 13 October that management of other consignment stores is outside the current delivery. No consignment-store mapping is required to proceed with the Daytona 73 / Iron and Resin implementation. CENTRAL remains the normal supply source; DESTOCK_VD and DEFECTUEUX retain their separate roles. Existing raw records and ownership facts remain available, but this delivery does not implement consignment replenishment or claim consignment sell-through accuracy.

Lifecycle replenishment beyond separating clearance transactions, supplier lead times, purchase constraints, visit-based projections and size-curve correction are later implementation stages. The shared draft and projection changes are documented in [PURCHASE_DRAFT.md](PURCHASE_DRAFT.md).

The regenerated scope uses the existing activated API export through 7 October 2026; it is not a new live download. Current stock follows that export's recorded inventory timestamp. A new export is needed to update Joolan history and stock freshness.
