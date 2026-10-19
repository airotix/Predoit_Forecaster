# Page-loading performance

The current app uses a local FastAPI service and Next.js frontend. Page navigation and data calculation have separate costs. Development mode compiles routes on first visit; use the production frontend for daily planning.

## Daily run in VS Code

Keep the Python backend running on port 4000 as documented in [Quick start](../QUICK_START.md). In a frontend terminal:

```powershell
cd C:\Users\FBC\Desktop\forecaster\forecasterr\frontend
npm.cmd run build
npm.cmd run start
```

Build once after source changes. On subsequent starts, only `npm.cmd run start` is needed. Stop the frontend before rebuilding, particularly on Windows where its running standalone files can block replacement. Stop the existing development server before starting production mode on port 3000. The start script prepares browser assets and runs Next's standalone server on 127.0.0.1:3000. `--hostname` and `--port` may be supplied explicitly. `npm.cmd run dev` remains the editing workflow.

## Implemented optimizations

- The backend reuses serialized read responses for up to ten minutes, with a 64 MB/64-entry limit. Commits to either the serving or raw-source SQLite database invalidate the cache immediately. Authentication middleware still runs for each request; cache keys isolate credentials, cookies, parameters and database generations. Browser response caching is disabled.
- Concurrent identical reads share their computation. Gzip is negotiated for large JSON responses. Writes, exports with audit side effects, live job state, and server-sent events are excluded from the response cache.
- Budget scenarios reuse source-stock and supplier-receipt calculations. Recommendation scenarios reuse one catalogue-price lookup and avoid calculating the selected scenario twice.
- Customer/date and activity indexes avoid full JSON-ledger scans for customer history and coverage. Catalogue indexes support whole-article pagination; seasonal allocation explicitly groups in article order to avoid sorting large repeated detail payloads.
- Versioned compact-source and reorder-KPI JSON caches live under `backend-ai/data/.read-cache/`. They are derived from saved source data, preserve unknown/decimal values, and are safe to delete while the app is stopped. They regenerate when source identity changes. Only the newest three files per cache kind are retained. A corrupt/unwritable cache falls back to source calculation.
- Order-ledger insert/update/delete triggers increment a revision counter. Reorder and coverage caches observe this counter, including when a record changes without publishing a new forecast. New forecast jobs precompute reorder KPIs after publication so the first page visitor does not pay for that scan.
- The frontend combines overlapping GETs, avoids an extra load on initial live-stream connection, and shares one server-sent-events connection between the page and source banner. Completed responses are not cached in the browser API client. Requests have bounded loading time and writes invalidate overlapping browser read generations.

## Verification and limits

Run the local, read-only benchmark from `backend-ai`:

```powershell
python -B benchmark_pages.py --output output/performance/timings.json
```

It measures all main page shells and their main data endpoints sequentially, including first/repeat reads, payload sizes and content hashes. These are HTTP timings, not a browser-rendering trace. Scenario switches, changed inputs and new data may require a first calculation again. A full fresh Joolan export/model run still has its own duration and quota limits.

The optimization pass compared the API response bodies with their pre-change SHA-256 hashes. Forecast quantities, unknown values, financial results and source labels remained identical. Runtime job endpoints remain live. No new forecast, Joolan export, supplier PO or price edit is performed by the benchmark.

Regression checks cover database invalidation, authorization, request coalescing, compression, memory limits, ledger changes, corrupt cache recovery, and preservation of existing forecast/budget behavior. Financial writes and approvals continue to recompute and validate against current inputs; they never trust a cached GET for authorization or version checks.
