"""Read-only delivery audit; never starts exports, forecasts or approved orders."""
import json,time,sqlite3,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
def get(path):
 start=time.perf_counter()
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+path,timeout=240) as response:
   raw=response.read();data=json.loads(raw) if 'json' in response.headers.get('Content-Type','') else None
   return dict(path=path,status=response.status,seconds=round(time.perf_counter()-start,2),bytes=len(raw),data=data)
 except Exception as e:return dict(path=path,error=str(e),seconds=round(time.perf_counter()-start,2))
if __name__=='__main__':
 paths=['3000/'+p for p in ('setup','dashboard','catalogue','customers','products','projection','recommendations','budget','validation')]
 paths+=['4000/api/'+p for p in ('health','forecast/readiness','forecast/job','pipeline/lineage','seasons/active','joolan/fresh','dashboard','validation','budget/reviews','catalogue?grouped=true&limit=1')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  results=list(pool.map(get,paths))
 summary=[]
 for r in results:
  data=r.pop('data',None);summary.append(r);print(r,flush=True)
  if isinstance(data,dict) and any(p in r['path'] for p in ('readiness','lineage','seasons/active','forecast/job','validation')):
   summary[-1]['details']={k:v for k,v in data.items() if k in ('ready','blockers','warnings','status','errorMessage','runId','source','freshRun','cutoff','forecastStart','forecastEnd','inputsChanged','historyChanged','sourceGenerationChanged','budget','targetMargin','currency','financialComplete','scenarioMetrics')}
   print(summary[-1]['details'],flush=True)
 c=sqlite3.connect('file:data/joolan_live.db?mode=ro',uri=True)
 lineage=json.loads(dict(c.execute('SELECT key,value FROM pipeline_metadata'))['lineage'])
 print('Source validation',lineage.get('freshReport'),flush=True)
 print('Historical coverage',c.execute('SELECT MIN(year_month),MAX(year_month),COUNT(*) FROM historical_demand').fetchone(),flush=True)
 print('Recommendations',c.execute('SELECT COUNT(*),COUNT(DISTINCT reference),SUM(forecast_base),SUM(forecast_base>0) FROM recommendations').fetchone(),flush=True)
 print('Catalogue price coverage',c.execute("SELECT COUNT(*),COUNT(p.purchase),COUNT(p.selling) FROM catalogue_skus s LEFT JOIN catalogue_prices p ON p.sku=s.sku AND p.currency='EUR' WHERE s.current=1").fetchone(),flush=True)
 print('Database quick check',c.execute('PRAGMA quick_check').fetchone(),flush=True)
 c.close()
 Path('output/delivery-audit.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
