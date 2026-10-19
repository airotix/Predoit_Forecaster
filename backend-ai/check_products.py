"""Read-only consistency checks for the product KPI endpoint."""
import json,sqlite3,urllib.request,urllib.parse
from pathlib import Path
def check():
 c=sqlite3.connect(f"file:{Path('data/joolan_live.db').resolve().as_posix()}?mode=ro",uri=True)
 print('History range',c.execute('SELECT MIN(year_month),MAX(year_month),COUNT(*) FROM historical_demand').fetchone())
 print('Published rows',c.execute('SELECT COUNT(*),COUNT(DISTINCT reference),SUM(forecast_base) FROM recommendations').fetchone())
 lineage=json.loads(dict(c.execute('SELECT key,value FROM pipeline_metadata')).get('lineage','{}'))
 print('Lineage', {k:lineage.get(k) for k in ('source','cutoff','forecastStart','forecastEnd')})
 with urllib.request.urlopen('http://127.0.0.1:4000/api/products',timeout=60) as response:products=json.load(response)
 print('API products',len(products),'nonzero size breakdowns',sum(any(p['sizeBreakdown'].values()) for p in products))
 for p in products[:3]:
  ref,color=p['skuId'].split('|',1)
  history=c.execute('SELECT SUM(true_demand),SUM(cde_qte),SUM(liv_qte) FROM historical_demand WHERE reference=? AND couleur=?',(ref,color)).fetchone()
  forecast=c.execute('SELECT SUM(forecast_base) FROM recommendations WHERE reference=? AND couleur=?',(ref,color)).fetchone()[0]
  print(p['skuId'],dict(displayedUnits=p['totalUnitsSold'],history=history,forecast=forecast,diffusion=p['diffusionRate'],depth=p['depthPerCustomer'],customers=p['buyingCustomers']))
  if 'historicalDemand' in p:
   assert abs(p['historicalDemand']-history[0])<0.0001
   assert abs(sum(p['sizeBreakdown'].values())-p['historicalDemand'])<0.0001
   assert abs(p['forecastUnits']-forecast)<0.0001
 with urllib.request.urlopen('http://127.0.0.1:4000/api/products?search=105099',timeout=60) as response:filtered=json.load(response)
 assert filtered and all('105099' in p['skuId'] or '105099' in p['name'] or '105099' in p['category'] for p in filtered)
 print('Search filter passed:',len(filtered),'matches')
 for field,key in [('category','category'),('status','status')]:
  value=products[0][key]
  with urllib.request.urlopen('http://127.0.0.1:4000/api/products?'+urllib.parse.urlencode({field:value}),timeout=60) as response:filtered=json.load(response)
  assert filtered and all(p[key]==value for p in filtered)
  print(field,'filter passed:',len(filtered),'matches')
 assert len({p['skuId'] for p in products})==len(products)
 for p in products:
  assert 0<=p['diffusionRate']<=1
  assert p['reorderRate'] is None or 0<=p['reorderRate']<=1
  if 'repeatOrderRate' in p:
   assert p['repeatOrderRate'] is None or 0<=p['repeatOrderRate']<=1
   if p['reorderRate'] is not None:assert p['reorderRate']<=p['repeatOrderRate']
  if 'historicalDemand' in p and p['historicalDemand'] is not None:assert abs(sum(p['sizeBreakdown'].values())-p['historicalDemand'])<0.0001
 print('All product identities, rate bounds and size totals passed.')
 print('Season reorders above zero:',sum(p['reorderRate'] is not None and p['reorderRate']>0 for p in products))
 c.close()
if __name__=='__main__':check()
