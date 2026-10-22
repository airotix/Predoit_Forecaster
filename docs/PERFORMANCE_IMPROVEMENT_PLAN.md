# Page-loading audit and implementation plan — 22 October 2026

## Result

All 18 existing page routes returned HTTP 200. Of 34 measured API routes, 33 responded successfully; the operator-only full database-integrity endpoint timed out after 90 seconds. It is not called by the current Settings page. This timeout is a performance finding, not proof of database corruption.

The highest-impact findings are development-mode compilation, 30.48 MB decoded Budget responses, 18.34 MB Recommendations responses, and repeated whole-assortment calculations on financial reads. No product change or performance optimization was applied during this audit. Existing uncommitted application fixes were preserved.

## Measurement method and limits

- Measured the running local FastAPI backend on port 4000 and the development frontend on port 3000. Timings are specific to this Windows machine and saved data, not a hosted performance SLA.
- Measured each page shell twice, each normal API up to three times, cache-hit/miss headers, compressed wire sizes and decoded body sizes. The initially measured requests may already be cached because the user had opened Budget.
- Forced response-cache misses on nine core read routes with ignored diagnostic query parameters. On-disk derived caches remained available. This is not a clean-machine/export-cold benchmark.
- Retested Dashboard and Allocation misses twice to avoid treating a single slow outlier as normal. Dashboard confirmed at 5.98–6.07 s; its initial isolated miss was 19.40 s. Allocation confirmed at 1.44–1.45 s; its earlier misses were 1.79 and 8.03 s. The full integrity diagnostic and first-time warming can compete for I/O, so use the confirmations for the plan.
- Compared the already-built production frontend on temporary port 3001 without stopping the development server. Only HTML was requested on 3001; no claim is made about full browser/API performance on that origin. The temporary server was stopped afterward.
- HTTP shell timings exclude JavaScript download/execution, JSON parsing, React rendering and interaction delay. HTTP API timing stops after reading the response body and excludes local gzip decompression/JSON parsing by the benchmark.
- Browser data-ready observations, with warmed assets/API state, confirmed Products at 1.96 s, Budget at 1.15 s, Recommendations at 1.25 s, Catalogue at 2.00 s, Scope at 3.12 s and Customers at 1.18 s. These include automation/observation overhead and are not LCP/INP. Dashboard/Allocation readiness probes were inconclusive, while those pages and their data APIs responded normally.
- These small sample sizes do not establish p95/p99. Establish real browser paint/interaction metrics in the acceptance phase.
- No new Joolan export, forecast, price save, PO creation, supplier message, final validation or backup was initiated. The HTTP benchmark used GETs only. Browser probes did not submit any form.

## Page-by-page findings

Each entry separates page-shell response time from its main data request. Do not add these values and call the sum a measured full-page load: some requests run in parallel. Shared season/lineage reads and delayed details also contribute. API repeat timings are cache hits where supported; Validation deliberately recalculates and has no such hit.

### Home / dashboard redirect — `/`

- Development HTML: first measured **0.075 s**, repeat **0.048 s**.
- Production HTML: first measured **0.901 s**, repeat **0.007 s**.
- Main API: `dashboard` — calculation/first measured **6.025 s**; repeated median **0.008 s**; decoded JSON **0.001 MB**, wire **0.000 MB**.
- Planned change: Production mode; share dashboard summary.

### Dashboard — `/dashboard`

- Development HTML: first measured **0.076 s**, repeat **0.065 s**.
- Production HTML: first measured **0.209 s**, repeat **0.007 s**.
- Main API: `dashboard` — calculation/first measured **6.025 s**; repeated median **0.008 s**; decoded JSON **0.001 MB**, wire **0.000 MB**.
- Planned change: Precompute the dashboard financial summary; avoid full catalogue price evidence and all recommendation columns on every miss.

### Season Setup — `/setup`

