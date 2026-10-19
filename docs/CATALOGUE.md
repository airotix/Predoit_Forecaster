# Saved SKU catalogue

The SKU Catalogue page reads all variants from the currently validated Joolan export and stores their product, SKU and warehouse records in the persistent `catalogue_skus` table in `backend-ai/data/joolan_live.db`. Entries removed from a later export are retained but marked non-current. The raw Joolan source is unchanged.

`catalogue_prices` stores purchase and selling prices per SKU and ISO currency, with separate manual/Joolan provenance. Prices are net unit prices excluding VAT. Only verified Joolan pricing mappings seed defaults; absent values remain unknown. Manual fields, including deliberately cleared prices, survive source refreshes and forecast publications. Other-currency prices are never converted automatically.

The page provides paginated search, brand filters, editable prices and complete imported detail records. Saving prices is permanent. Discarding edits or editing the Budget Tracker does not modify this master.

Forecast execution refreshes the catalogue snapshot when the source changes and merges its currency-matched prices into planning inputs. Their fingerprint participates in forecast lineage. Budget reports read saved prices immediately; existing quantity and price simulation overrides still take precedence in the draft. Catalogue pricing cannot resolve missing inventory, supplier commitments or cancellations, and does not bypass approval checks.

Forecast-generated tables can be replaced without dropping the catalogue tables. Persistence tests cover database reopening, forecast table rebuilds, source refresh, currency separation, unknown prices, and Budget/forecast-input consumption.
