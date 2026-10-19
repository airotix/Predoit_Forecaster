# Budget tracker

Open `http://localhost:3000/budget`. The page uses the published demand forecast
and the active fresh Joolan source. It does not reuse the previous historical CSV.

## Configure the season

Enter the purchasing budget, target gross margin and currency, then save them.
The existing zero values remain draft defaults until explicitly saved. A zero
budget can be deliberately saved; usage percentages require a positive limit.
Budget and mapping changes do not retrain demand. Changing the planning dates or
season still requires a forecast for the selected planning period.

Under financial mappings, select the brands and supplying warehouses. The default
budget scope is DAYTONA73 and CENTRAL. Other brands, defective and retail stocks
are not pooled into that scope by default. These are filters on the saved export;
another full export is unnecessary to change this budget view.

Select the cost basis and selling tariff, confirm their currencies and the actual
price/discount meanings. Current SKU prices use Prix_Achat less Remise_Achat.
Prix_Achat_Moyen is an optional weighted-average planning proxy. Zero price
placeholders are unpriced, rather than assumed to represent free products.
The selling tariff's HT flag and the product's numeric Taux_TVA_Vente determine
the price before VAT. Country-specific tax overrides and inherited tariff rules
are not inferred; use verified applicable prices for the chosen business scope.

## Currency references

The currency lookup requires an api_query-enabled key entered in the password
field. It downloads only the small devises reference table, checks its row count
and saves it against the active export with a capture timestamp. Keys remain in
memory and are not saved. Existing source datasets are preserved.

Codes such as 01 and 02 are resolved only from Joolan's reference records.
Cross-currency values are displayed separately. No exchange-rate direction or
conversion is assumed. Prices not verified in the budget currency remain unknown.

## Calculations

Proposed purchase quantity = maximum of forecast minus selected available stock
minus eligible outstanding supplier quantities, and zero. A saved scenario/season
manual quantity override takes precedence and is clearly identified.

Incoming quantities use confirmed supplier order lines planned within the season.
Draft, cancelled and closed orders are not treated as future receipts. Missing
dates, overdue open orders, unknown statuses or in-transit stock requiring overlap
reconciliation leave affected incoming quantities unknown.

Proposed purchase value = proposed quantity times verified net SKU cost.
Existing PO values use Prix_Achat_Devise, the line discount and sequential header
discounts Remise1 through Remise5, once their interpretation is confirmed.
Open orders contribute the larger of ordered/delivered quantities; closed or
cancelled orders contribute delivered quantities only. Allocation follows planned
receipt dates. These values are PO-based planning commitments, not paid invoices.

Remaining budget = seasonal limit minus existing allocated PO value minus proposed
new purchase value. Incoming orders also reduce new purchase quantities; they are
not added twice to the budget. Known subtotals stay visible when other rows are
unpriced, while incomplete overall totals and remaining funds are marked Unknown.

Forecast gross margin uses forecast revenue minus the selected unit-cost basis for
all forecast sales, including sales supplied by existing inventory. Selling-price
gaps can leave margin unknown while a purchase budget is otherwise complete.

## Review and limits

Coverage shows known stock, incoming supply, costs, selling prices and valued
purchase decisions. Variant and supplier tables are paginated. Supplier exceptions
identify records needing date/status/quantity reconciliation instead of hiding
their quantities or assuming zero. Financial confirmations are saved per season.

The view remains a draft: booked demand can include unknown partial cancellations;
pack sizes, minimum orders, time-phased replenishment, actual invoice payments,
landed costs and live FX are not resolved by this feature. Purchasing approval is
still blocked by the fresh-only deployment policy.

Implementation: `backend-ai/budgeting.py`, `backend-ai/budget_routes.py`,
`frontend/src/app/budget/page.tsx`. Source data stays in joolan_source.db; settings
are stored in the serving database's planning_state and planning_seasons tables.

For a read-only local check, run `python -B check_budget.py` from backend-ai.
The first request loads the saved source projection; subsequent requests reuse
a bounded cache. Currency refresh invalidates only its small reference cache.
# Buying-plan order simulator

The Budget page leads with the buying budget, priced supplier-order subtotal,
covered proposed purchases and the balance after included amounts. The delivery
calendar and missing-data tables have been removed from this page.

The covered-data view includes only positive-quantity recommendations with finite
quantity, stock, supply, cost, price, turnover and margin. Manual price assumptions
are excluded. Supplier records must have resolved nonnegative ordered/received
quantities, net cost and value in the budget currency. Foreign-currency records
are excluded without conversion. Exclusion counts are shown in a compact coverage
note; source records remain intact. No revenue/margin cards are shown when there
are no covered recommendations. A partial balance is never spending approval;
the original full-plan validation gates remain enforced on the server.

Unit price fields in this view are read-only. Users can still adjust quantities,
sell-through or select a recorded supplier price for an included recommendation.

Each order variant has an integer quantity, supplier price selection, selling price,
sell-through assumption and adjustment reason. Recalculate sends the full draft to
the server. Order cost is quantity × net unit purchase price. Expected turnover is
quantity × assumed sell-through × net selling price. Gross margin subtracts the
cost of units expected to sell; the remaining purchased units remain inventory.
These order figures are separate from total season forecast turnover. The default
100% sell-through is an explicit simulation assumption, not a forecast probability.

Supplier selections use net prices from saved Joolan supplier-order lines in the
season and budget currency. A SKU purchase price is an estimate until a supplier
price is selected. Manual cost or selling-price edits are simulation-only and cannot
be validated as sourced prices. Minimum quantities, packs, freight, duties, payment
terms and supplier price validity still need verification before an executable PO.

Validation recalculates on the server, requires a current source/settings/forecast
revision, complete plan purchase values and commitments, resolved turnover/margin,
budget compliance, and selected orders above the margin target with known stock
and supply. Adjustments require reasons. A successful validation stores a local
financial review snapshot in `planning_state` under `buying_review:<id>`; it does
not send an order to Joolan or bypass the existing approved-export policy.



## Article forecast draft
The tracker now groups all forecast variants by article reference, with colours and sizes in one expandable table. The UI explicitly requests the forecast quantity basis (rounded up), before inventory/supply deductions. Purchase price estimates come from the verified SKU price or an unambiguous recorded supplier price; selling price is an editable input when unavailable. Both prices and order quantities can be cleared or edited; missing values remain unknown. These are session draft assumptions, not changes to Joolan supplier orders.

Whole articles with complete financial inputs and a margin meeting the target are ranked by gross margin per purchase cost, then forecast demand and reference. They are included only when their entire cost fits the allowance after known commitments. This deterministic heuristic is not an optimal procurement solver. Exclusions distinguish missing prices, below-target margin, and budget shortfall. Unknown commitments make all allocation provisional. Manual price assumptions and source gaps retain the existing validation restrictions. Click Recalculate after edits; changing season/scenario resets the draft.
