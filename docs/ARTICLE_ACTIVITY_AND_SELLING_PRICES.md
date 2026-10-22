# Article activity and editable selling prices

## Two-year activity review

Catalogue, Product KPIs, Demand Projection, Seasonal Allocation, SKU Recommendations and Budget Tracker show articles without positive customer orders in the last two years after the other articles. The existing sort is retained within each group; Catalogue applies this before pagination.

The date is the latest valid customer-order date across the article's colours and sizes in the published, scoped order ledger. Cancelled/unconfirmed, nonpositive, invalid-date and future-dated lines do not reset activity. The anchor is the published export's through-date, with the training cutoff month-end as a fallback. A line exactly two calendar years old qualifies. The machine clock and article collection codes do not determine activity.

The badge is **No orders in 2+ years — review discontinuation**. This is a display warning: it does not assert that the article is discontinued, remove historical training observations, change forecasts, alter budget allocation priority, or block purchasing. Existing Joolan/local inactive flags continue to control purchasing. Articles without recorded order history receive a separate badge; they are not automatically classed as dormant.

Activity is cached by ledger revision and publication identity. New publications collect the dates during their existing order-ledger pass, avoiding another full database scan. The first read of an older publication may build the cache once. Cache files are regenerable and stay under the ignored data folder.

## Selling-price editing

Typing a valid selling price in a Budget article/colour bulk field immediately creates edits for its sizes. Clicking Apply is no longer required to make the typed value part of the draft. Individual sizes remain editable. Article financial totals and selected-article review figures preview edits immediately; **Save & recalculate** persists and checks the Budget draft. Allocation explanations reflect the last server calculation until saved.

PO drafts support individual, article-wide and colour-wide selling-price entry. The financial cards preview edits immediately. A visible input list names variants missing quantity, purchase cost or selling price. **Save PO changes** stores the edits and recalculates server totals. A change reason is required for final financial validation of amended assumptions.

Already-created POs retain their saved price snapshot. **Refresh selling prices from Budget / Catalogue** previews current saved Budget prices for the same publication/season/scenario/currency, then Catalogue prices where the Budget has none. The preview preserves manual PO price overrides. **Apply to draft**, then **Save PO changes**, adopts the proposed prices. Refresh is unavailable for validated/cancelled orders, and does not overwrite Catalogue, other POs or the original Budget draft.

This selling-price refresh does not change supplier costs or currencies. Supplier-order costs still retain their existing source/FX evidence and review requirements.

At 100% sell-through, 3 units costing EUR 79 and selling for EUR 129 produce purchase cost EUR 237, expected turnover EUR 387, gross margin EUR 150 and margin rate 38.76%. Missing prices remain unknown; they are never substituted with zero. At zero turnover a margin percentage cannot be calculated.

These are local planning changes. They do not submit supplier orders or write to Joolan.
