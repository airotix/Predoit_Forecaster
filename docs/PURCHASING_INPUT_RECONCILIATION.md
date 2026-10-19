# Purchasing input reconciliation

Open **Budget Tracker → Resolve purchasing inputs** at `/budget/reconciliation`.
The page reads saved Joolan evidence and current Catalogue values, listing missing purchase costs,
selling prices, warehouse stock, incoming supply and customer-delivery inputs.
Search, issue filters and pagination keep the review manageable. Each variant
links to its article in Budget Tracker. Counts include inactive and zero-quantity
variants; a saved draft override is shown separately from an unresolved source.

## Price sources and FX

Purchase defaults use actual supplier orders and their net prices, discounts,
currency, supplier and actual dates. Exact variants are preferred; wider article
matches require agreement across the available latest evidence. Same-day
conflicts, zero prices, unknown currencies and incomplete exports stay unresolved.
Different supplier names are not merged automatically.

For legend73, a bounded read-only verification checked 30 USD receipt records
against Joolan's recorded base prices and two EUR receipt witnesses. All 30 USD
prices reconciled with division by `Taux_Devise` within 0.02; multiplication matched
none. The persisted policy enables USD→EUR only, retains the evidence and is
scoped to the tenant. An individual supplier order still needs its own usable
rate; the proof does not supply missing rates. Receipt prices establish direction
only: automatic purchase prices still come from supplier orders.

Historical supplier alternatives are visible with source order, date and currency.
Select one in Budget Tracker, save the draft and explicitly review the supplier
and price with a reason. The system never interprets a missing value as zero.
Manual Catalogue prices, saved drafts, reviews, forecasts and existing POs are
preserved. Source refreshes can mark saved drafts stale for review.

## Supply and documents

Open supply whose expected receipt date has passed the export cutoff is flagged
for reconciliation, including dates inside the planning season. It is not added
as available inventory. Existing foreign supplier commitments use the same
verified conversion while retaining native values. Missing quantities, dates,
stock rows and overlapping transit balances still prevent certified totals.

New supplier POs group by supplier and native currency. Their financial review
uses the budget currency; CSV/print outputs retain the supplier's native price
and currency. Both amounts are editable and linked by the saved historical rate.
The rate is a planning assumption, not a bank quote. No Joolan write or supplier
communication occurs. See [PO workflow](PURCHASE_ORDERS.md) and
[price review](FINANCIAL_PRICE_REVIEW.md).

## Verification

The backend suite includes receipt/rate validation, tenant scope, absent rates,
zero/conflicting prices, manual preservation, different supplier review,
foreign commitments, overdue supply, native PO exports/edits and paginated input
review. Live activation backs up the serving database before updating automatic
price evidence. The source export and published demand forecast are retained.

## Local activation result — 19 October 2026

For the published Oct 2026–Mar 2027 buying plan (4,478 variants):

- Purchase costs missing before: 1,982. Recovered: 718.
- Existing usable costs updated to newer order evidence: 244.
- Nine earlier same-article fallbacks were withdrawn because the additional
  converted evidence no longer supports uniform pricing. Missing after: 1,273.
- Remaining primary reasons: 361 supplier changes; 251 nonuniform other variants;
  522 zero/invalid source prices; 56 without supplier orders; 83 unmapped currencies.
- Other unresolved inputs: 20 stock, 58 selling price, 819 incoming supply and
  1,510 customer delivery variants. These groups overlap and include inactive or
  zero-quantity variants. They are not a count of approved purchase lines.
- 3,313 supplier lines require reconciliation after comparing receipt dates to
  the actual export cutoff. This is a stricter timing check, not newly created orders.

The pre-activation serving database backup and evidence are under ignored local
`backend-ai/output/` files (`before-step2-20261019-093717.db`,
`step2-activation.json`, `step2-budget-reconciliation.json`,
`step2-withdrawn-defaults.json`, `step2-live-smoke.json`). Protected-data checks
confirmed the published forecast, source selection, manual prices, drafts,
reviews, statuses and existing POs were preserved. No live order was approved.

345 backend tests and 16 frontend tests passed; TypeScript, lint and production
build passed. HTTP checks returned 200 for the reconciliation, Budget and PO
pages and the reconciliation/draft APIs. First observed reconciliation API load
was 22.2 seconds, with the subsequent draft calculation 8.5 seconds; these are
individual local requests, not browser paint or load-test results. Interactive
browser acceptance and production-readiness work remain separate.
