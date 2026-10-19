# Run with fresh Joolan data

**Setting up another machine? Start with [QUICK_START.md](QUICK_START.md)** for dependency installation, server configuration, first-run bootstrap, data transfer and daily startup. The steps below describe the manual administrator workflow.

Previous CSVs, saved workbooks and old databases are excluded from this workflow.

Start the backend:

```powershell
cd C:\Users\FBC\Desktop\forecaster\forecasterr\backend-ai
python -B -m uvicorn api_server:app --host 127.0.0.1 --port 4000
```

Start the frontend in another terminal:

```powershell
cd C:\Users\FBC\Desktop\forecaster\forecasterr\frontend
npm.cmd run dev
```

Open http://localhost:3000/setup and keep both terminals running.

1. Enter the API key in the password field. Use enseigne legend73, with api_query and api_stock permissions.
2. Click **Check connection and discover fields**. Verify the enseigne contains Daytona 73's data and select its supplying warehouses.
3. Click **Start fresh Joolan export**. All available COMMANDE history through the selected date, catalogue, customers and current stock are downloaded anew.
4. If quota is reached, wait for Joolan's reset, re-enter the key and click **Resume this export with the key above**. Complete pages are retained.
5. Review validation. Missing or ambiguous fields need a verified live mapping; the app does not invent zero cancellations or incoming quantities.
6. Click **Use this validated fresh export** when validation succeeds.
7. Save a demand-planning season after the last complete training month. For an export through October 7, 2026, October 2026 through March 2027 is a valid example.
8. Click **Run fresh-data forecast**, wait for completion, then open the dashboard.

Raw source versions are in `backend-ai/data/joolan_source.db`. Serving results are in `backend-ai/data/joolan_live.db`. The generated intermediate CSV contains only the activated fresh version.

Purchase approval remains unavailable pending verified cost, currency, supply and lead-time semantics. Integration does not establish forecast accuracy. See [mapping and release requirements](docs/FRESH_JOOLAN.md).

The [Budget Tracker](http://localhost:3000/budget) now supports seasonal limits,
scoped Joolan stock and supplier orders, partial totals and financial mappings.
See [budget setup and calculation rules](docs/BUDGET_TRACKER.md). Currency labels
can be fetched separately without downloading the full history again.
