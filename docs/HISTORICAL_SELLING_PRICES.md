# Previous-season selling-price defaults

Enabled on 14 October 2026 at the user's request. The selected previous season is **1 April–30 September 2026**, immediately before the current October 2026–March 2027 plan. This is a one-time import from the saved fresh Joolan API export; no legacy CSV, older season fallback or remote ERP write is involved.

- Scope: DAYTONA73, D73, IRON AND RESIN, IRON&RESIN; customer orders supplied by CENTRAL.
- Exact matching: article, colour, size and currency. Ambiguous catalogue identities are excluded.
- Eligible sources: COMMANDE headers and lines, both confirmed (1) or closed (3), billable headers, positive quantities and net prices. Draft, cancelled, unknown-status, non-billable and unknown-currency records are excluded.
- Currency: explicit `devises.Code` mapping, with matching header/line currencies. No exchange-rate conversion.
- Price: `sum(Total_HT_Devise) / sum(Quantite)`, rounded to cents. Each line must reconcile with `Quantite × Prix_HT_Devise × (1 − Remise / 100)` within two cents. VAT is excluded and recorded discounts are applied once.
- These are historical agreed customer-order prices used as editable planning defaults, not evidence of realized turnover or the client's current price list.

The import saved **7,133 catalogue prices**. Catalogue displays the period, order/line counts and observed price range. A variant without eligible matching history receives no historical default. The catalogue remains editable, and manual prices (including explicit blanks) are preserved. Historical defaults survive a saved-source catalogue refresh. Budget Tracker and new forecasts read the saved catalogue values; budget edits remain separate.

Persistent records are in `backend-ai/data/joolan_live.db`: `catalogue_prices.selling_source` uses `historical:2026-04-01:2026-09-30`. The `planning_state` keys `historical_price:<sku>:<currency>` retain provenance, and `historical_price_import` records the import summary. Existing saved drafts may become stale and need review plus Save & recalculate before validation. No saved draft quantities or manual prices are changed by this import.

The period is fixed for now. It does not automatically roll forward or import other seasons. The client can later replace defaults in SKU Catalogue and save the updated prices permanently.

Verification: 200 backend tests and the frontend production build passed. Live catalogue and budget APIs returned HTTP 200; the buying view receives historical defaults for **3,951 of 4,041 positive-demand variants (97.8%)**, leaving 90 unknown. The EUR catalogue contains 7,089 selling prices; the 7,133 imported price records also include other separately labelled currencies. No draft edits were saved during verification.
