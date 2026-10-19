"""Read-only live forecast/purchase/history reconciliation; mutations tested in fixtures."""
import json,sqlite3,urllib.request
c=sqlite3.connect('file:data/joolan_live.db?mode=ro',uri=True)
with urllib.request.urlopen('http://127.0.0.1:4000/api/recommendations?scenario=base',timeout=120) as response:rows=json.load(response)
assert abs(sum(r['currentScenarioTotal'] for r in rows)-c.execute('SELECT SUM(forecast_base) FROM recommendations').fetchone()[0])<.01
for r in rows:
 sizes=r['sizeBreakdown'];assert len({s['size'] for s in sizes})==len(sizes)
 assert abs(sum(s['forecast'] for s in sizes)-r['currentScenarioTotal'])<.001
 if any(s['finalQty'] is None for s in sizes):assert r['purchaseTotals']['base'] is None
 else:assert abs(sum(s['finalQty'] for s in sizes)-r['purchaseTotals']['base'])<.001
print('Article/colour combinations:',len(rows))
print('Positive demand forecasts:',sum(r['currentScenarioTotal']>0 for r in rows))
print('Unresolved net purchase groups:',sum(r['purchaseTotals']['base'] is None for r in rows))
print('Historical size values:',sum(bool(r['historicalSizes']) for r in rows))
print('All forecast, size and purchase totals reconciled.')
try:
 urllib.request.urlopen('http://127.0.0.1:4000/api/recommendations?scenario=invalid')
except urllib.error.HTTPError as e:assert e.code==400;print('Invalid scenario rejected:',e.code)
else:raise AssertionError('Invalid scenario accepted')
c.close()