- Development HTML: first measured **4.000 s**, repeat **0.094 s**.
- Production HTML: first measured **0.101 s**, repeat **0.006 s**.
- Main API: `automatic` — calculation/first measured **0.045 s**; repeated median **0.029 s**; decoded JSON **0.103 MB**, wire **0.103 MB**.
- Planned change: Only poll while a job is active; update the selected season locally after completion instead of POSTing a no-op activation on every mount.

### Manual Joolan Setup — `/setup/manual`

- Development HTML: first measured **2.998 s**, repeat **0.094 s**.
- Production HTML: first measured **0.055 s**, repeat **0.007 s**.
- Main API: `joolan/fresh` — calculation/first measured **0.042 s**; repeated median **0.040 s**; decoded JSON **0.183 MB**, wire **0.183 MB**.
- Planned change: Split live job progress from static discovery/report data; pause polling for hidden tabs and completed jobs.

### SKU Catalogue — `/catalogue`

- Development HTML: first measured **3.018 s**, repeat **0.093 s**.
- Production HTML: first measured **0.061 s**, repeat **0.007 s**.
- Main API: `catalogue?currency=EUR&grouped=true&limit=20` — calculation/first measured **0.728 s**; repeated median **0.005 s**; decoded JSON **0.621 MB**, wire **0.014 MB**.
- Planned change: Keep existing article pagination; lazy-load evidence/details only when an article is opened; keep complete colour/size groups.

### Business Scope — `/scope`

- Development HTML: first measured **2.955 s**, repeat **0.163 s**.
- Production HTML: first measured **0.064 s**, repeat **0.004 s**.
- Main API: `operating-scope` — calculation/first measured **1.079 s**; repeated median **0.005 s**; decoded JSON **0.005 MB**, wire **0.001 MB**.
- Planned change: Cache immutable catalogue/warehouse options by export revision; fetch once per app session, invalidate after source/scope changes.

### Settings & access — `/settings`

- Development HTML: first measured **3.625 s**, repeat **0.077 s**.
- Production HTML: first measured **0.079 s**, repeat **0.005 s**.
- Main API: `auth/users` — calculation/first measured **0.008 s**; repeated median **0.017 s**; decoded JSON **0.000 MB**, wire **0.000 MB**.
- Planned change: Production mode and one auth bootstrap; load the admin user list when the management panel is needed.

### Customer Coverage — `/customers`

- Development HTML: first measured **0.248 s**, repeat **0.066 s**.
- Production HTML: first measured **0.065 s**, repeat **0.005 s**.
- Main API: `customers` — calculation/first measured **0.040 s**; repeated median **0.008 s**; decoded JSON **0.524 MB**, wire **0.071 MB**.
- Planned change: Fast server response already; paginate/filter the customer directory server-side as it grows; retain on-demand order articles.

### Product KPIs — `/products`

- Development HTML: first measured **2.893 s**, repeat **0.071 s**.
- Production HTML: first measured **0.124 s**, repeat **0.030 s**.
- Main API: `products` — calculation/first measured **1.352 s**; repeated median **0.009 s**; decoded JSON **10.032 MB**, wire **0.565 MB**.
- Planned change: Return a compact paged list; load historical size/reorder detail on opening the product drawer.

### Demand Projection — `/projection`

- Development HTML: first measured **3.123 s**, repeat **0.107 s**.
- Production HTML: first measured **0.053 s**, repeat **0.005 s**.
- Main API: `projections` — calculation/first measured **0.363 s**; repeated median **0.009 s**; decoded JSON **3.909 MB**, wire **0.174 MB**.
- Planned change: Return a paged article summary; keep the current separate colour/size detail endpoint.

### Seasonal Allocation — `/allocation`

- Development HTML: first measured **2.613 s**, repeat **0.084 s**.
- Production HTML: first measured **0.055 s**, repeat **0.004 s**.
- Main API: `seasonal-allocation?scenario=base` — calculation/first measured **1.441 s**; repeated median **0.015 s**; decoded JSON **0.049 MB**, wire **0.006 MB**.
- Planned change: Materialize article collection/brand facts rather than grouping repeated full SKU detail JSON on every request.

