# Fresh Joolan integration and release checks

Implemented against the supplied Joolan 2.0.0 Swagger, saved as `docs/joolan-openapi.yaml`. It defines endpoints and stock response fields, but not all columns in the enseigne's SQL tables. Live discovery and reconciliation are required before release.

## Data contract

| Data | Source | Use |
| --- | --- | --- |
| Orders | query.do: negoce_entetes + negoce_lignes | Fresh COMMANDE history through the inclusive selected date. Unique compatible header joins; ordered, delivered and cancelled quantities. |
| Catalogue | query.do: produits + skus | Full catalogue, including non-ecommerce products. catalogue-web.do is filtered and cannot provide a complete catalogue. |
| Customers | query.do: negoce_clients | Validate identities and populate available customer metadata. |
| Inventory | GET image-full-stocks.do, explicit Magasins | Includes zero balances. Disponible enters available stock only when every selected warehouse is represented. Physical, reservation and delivery balances stay separate in raw storage. |
| Suppliers/prices | Relevant tables when available | Raw fournisseurs, tarifsproduits, produits_min_max and magasins. Tax, currency, effective dates and purchasing semantics remain unverified. |
| Supplier orders | Tables discovered by supplier/product/quantity/delivered/date fields | Raw candidates retained. Status, actual ETA, units and overlapping logistics balances need verification before normalization. |

No Joolan create/update/approval/shipping endpoint is used. Required permissions are api_query and api_stock. Confirm legend73's Daytona 73 scope and supplying warehouse codes; do not pool retail inventory without a supply rule.

## Persistence and recovery

`backend-ai/data/joolan_source.db` holds export runs, schema, raw JSON records, page checkpoints and validation reports. Every new export gets new remote boundaries. Resume uses only pages from that run. Credentials pass through stdin to an independent worker and stay in memory, never durable configuration or subprocess arguments. Joolan requires the key in its outbound HTTPS query string; outbound request URLs must not be logged.

`backend-ai/data/joolan_live.db` holds source references, seasons, lineage and atomically published reports. Older CSVs/databases remain on disk but are not selected by the active API or public CLI entry point. The intermediate model CSV comes only from the activated new export.

One export runs at a time. Rows and page cursors commit together. Quota errors pause immediately. Resume preserves completed tables after checking their local counts, without downloading them again. Incomplete tables recheck remote bounded counts; inconsistent partial tables restart. Offset-only partial tables restart on resume. Exited workers become resumable. Failed validation cannot replace the active generation. Results from another source generation are blocked.

If the stock endpoint rejects the request, inventory can be freshly exported from the stocks table through the permitted Query API, restricted to the selected stores and brands. This table may omit zero-stock combinations, so missing rows remain unknown. The validation report identifies which inventory source was used. Rate-limit errors pause immediately rather than issuing fallback queries.

Query reads are not transactional ERP snapshots. Matching counts cannot detect all concurrent edits. Reconcile totals after long pauses. Full stock responses currently load into memory; measure peak memory on the actual catalogue.

## Validation and remaining mapping

Required columns, catalogue/customer matches, header joins, dates, quantity bounds and stock coverage are checked. Warehouse codes are resolved against the selected master codes without regard to letter case; ambiguous codes still fail. Missing stock stays unknown; negative available balances are preserved.

Over-deliveries retain the actual delivered amount, keep booked demand at the original ordered amount and clamp open balances to zero. Signed negative adjustments stay in raw storage and are disclosed separately; they are omitted from the positive booked-order target only when they account for no more than 0.1% of lines and absolute ordered units. Larger adjustments block forecasting until the signed-demand mapping is reviewed. Invalid dates, quantities and ambiguous joins still block activation.

Explicit Quantite_Annulee values are used where supplied. Otherwise the documented Statut mapping applies: 0 unconfirmed (excluded), 1 confirmed, 2 cancelled (unfulfilled remainder excluded), 3 closed (zero open balance). Closed/confirmed lines without explicit partial-cancellation quantities retain booked order demand and disclose unknown cancellation completeness. This is not certified net-sales demand; purchase approval remains blocked.

Training excludes unfinished months, using the last complete export month as the common cutoff even if there were no orders that month. Partial-month orders remain actuals. Lineage records export ID, input hash and dates. Catalogue variants without training history still need a validated cold-start policy; catalogue export alone does not forecast new products.

Purchase approval is blocked until costs, tax/currency, supplier receipts, lead times and lifecycle rules are mapped and reconciled. This is presently a demand forecasting workflow, not an approved purchasing system.

## Production release still requires

1. A fresh live export, cancellation/quantity reconciliation and warehouse checks.
2. Verified price, procurement, receipt-date, lead-time and lifecycle mappings.
3. Rolling holdout evaluation on new data against seasonal/intermittent baselines at brand, article and variant level. Import reliability is not model accuracy; the earlier audit did not demonstrate acceptable variant-level accuracy.
4. User/tenant authentication and authorization, TLS, managed secrets for unattended jobs, scheduling, monitoring and restore-tested backups.
5. Durable forecast queue/worker isolation for multi-user service. Export workers are separate processes; forecast refresh still uses the API background thread.
6. Load, recovery and restore tests. SQLite/local-only access currently targets the single-machine pilot, not an independently verified SaaS deployment.

Tests cover fresh export/activation/forecast roundtrip, quota resume, generation isolation, invalid source preservation, missing cancellations and stock, interrupted workers, closed-month training, customer totals without season years, and rejection of old API/CLI sources.
