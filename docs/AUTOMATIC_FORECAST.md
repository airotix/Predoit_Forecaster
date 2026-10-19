# Automatic Joolan forecasting

The normal Setup page now accepts a forecast period in whole months. **Refresh data & forecast** runs a durable background job: live schema discovery, fresh full export, missing-data reconciliation, validation, season selection, catalogue preparation, model execution and publication. Administrator tools remain at `/setup/manual`; CSV imports are not part of this workflow.

## Server configuration

Save the Joolan key in `backend-ai/.env`:

```dotenv
JOOLAN_API_KEY=your_actual_key
JOOLAN_ENSEIGNE=legend73
```

`.env` files are excluded from Git. The backend reads these settings directly and detects changes without returning the key to the browser. Process environment variables take precedence. There is no `NEXT_PUBLIC_*` key and no credential in job configuration, subprocess arguments or source records. Do not put credentials in chat, the frontend or source control. `.env.example` contains only placeholders.

## Scope and dates

- Uses the saved client scope: DAYTONA73, D73, IRON AND RESIN, IRON&RESIN; CENTRAL as normal supplying warehouse. The business scope is configured once and retained.
- Downloads all customer-order history available through the job's UTC creation date, for the selected brands; current inventory is requested anew. The monthly model trains on complete months before the requested period. Current-month orders/inventory remain available for operational context.
- Forecast period must cover 1–24 full months, beginning in the current month or later. Retrospective backtests are a separate operation. The model's existing maximum history-to-horizon gap checks still apply.
- Reuses the active season if its dates match, preserving its budget and financial settings. A new period retains the existing currency and approved Joolan field/price mappings, without copying the buying budget. This avoids repeating data-mapping entry for every forecast. A budget still has to be agreed for purchasing.
- Retains permanent manual catalogue values and the previously agreed historical selling-price period. It refreshes that same historical period from the new API export; it does not roll the pricing period forward automatically.

## Finding missed data

Every new job performs a **fresh full extraction**, rather than appending only new order IDs. This retrieves older records previously omitted and historical corrections now present in Joolan. Required tables and discovered procurement/reference tables are exported with all exposed non-secret fields. Changed schema causes saved pages of the affected table to be replaced on resume.

Before activation, reconciliation repeats scoped row counts, primary-key boundaries and column checks for every exported table, including optional datasets. Missing/inconsistent completed records or fields trigger a full repair of that table. Newly appended primary-key tails can extend this generation's verified download only if its old bounded count is unchanged, its captured fields are intact and its cursor reached the old upper boundary. This avoids redownloading full tables whenever live orders arrive; it is not max-ID-only syncing between separate runs. Up to five immediate reconciliation repairs are attempted. Invalid joins, quantities, identities or mandatory fields stop forecasting. Missing optional tables/fields and stock coverage are reported as limitations, not invented values. Joolan reads are not a cross-table transactional snapshot; equal counts cannot prove an unchanged value in every row throughout the extraction window.

The source `runs.report.exportAudit` records table counts, completion checks, unavailable optional tables and field coverage. Original raw records and previous export generations remain in `joolan_source.db`.

## Recovery and storage

- `joolan_source.db.automatic_jobs` stores the workflow state, export run, selected dates, publication ID and retry schedule. Only one running or paused automatic job is allowed.
- A worker process continues after the browser closes and independently of the web server's request lifetime. Its credentials come from server configuration.
- Quota pauses retain completed pages and automatically retry after one hour. No key re-entry is requested. Other permission or mapping failures pause with a readable error; **Retry with server connection** uses the current environment key.
- Transient connection/JSON failures retry automatically up to three times with 30/60/90-second delays. Access/permission failures retain a sanitized diagnostic; they do not expose the key or upstream credential URLs.
- If a worker dies, status recovery marks the job paused. If publication already succeeded, it recognizes the published lineage instead of rerunning it. Model/publication failure restores the previous active source and season when safe; the serving tables are published by the existing atomic pipeline transaction.
- While a job manages the source/season, conflicting manual changes are blocked. The previous results may be temporarily unavailable between source activation and completion. On a handled failure the previous source/season selection is restored. Dismiss a paused job to choose another period.

## Limits

Forecasting does not make absent Joolan fields available. Unverified cancellation semantics, customer-visit data, supplier commitments, price currency/tax definitions, MOQ/lead-time rules and missing variant stock remain explicit data-quality issues. Financial approval requires valid prices, supply information and a buying budget. Consignment-store management remains outside the delivery scope.

This version prioritizes correctness and recovery: a full history refresh can be slow and may span multiple quota windows. Incremental syncing will require a reliable last-modified/deletion contract plus periodic full reconciliation; a maximum-ID-only append would miss historical corrections.

## Verification

Backend regression tests cover isolated end-to-end export/audit/publication, quota recovery, connection retries, failure rollback, date validation, duplicate jobs, credential storage, missing rows/fields and verified primary-key tail extensions. The new Setup page responds over local HTTP, and the frontend production build is verified. Interactive browser QA has not been performed in this environment.

A live automatic job for October 2026–March 2027 was started on 14 October using the server env key: job `dfb914b3a637403da3522c28358fa734`, export `e036a2ae0ad149669a2896c1309ba26f`, history through 14 October. The live source passed reconciliation and validation with no blockers: 605,234 usable order lines, 103,205 catalogue variants and 34,611 CENTRAL inventory records. The job then advanced to catalogue preparation. This records source validation, not a claim of successful forecast publication; the job's current status and final report are displayed on Setup.