### SKU Recommendations — `/recommendations`

- Development HTML: first measured **3.034 s**, repeat **0.083 s**.
- Production HTML: first measured **0.059 s**, repeat **0.005 s**.
- Main API: `recommendations?scenario=base` — calculation/first measured **10.518 s**; repeated median **0.011 s**; decoded JSON **18.341 MB**, wire **0.738 MB**.
- Planned change: Page the article/colour summary and fetch one selected size breakdown; reuse one versioned scenario result instead of rebuilding the whole assortment.

### Budget Tracker — `/budget`

- Development HTML: first measured **0.092 s**, repeat **0.065 s**.
- Production HTML: first measured **0.062 s**, repeat **0.004 s**.
- Main API: `budget/draft?scenario=base` — calculation/first measured **9.103 s**; repeated median **0.013 s**; decoded JSON **30.484 MB**, wire **1.624 MB**.
- Planned change: Separate global summary/allocation from paged article rows and lazy evidence. Preserve global financial calculations and durable edits.

### Purchasing-input reconciliation — `/budget/reconciliation`

- Development HTML: first measured **3.089 s**, repeat **0.090 s**.
- Production HTML: first measured **0.054 s**, repeat **0.004 s**.
- Main API: `budget/reconciliation?scenario=base&issue=all&search=&offset=0&limit=50` — calculation/first measured **5.755 s**; repeated median **0.015 s**; decoded JSON **0.022 MB**, wire **0.003 MB**.
- Planned change: Derive the issue index once per financial-input revision; filter and paginate it without reconstructing the full buying simulation.

### Order Validation — `/validation`

- Development HTML: first measured **3.053 s**, repeat **0.079 s**.
- Production HTML: first measured **0.063 s**, repeat **0.005 s**.
- Main API: `purchase-orders/22e32f76014a49a6acdaf12f62104784/validation` — calculation/first measured **4.791 s**; repeated median **5.370 s**; decoded JSON **0.005 MB**, wire **0.005 MB**.
- Planned change: Use selected-PO checks plus a versioned global commitment aggregate for GET previews. Final validation POST remains authoritative and current.

### Purchase Orders — `/purchase-orders`

- Development HTML: first measured **2.988 s**, repeat **0.070 s**.
- Production HTML: first measured **0.071 s**, repeat **0.005 s**.
- Main API: `purchase-orders?season_id=334344374b0f43ea84b4d76fe1b42f55&scenario=base` — calculation/first measured **0.497 s**; repeated median **0.005 s**; decoded JSON **0.005 MB**, wire **0.002 MB**.
- Planned change: Open the saved list/detail independently of Budget; use a small budget-import summary instead of downloading the 30.5 MB full draft.

### Sign-in — `/login`

- Development HTML: first measured **3.507 s**, repeat **0.057 s**.
- Production HTML: first measured **0.059 s**, repeat **0.006 s**.
- Main API: `auth/config` — calculation/first measured **0.006 s**; repeated median **0.005 s**; decoded JSON **0.000 MB**, wire **0.000 MB**.
- Planned change: Production mode; defer Microsoft SSO code until needed and avoid loading protected app data before sign-in.

### PO print / PDF view — `/purchase-orders/22e32f76014a49a6acdaf12f62104784/print`

- Development HTML: first measured **2.815 s**, repeat **0.077 s**.
- Production HTML: first measured **0.115 s**, repeat **0.101 s**.
- Main API: `purchase-orders/22e32f76014a49a6acdaf12f62104784` — calculation/first measured **0.044 s**; repeated median **0.041 s**; decoded JSON **0.004 MB**, wire **0.004 MB**.
- Planned change: Read only the selected saved PO, defer optional explanatory evidence and retain immutable validated document snapshots.

## Root causes with code evidence

