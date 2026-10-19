"""Read-only smoke check for the running local budget API."""
import json
import time
import urllib.request
import sys

def read(path):
    with urllib.request.urlopen('http://127.0.0.1:4000/api/'+path,timeout=120) as response:
        return json.load(response)

if __name__=='__main__':
    if '--fields' in sys.argv:
        import fresh_joolan as f
        c=f.connect()
        rid=c.execute("SELECT value FROM state WHERE key='active_run'").fetchone()[0]
        schema=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='schema'",(rid,)).fetchone()[0])['tables']
        print('Product VAT fields:',[v for v in schema['produits'] if 'tva' in v['name'].lower()])
        print('VAT reference tables:',{t:cols for t,cols in schema.items() if 'tva' in t.lower()})
        print('VAT values:',c.execute("SELECT json_extract(payload,'$.Taux_TVA_Vente'),COUNT(*) FROM records WHERE run_id=? AND dataset='produits' GROUP BY 1",(rid,)).fetchall())
        c.close();sys.exit(0)
    started=time.monotonic()
    options=read('budget/options')
    print(json.dumps(dict(season=options['season']['name'],tariffs=len(options['tariffs']),currencyReferences=len(options['currencies']))),flush=True)
    report=read('budget?scenario=base')
    print(json.dumps(dict(seconds=round(time.monotonic()-started,2),scope=report['settings']['brands'],warehouses=report['settings']['warehouses'],
        coverage=report['coverage'],supplierLines=len(report['purchaseOrders']),exceptions=report['unallocatedSupplierLines'],
        budgetConfigured=report['summary']['budgetConfigured'],budgetComplete=report['summary']['budgetComplete'])),flush=True)
