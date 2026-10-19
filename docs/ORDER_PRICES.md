# Order-based catalogue prices

Automatic catalogue defaults now come from the latest usable **actual Joolan
orders**, rather than SKU master purchase prices, selling tariffs, or a seasonal
weighted average. Prices are native-currency net unit amounts excluding VAT.
The customer-order price is the B2B selling price to a retailer, not consumer RRP.

## Selection

- Purchase: `commandes` + `commandes_produits`; confirmed/closed supplier orders,
  actual header `Date`, `Prix_Achat_Devise`, line `Remise_Achat`, and sequential
  header `Remise1`–`Remise5`. The catalogue's recorded supplier is respected when
  present. Supplier cost basis must be verified (`poCostsVerified`).
- Selling: `negoce_entetes` + `negoce_lignes`; confirmed/closed `COMMANDE`
  headers and lines, billable orders in configured primary supplying warehouses.
  Positive quantities and prices only. `Total_HT_Devise` must reconcile with
  `Quantite * Prix_HT_Devise * (1 - Remise / 100)` within 0.02 currency units.
  The selected net unit price is line total / ordered quantity, rounded to cents.
- Both: currencies are resolved through the exported `devises` reference. Customer
  header/line currencies must agree. No FX rates or conversions are assumed.
  Supplier costs can additionally supply an EUR planning default through the
  verified recorded-order policy described below; selling prices are not converted.
  Required source datasets must be complete. Invalid records are excluded and
  counted in the import report; no incomplete export supplies a supposed latest price.
- Latest means greatest valid actual order date at or before the export cutoff
  and today. Price selection also accepts an explicit earlier `through_date` for
  isolated historical/as-of use. Live catalogue values must not be reused in a
  historical backtest without applying that backtest's own cutoff.
- Same-day conflicting prices remain unknown. Numeric document IDs do not prove
  transaction chronology. Same-day equal prices may use one reference as evidence.

Exact article/colour/size evidence takes priority. A variant with no valid exact
history can use a same-article/colour price, then a same-article price, only when
all latest available variant prices in that group agree (and, for purchases,
suppliers agree). Conflicting exact evidence cannot be bypassed by fallback.
Broader matches are explicitly labelled with the evidence variant. No master or
tariff fallback fills unmatched prices.

## Persistence and updates

- `catalogue_prices`: effective values used by planning, per SKU and currency.
- `catalogue_order_prices`: latest automatic evidence, separately for purchase
  and selling, including null values/reasons, source export, cutoff, source order,
  order date, native currency, match level, and previous automatic price on change.
- `planning_state['order_price_import']`: versioned source/settings fingerprint,
  matching counts and exclusions. Unchanged evidence is reused; a source revision
  triggers a new scan. Selection is bounded in memory to the latest date per variant.
- Manual prices, including explicitly cleared prices, survive exports. In Catalogue,
  **Use latest Joolan purchase/selling price** restores the recorded automatic
  default for that individual SKU. It may restore an unknown price if no usable
  order exists. The evidence remains visible while a manual value is active.
- Catalogue GET syncs from the saved validated export. It does not contact Joolan;
  use Season Setup to export recent records. The automatic refresh/forecast workflow
  syncs these prices after activating the new export and before running the model.
- The legacy previous-season importer is no longer called by automatic forecasts.
  Explicit legacy imports invalidate the new price marker so the next sync restores
  current automatic defaults, except manually maintained values.

## Verified recorded-order FX

The tenant-scoped policy in `planning_state['supplier_fx_policy']` enables only
currency pairs corroborated against actual Joolan receipt native/base prices.
USD to EUR uses `net native unit cost / commandes.Taux_Devise`. A missing,
nonpositive or unverified rate leaves the EUR cost unknown. The original currency,
net amount, order, date, rate and verification reference remain in the evidence.
These historical planning rates are not current bank settlement rates. Exact ISO
names in the currency reference (for example `Nom=USD`) are accepted; descriptive
labels and numeric currency codes are not guessed.

Missing costs include explicit reasons, rejected-source counts and historical
supplier alternatives. A different recorded supplier is a review candidate, never
an automatic substitute. Zero source prices remain unresolved. Use
**Budget Tracker → Resolve purchasing inputs** (`/budget/reconciliation`).

## Budget and PO protection

New drafts use Catalogue prices. Saved Budget Tracker drafts keep resolved prices,
quantities and sell-through assumptions. Changed source data marks a draft stale;
it does not silently replace those saved prices. **Refresh catalogue defaults**
adopts automatic defaults in a new saved draft version while retaining explicit
draft edits. Use **Save & recalculate draft** to keep existing assumptions.
Currency changes require separate review and do not carry prices across currencies.

PO drafts retain their own original snapshots and amendments. Updated catalogue
prices flag source changes; they never rewrite existing POs. No supplier order is
sent, and no Joolan record is changed by price selection or catalogue resets.

## Checks

`backend-ai/tests/test_order_prices.py` covers latest selection, reconciled discounts,
native currencies, future/cancelled/nonbillable/consignment exclusions, source
completeness, same-day conflicts, uniform fallback, manual protection/reset,
as-of selection, price change evidence and explicit saved-draft refresh.

The existing catalogue, budgeting, supplier-price, purchase-draft and PO tests
also exercise the financial handoffs. Historical forecast accuracy is unaffected
by this implementation and is a separate validation task.
