"""Build a readable review and an inline-data canvas from the audit results."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'backend-ai/output/accuracy-audit'
r=json.loads((OUT/'report.json').read_text())
assert len(r['folds'])==3,'Finish all three evaluations before publishing the review.'
folds=r['folds']
total=sum(f['allVariantMonths']['actualUnits'] for f in folds)
pooled=lambda section,metric:sum(f[section][metric]*f[section]['actualUnits'] for f in folds)/sum(f[section]['actualUnits'] for f in folds)
r['pooled']={section:{k:pooled(section,k) for k in ('wape','bias')} for section in ('allVariantMonths','brandMonths','seasonalNaive','recentMean')}
r['pooled']['newVariantDemandShare']=sum(f['missingNewProductUnits'] for f in folds)/total*100
(OUT/'report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
fmt=lambda n:f'{n:,.1f}'
lines=[]
for f in folds:
    lines.append(f"- **{f['testStart']} to {f['testEnd']}:** variant/month WAPE **{fmt(f['allVariantMonths']['wape'])}%**; brand/month WAPE **{fmt(f['brandMonths']['wape'])}%**; total bias **{fmt(f['allVariantMonths']['bias'])}%**. New variants account for {fmt(f['missingNewProductShare'])}% of actual units.")
review=f'''# Daytona 73 forecast review — October 7, 2026

**Verdict: working local prototype; not yet reliable for automated purchasing or a production accuracy claim.**

The completed October 2026–March 2027 run proves execution, not predictive accuracy. Future outcomes are unavailable. I evaluated the same forecasting engine independently on three historical six-month periods, using the full known variant universe at each origin, 250 CatBoost iterations, and model selection strictly before the outer test period. Production settings and forecasts were not changed by this audit.

## Measured accuracy

WAPE = sum of absolute forecast errors / sum of actual units × 100. Lower is better. Bias = sum(forecast − actual) / sum(actual) × 100. Negative bias means underforecasting. WAPE can exceed 100%; it is not a probability of being correct. I do not label 100 − WAPE as product accuracy.

{chr(10).join(lines)}

Across all three tests, pooled variant/month WAPE is **{fmt(r['pooled']['allVariantMonths']['wape'])}%**, versus **{fmt(r['pooled']['seasonalNaive']['wape'])}%** for seasonal naive and **{fmt(r['pooled']['recentMean']['wape'])}%** for the recent six-month mean. Always forecasting zero gives 100% WAPE on these nonnegative demands. The model therefore needs substantial improvement despite beating some simple baselines. Zero is a diagnostic comparison, not a useful service-level policy.

Pooled brand/month WAPE is **{fmt(r['pooled']['brandMonths']['wape'])}%**. Aggregate errors cancel across products; this does not establish useful SKU purchasing accuracy. In October 2025–March 2026, the model forecast 67,864 units against 67,011 actual units (only +1.3% total bias), yet variant/month WAPE was 159.2% and brand/month WAPE was 54.5%.

Variants absent from training account for **{fmt(r['pooled']['newVariantDemandShare'])}%** of actual units across these tests. The pipeline only creates forecasts for variants with history. The audit counts those missing forecasts as zero when evaluating the full business demand, and also reports known-variant-only scores separately. A new variant may be a new product, colour or size.

**Limitations:** this is a retrospective order-history test on the currently revised snapshot, not an as-of ERP event archive. It measures the available order-based demand target, not stockout-corrected consumer demand. The February 2026 CSV/Joolan boundary changes demand definition and unknown cancellations remain. Three folds are diagnostic evidence, not a future guarantee. The existing backtest utility also skips unseen variants in its score; this audit explicitly includes their missed units.

## What the current published result contains

- 524,538 valid source rows, January 2016–October 5, 2026; training ends September 2026.
- 40,216 product/colour/size variants and 241,296 monthly forecasts.
- 62,142 forecast units for October 2026–March 2027.
- 35,788 variants (89.0%) have zero total forecast; lifecycle status is needed to distinguish valid discontinued-item zeros from missed demand.
- 3,657 variants have no model-selection validation window.
- All 40,216 variants have unknown current stock, incoming stock, selling price and purchase cost. Cancellations are incomplete.
- The saved selection-period WAPE is 80.8%, but the same period selected the model winner. That is an optimistic selection score, not independent accuracy.
- Only 823 variants select CatBoost; most use dormant-zero or other baselines. The active engine is `forecasting.py`; legacy SARIMA assignment output is not evidence that SARIMA generated this run.

## Production blockers, with code evidence

1. **Demand meaning and dates.** `m1_data_preparation.py:317` combines CSV delivered-plus-remaining units with newer Joolan ordered-minus-known-cancelled units. Monthly buckets use order creation date. Agree whether the customer needs new bookings, delivery demand, replenishment or sell-through. Map required delivery date and current open-order status for purchasing; reconcile the boundary to ERP totals.
2. **New products and seasonal assortment.** `forecasting.py:15` creates histories only for observed variants. Inputs in `forecasting.py:12` are lags, rolling summaries, calendar month, age and identifiers; no upcoming catalogue, launch date, material, collection, price, distribution or promotion features. Introduce the upcoming-season assortment and predecessor/analogue mapping, with shared category/style models and planned size/colour availability.
3. **Confidence and uncertainty.** `main.py:85` labels confidence from validation-point count. `forecasting.py:139` builds bands from six residuals from the same model-selection window. Calibrate ranges on separate held-out predictions, by horizon and demand segment. Overall coverage is dominated by zero months; inspect coverage on positive-demand and active items too. Display empirical error, sample size, bias and validation dates.
4. **Purchase logic.** `planning.py:103` effectively uses forecast minus available inventory; `m7_recommendations.py:190` sums historical undelivered balances without current delivery/status reconciliation. Add date-specific available-to-promise stock, reservations, incoming receipt dates, supplier lead-time variability, safety stock, MOQ, pack multiples and budgets. Avoid counting confirmed future orders twice. A historical backorder ratio (`m3_kpis.py:181`) is not an observed inventory outage.
5. **Job durability and scale.** `api_server.py:49` runs training in an API-process thread. Guards are process-local and startup marks running jobs failed. Move jobs into a durable worker with progress, cancellation, retries, leases and one active job per company. The last full publication took about 16m43s and the backend was observed using about 2.4 GB RAM. `database.py:713` materializes the full order ledger before inserting; chunk that stage and avoid unnecessary complete rebuilds.
6. **Shared-service security.** `product_routes.py:16` has useful localhost/shared-token protection, but no per-user roles or tenant isolation; audit actors are generic. The frontend API client does not implement a shared-service login flow. Add authenticated sessions, planner/approver/admin roles, tenant-scoped data, secret management, TLS, export permissions and named audit actors before shared hosting.
7. **Release operations.** Python requirements use broad unpinned ranges. Add a reproducible runtime lock, schema migrations, CI checks, restore-tested backups, staging, readiness/health endpoints, job metrics, data freshness alerts and drift/error monitoring. Persist trained models, code revision, dependency versions and as-of training data alongside the existing hashes and prediction files. SQLite is adequate for a controlled single-company pilot; choose a managed transactional database and separate artifact storage when shared concurrency and recovery needs require them.

## A practical route to a saleable pilot

**First milestone — reconcile data.** With Daytona 73 operations, confirm `legend73`/brand scope, COMMANDE meaning and identifiers. Build a signed-off field dictionary for products, warehouses, physical stock, reserved stock, supplier lines/ETAs, cancellations, returns, purchase costs and prices. Fetch changes plus an overlap window and reconcile edits to older orders; an order-date-only append cannot capture later cancellations. Acceptance: exact keyed joins, unexplained count/quantity differences resolved, clear quarantine and freshness indicators.

**Second milestone — improve forecasting.** Start with a manageable assortment selected with the planner. Separate replenishable carryovers, fashion launches, returning seasonal products and discontinued items. Test a category/style forecast with reconciled colour/size allocations against the existing engine; use analogue/catalogue features for launches. Measure 1-, 3- and 6-month errors, bias, new-item coverage and weighted service/cost outcomes across more origins. Use as-of data and hold out both dates and launches. Do not assume a more complex model will win.

**Third milestone — make decisions auditable.** Show actuals versus forecasts, source freshness, known orders, stock/arrivals and uncertainty by SKU. Add exception review and reason-coded planner overrides. Store frozen versions and separate model output from human decisions. Compare model-only versus planner-adjusted outcomes so overrides can be evaluated.

**Fourth milestone — operate safely.** Separate web/API/worker processes; add real user identity, durable jobs, backups, monitoring and reproducible deployment. Use a draft-only shadow pilot through at least one ordering cycle before enabling approved purchasing. Additional API workers alone do not make the current process-local job locks safe.

**Suggested pilot exit criteria (proposed targets, not achieved claims):** beat the strongest practical baseline and the current planner process on several unseen periods; reduce WAPE by at least 15% relative on the agreed active assortment; hold absolute bias below 10%; calibrate an explicitly labelled 80% range to roughly 75–85% observed coverage on sufficient held-out data; cover the complete upcoming assortment or require explicit review for every uncovered item; demonstrate a restore, retry and tenant-isolation test; agree a measurable service-level/stock-cost benefit with Daytona 73. Targets should be adjusted to lead times and the cost of overstock versus missed sales.

Market the first release as an assisted demand-planning pilot with measured business outcomes. Do not advertise a blanket accuracy percentage.

## Reproduce and inspect

Run `python -B -u audit_forecast.py` from `backend-ai`. It reads the serving database in read-only mode and writes only under `output/accuracy-audit`. Each fold's CSV contains actuals, forecasts, scenario bounds, baselines and a flag for previously unseen variants. `report.json` includes all segment metrics and monthly totals. The published run ID is `{r['runId']}`.

Method references: [rolling-origin validation](https://otexts.robjhyndman.com/fpp3/tscv.html), [hierarchical forecasting](https://otexts.robjhyndman.com/fpp3/hierarchical.html), [FastAPI guidance on heavy background computation](https://fastapi.tiangolo.com/tutorial/background-tasks/).
'''
(ROOT/'FORECAST_ACCURACY_REVIEW.md').write_text(review,encoding='utf-8')
canvas='''import {useHostTheme,useState,Stack,Row,H1,H2,Text,Button,Table,LineChart,BarChart,Divider} from "cursor/canvas";
const report = __DATA__;
export default function Review(){
 const theme=useHostTheme(); const [index,setIndex]=useState(2); const fold=report.folds[index];
 const pct=(n:number)=>n.toFixed(1)+"%";
 return <Stack gap={22} style={{padding:28,maxWidth:1120,margin:"auto",color:theme.text.primary,background:theme.bg.editor}}>
 <div><H1>Daytona 73 · Forecast accuracy review</H1><Text>October 7, 2026 · Three independent six-month historical tests · Full variant universe</Text></div>
 <div style={{padding:18,background:theme.fill.secondary}}><H2>Not ready for automated purchasing</H2><Text>The workflow runs, but product allocation errors are too high. A close six-month total hides errors across products and months. Future October 2026–March 2027 accuracy remains unknown.</Text></div>
 <Row gap={28} wrap><div><H2>{pct(report.pooled.allVariantMonths.wape)}</H2><Text>Pooled variant/month WAPE</Text></div><div><H2>{pct(report.pooled.brandMonths.wape)}</H2><Text>Pooled brand/month WAPE</Text></div><div><H2>{pct(report.pooled.newVariantDemandShare)}</H2><Text>Demand from unseen variants</Text></div></Row>
 <Text>WAPE = total absolute error ÷ actual units. Lower is better; values above 100% are possible. These are error percentages, not probabilities of correctness.</Text>
 <Divider/><H2>Historical test results</H2>
 <Table headers={["Test period","Variant/month error","Brand/month error","Total bias","New-variant unit share"]} rows={report.folds.map(f=>[f.testStart+" – "+f.testEnd,pct(f.allVariantMonths.wape),pct(f.brandMonths.wape),pct(f.allVariantMonths.bias),pct(f.missingNewProductShare)])}/>
 <Row gap={8} wrap>{report.folds.map((f,i)=><Button key={f.testStart} onClick={()=>setIndex(i)}>{f.testStart+" – "+f.testEnd}</Button>)}</Row>
 <div><H2>Brand demand: actual versus historical forecast</H2><Text>Y axis: units · X axis: calendar month · Selected test {fold.testStart}–{fold.testEnd}</Text>
 <LineChart categories={fold.monthly.map(m=>m.month)} series={[{name:"Actual units",data:fold.monthly.map(m=>m.actual),tone:"neutral"},{name:"Model forecast units",data:fold.monthly.map(m=>m.forecast),tone:"info"},{name:"Seasonal naive units",data:fold.monthly.map(m=>m.seasonalNaive),tone:"warning"}]} height={280}/>
 <Text>Source: read-only forecast.db; model trained through {fold.trainEnd}. Aggregate totals can cancel product-level mistakes.</Text></div>
 <div><H2>Variant/month error against simple baselines</H2><Text>Y axis: WAPE (%) · X axis: method · {fold.testStart}–{fold.testEnd}</Text><BarChart categories={["Current engine","Seasonal naive","Recent mean","Always zero"]} series={[{name:"WAPE (%)",data:[fold.allVariantMonths.wape,fold.seasonalNaive.wape,fold.recentMean.wape,100],tone:"neutral"}]} valueSuffix="%" height={230}/><Text>Always zero is a diagnostic comparison, not a useful service policy. Source: full-universe outer-test predictions.</Text></div>
 <H2>Scenario ranges need calibration</H2><Text>Range coverage in this test: {pct(fold.bandCoverage)} across known-variant months, versus {pct(fold.positiveActualBandCoverage)} on months with positive actual demand, including unseen variants. Zero-demand months account for {pct(fold.zeroActualMonthShare)} of evaluated rows. The current ranges have no validated confidence level.</Text>
 <Divider/><H2>What is published now</H2><Table headers={["Measure","Value"]} rows={[["October 2026–March 2027 base units","62,142"],["Product/colour/size variants","40,216"],["Zero-forecast variants","35,788 (89.0%)"],["Variants without a selection validation window","3,657"],["Stock, incoming, price and cost inputs","Unknown for all 40,216 variants"],["Data / complete training month","Through October 5, 2026 / September 2026"]]}/>
 <H2>Production priorities</H2><Table headers={["Order","Deliverable","Release evidence"]} rows={[
 ["1 · Data","Confirm Joolan field meanings, brand scope, cancellations, delivery dates, stock, reservations and supplier ETAs","ERP reconciliation, stable keys, freshness and no unexplained quantity differences"],
 ["2 · Model","Upcoming-season catalogue, product lifecycle, launch analogues, category/style forecasts and size allocations","Beat practical baselines and planner process on unseen periods; include new products"],
 ["3 · Decisions","Lead times, safety stock, MOQ/packs, time-phased arrivals, budget and reason-coded overrides","Shadow-run orders show agreed service and stock-cost benefit"],
 ["4 · Operations","Durable worker, named users/roles, tenant isolation, reproducible releases, backups and monitoring","Restart/retry, restore, isolation and load checks pass"]]}/>
 <Text>Suggested pilot gates, not achieved claims: at least 15% relative WAPE improvement versus the strongest practical baseline on the agreed assortment; absolute bias below 10%; an explicitly labelled 80% interval with approximately 75–85% held-out coverage; complete upcoming-assortment coverage or mandatory review. Agree targets with the planner and lead-time economics.</Text>
 <H2>Scope and limitations</H2><Text>Retrospective evaluation uses the current revised order snapshot, not archived as-of data. Demand meaning changes at the February 2026 CSV/Joolan boundary, cancellations are incomplete, and stockouts are not measured. Tests cover April 2025–September 2026. No published forecasts or source settings were changed.</Text>
 <Text>Run: {report.runId}. Reproduce with backend-ai/audit_forecast.py. Detailed findings: FORECAST_ACCURACY_REVIEW.md; numeric evidence: backend-ai/output/accuracy-audit/report.json.</Text>
 <Text><a href="https://otexts.robjhyndman.com/fpp3/tscv.html" style={{color:theme.text.link}}>Method: rolling-origin validation</a> · <a href="https://otexts.robjhyndman.com/fpp3/hierarchical.html" style={{color:theme.text.link}}>Hierarchical forecasting</a> · <a href="https://fastapi.tiangolo.com/tutorial/background-tasks/" style={{color:theme.text.link}}>Durable compute guidance</a></Text>
 </Stack>;
}
'''.replace('__DATA__',json.dumps(r,separators=(',',':')))
(OUT/'canvas-source.txt').write_text(canvas,encoding='utf-8')
print(json.dumps(r['pooled'],indent=2))
print('Review and canvas source saved.')
