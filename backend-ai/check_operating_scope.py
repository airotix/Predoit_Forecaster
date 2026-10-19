"""Check current scope and start a forecast only with explicit --start."""
import json,sys,time,urllib.request,urllib.error,sqlite3
def get(path):
 with urllib.request.urlopen('http://127.0.0.1:4000/api/'+path,timeout=180) as response:return json.load(response)
if __name__=='__main__':
 if '--start' in sys.argv:
  ready=get('forecast/readiness');assert ready['ready'],ready['blockers']
  request=urllib.request.Request('http://127.0.0.1:4000/api/forecast/refresh',data=b'{}',headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=30) as response:print('Forecast job:',json.load(response),flush=True)
 else:
  job=get('forecast/job');print('Forecast status:',job,flush=True)
  if job['status']=='complete':
   data=get('operating-scope');assert data['saved']
   assert set(data['scope']['brands'])=={'DAYTONA73','D73','IRON AND RESIN','IRON&RESIN'}
   assert data['scope']['warehouseRoles']['CENTRAL']=='primary'
   assert all(r!='primary' for w,r in data['scope']['warehouseRoles'].items() if w!='CENTRAL')
   lineage=get('pipeline/lineage');assert not lineage['operatingScopeChanged']
   c=sqlite3.connect('file:data/joolan_live.db?mode=ro',uri=True)
   refs={r[0] for r in c.execute('SELECT DISTINCT reference FROM recommendations')}
   brand_by_ref={r[0]:r[1] for r in c.execute('SELECT DISTINCT reference,brand FROM catalogue_skus WHERE current=1')}
   assert {brand_by_ref[r] for r in refs}<=set(data['scope']['brands'])
   print('Published scoped forecast:',{k:lineage.get(k) for k in ('runId','cutoff','forecastStart','forecastEnd','operatingScopeRevision')},flush=True)
   print('Articles:',len(refs),'published brands:',sorted({brand_by_ref[r] for r in refs}),flush=True)
   print('Warehouse balances:',data['balances'],flush=True)
   print('Budget scope:',get('budget/options')['settings']['warehouses'],flush=True)
   print('Stock known:',c.execute('SELECT COUNT(*),COUNT(current_stock) FROM recommendations').fetchone(),flush=True)
   c.close()
