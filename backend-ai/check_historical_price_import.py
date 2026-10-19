"""Verify imported historical defaults without changing prices or drafts."""
import json,sqlite3,urllib.request
from pathlib import Path

if __name__=='__main__':
 c=sqlite3.connect('file:'+str(Path(__file__).parent/'data/joolan_live.db')+'?mode=ro',uri=True)
 summary=json.loads(c.execute("SELECT value FROM planning_state WHERE key='historical_price_import'").fetchone()[0])
 print('Import',json.dumps(summary),flush=True)
 counts=c.execute('''SELECT COUNT(*),SUM(p.selling IS NOT NULL),SUM(p.selling_source LIKE 'historical:%')
 FROM recommendations r LEFT JOIN catalogue_skus s ON s.reference=r.reference AND s.color=r.couleur AND s.size=r.taille AND s.current=1
 LEFT JOIN catalogue_prices p ON p.sku=s.sku AND p.currency='EUR' WHERE r.forecast_base>0''').fetchone()
 print('Current positive-demand variants / selling prices known / historical matches',counts,flush=True)
 assert summary['startDate']=='2026-04-01' and summary['endDate']=='2026-09-30'
 assert summary['saved']>0 and counts[1]>0
 missing=c.execute("SELECT COUNT(*) FROM catalogue_prices p WHERE p.selling_source LIKE 'historical:%' AND NOT EXISTS (SELECT 1 FROM planning_state t WHERE t.key='historical_price:'||p.sku||':'||p.currency)").fetchone()[0]
 assert missing==0
 c.close()
 for path in ('catalogue?currency=EUR&search=101126&grouped=true','budget/draft?scenario=base'):
  with urllib.request.urlopen('http://127.0.0.1:4000/api/'+path,timeout=300) as response:result=json.load(response)
  if path.startswith('catalogue'):
   assert result['historicalPriceImport']['startDate']=='2026-04-01'
   print('Catalogue HTTP 200; selling prices known',result['summary']['sellingKnown'],flush=True)
  else:
   historical=[r for r in result['rows'] if r.get('priceBasis','').startswith('Previous season')]
   assert historical
   assert all(r['orderUnitPrice'] is not None for r in historical if not any(e['id']==r['id'] and 'unitPrice' in e for e in result['draft']['edits']))
   print('Budget HTTP 200; historical defaults',len(historical),'of',len(result['rows']),'draft version',result['draft']['version'],'stale',result['draft']['stale'],flush=True)