1. **Development compilation on navigation.** `frontend/package.json` currently starts `next dev`. Most first page shells took 2.6–4.0 s in this run. Across all 18 routes, median first measured development shell was 2.993 s versus 0.063 s for production. This comparison concerns HTML generation only.
2. **Oversized data responses.** Budget serializes 30,484,239 bytes decoded / 1,624,387 bytes compressed. Recommendations serializes 18,340,846 / 738,420. Products serializes 10,031,601 / 564,867. Projection serializes 3,909,255 / 174,418. Pagination currently happens in the browser for several of these screens. Gzip is already implemented; adding gzip again is not the fix.
3. **Whole-catalogue price hydration for narrow tasks.** `catalogue.price_map` reads all prices plus all order-price evidence for a currency. `planning.final_rows` selects every recommendation column and builds all result rows. Dashboard financial totals, Budget and Recommendations reuse this path. `purchase_orders.selling_price_updates` also constructs this whole price map for a one-article PO; it took 2.89–3.30 s repeatedly.
4. **PO page request waterfall.** `frontend/src/app/purchase-orders/page.tsx` awaits list → full budget draft → requested PO detail. A saved PO detail itself took only 0.039–0.044 s, but the page couples it to the full calculation and 30.5 MB draft. `POValidation.tsx` similarly awaits list then checks.
5. **Read previews repeat expensive global financial work.** `po_validation.py` calls `budgeting.build_report` on every validation GET. The tested tiny PO still took 4.79–5.39 s for each read. Reconciliation rebuilds a complete simulation before returning only 50 issue rows; a cache miss took 5.76 s.
6. **Cache size/key/invalidation pressure.** `read_cache.py` stores both raw and compressed data in a 64 MiB cache, keys queries by raw query-string order and invalidates on any commit to either database. The four large core responses alone occupy about 62.8 MiB including gzip. Alternate scenarios and duplicate parameter combinations can evict them. Existing authorization isolation and write invalidation must remain intact.
7. **Repeated app bootstrap and idle polling.** `AppShell.tsx` fetches seasons/active season on every shell mount. `RunStatus.tsx` fetches lineage/source again; active-season hydration can trigger a second banner read. GET coalescing exists only while requests overlap, not after they complete. Setup polls every five seconds even when idle. Its completion handler calls `setActiveSeason`, which POSTs activation even when the already-active season is unchanged; avoid this no-op write and resulting invalidation.
8. **Heavy maintenance on a synchronous request.** `/api/admin/db/health` runs full `PRAGMA integrity_check` on each database. The serving DB is about 2.11 GiB and source DB about 2.78 GiB. It exceeded the 90-second HTTP timeout. This is a maintenance job, not a normal page prerequisite.

## Implementation sequence

### 1. Remove operational and navigation delays first

- Make daily startup use the validated production build (`npm run build` after changes, then `npm run start`). Keep a separate development command. Do not install packages or rebuild on every ordinary launch.
- Decouple opening saved POs from loading the entire Budget draft. Fetch the selected PO and list independently; load a compact import summary separately.
- Stop idle/hidden-tab Setup polling; update the active season locally after a known completed job and only call activation when the user actually changes it.
- Acceptance: every ordinary page shell returns within 0.3 s after server startup on this machine; a saved PO can open without waiting for Budget. No source, season or PO business behavior changes.

### 2. Reduce the initial payloads

- Add versioned summary and detail APIs for Budget, Recommendations, Product KPIs and Projections. Send 20–50 visible articles/colours and counts, not the entire assortment.
- Fetch complete colours/sizes and price-source evidence only when an article/drawer is opened. Reuse metadata once per result rather than repeating identical explanations on every size.
- Keep global search, sort, filters and the two-year activity order on the server before pagination. Keep whole-article breakdowns intact.
- Budget allocation MUST still consider the complete plan. Global totals and allocation are calculated for the full assortment, then the displayed rows are paginated; never allocate only the visible page.
- Acceptance: initial list payloads under 250 KB decoded where practical; initial Budget summary + first article page under 1 MB decoded; no forecast, currency, unknown-value or allocation changes.

### 3. Make financial reads reuse small, consistent projections

- Add reference/SKU-scoped price lookups for PO refresh and one-article details. Exclude price evidence from calculations that need only numeric prices.
- Read only the recommendation columns needed for the current calculation; avoid SELECT * and decoding large explanation payloads for aggregate totals.
- Reuse a derived financial summary/issue index keyed by forecast run, scenario, source, catalogue price/status revision, budget version and scope. Build it after publication/financial updates or on demand once.
- Use that consistent summary for Dashboard, Budget import summaries and validation GET previews. Return a clear “refreshing checks” state if calculation is still running.
- All save, submit and FINAL VALIDATE actions must check current versions and recompute authoritative constraints inside the existing transaction. Cached read previews must never authorize spending.
- Acceptance: ordinary summary/validation previews under 1 s warmed and under 3 s on an ordinary calculation miss; targeted selling-price refresh under 0.5 s for a small PO. Longer final write validation can show explicit progress. These are targets, not measured improvements yet.

### 4. Make allocation and cache behavior predictable

- Materialize small article collection, brand, status, activity and variant-count facts from each validated export/publication. Allocation should not regroup full repeated product JSON for every filter request.
- Canonicalize equivalent query parameters. Split immutable forecast/source caches from live draft/price caches using explicit revisions; keep token/role isolation and invalidate all affected data on writes.
- Compact paginated responses should make the existing cache effective. Only consider increasing its memory limit after measuring retained bytes; capacity alone is not the primary fix.
- Use EXPLAIN QUERY PLAN and trace timings before adding indexes. Focus on current catalogue reference/brand/code, selected PO rows and issue lookups. Keep SQLite for this local pilot; no database migration is justified solely by these measurements.

### 5. Share bootstrap and improve perceived navigation

- Mount the app shell once in the authenticated layout. Share a small bootstrap result for active season, role, source revision and forecast readiness.
- Retain completed read results for a short, explicit stale window and revalidate by publication/financial revisions. On writes, invalidate affected reads immediately; protect unsaved price/quantity edits.
- Lazy-load large charts, size matrices, evidence panels, admin user controls and SSO code only where used. Keep page-specific skeletons and progressive loading, so one slow panel does not blank the entire page.
- Keep critical validation status visibly refreshing rather than silently showing stale “ready” values.

### 6. Move maintenance off page requests and add performance gates

- Return lightweight DB metadata and the latest completed integrity-check result immediately. Run full integrity checks as a bounded background job with status/progress, preferably away from forecast calculation.
- Extend the benchmark into a reproducible cold-response-cache/warm-cache suite, followed by controlled browser measurements for navigation, data ready, LCP and interaction delay. Use the same saved data and stable machine conditions.
- Collect at least 20–30 navigations per representative flow before reporting p95. Proposed pilot targets: warmed usable navigation under 1.5 s, ordinary first data views under 3 s and no navigation-triggered two-minute spinner.
- Recheck all 18 routes plus scenario switching, global search, pagination, article expansion, budget edits, price saves, supplier selection, PO save/submit, permission isolation and stale-version handling.
- Compare baseline forecast quantities, price sources, unknowns, global totals and constraints before/after. Test every financial write against current data; keep the existing backend/frontend regression suites.

## Recommended first work package

Implement sequence 1 and the compact Budget/PO import-summary contract first. This removes daily compilation delay and an unnecessary full-plan dependency from saved POs. Then deliver the paginated Budget and Recommendations reads; these contain the largest payloads and the most expensive daily calculations.

## Evidence files

- `output/performance/2026-10-22/http-results.json`: every page and API sample, body sizes, response hashes and cache headers.
- `output/performance/2026-10-22/api-cache-miss.json`: forced response-cache misses for core APIs.
- `output/performance/2026-10-22/api-confirmation.json`: repeated Dashboard/Allocation misses.
- `output/performance/2026-10-22/production-pages.json`: production HTML comparison for all 18 routes.
- `output/performance/2026-10-22/browser-observations.json`: browser observation notes and explicitly inconclusive probes.
- The raw runtime evidence stays in ignored `output/`; this plan is the source-controlled deliverable.
