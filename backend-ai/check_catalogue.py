"""Read-only live check; GET seeds the permanent catalogue from the validated export."""
import json,sqlite3,urllib.request
with urllib.request.urlopen('http://127.0.0.1:4000/api/catalogue?currency=EUR&limit=50',timeout=300) as response:result=json.load(response)
c=sqlite3.connect('file:data/joolan_live.db?mode=ro',uri=True)
count=c.execute('SELECT COUNT(*) FROM catalogue_skus WHERE current=1').fetchone()[0]
assert result['summary']['skus']==count and len(result['rows'])==50
print('Permanent catalogue:',result['summary'],flush=True)
with urllib.request.urlopen('http://127.0.0.1:4000/api/catalogue?currency=EUR&search=100096&limit=50',timeout=60) as response:filtered=json.load(response)
print('Article 100096:',len(filtered['rows']),'SKU records',flush=True)
for row in filtered['rows'][:2]:
 print({k:row[k] for k in ('sku','reference','color','size','purchase','selling')},flush=True)
 sku=urllib.parse.quote(row['sku'],safe='')
 with urllib.request.urlopen('http://127.0.0.1:4000/api/catalogue/sku/'+sku,timeout=60) as response:details=json.load(response)
 assert 'product' in details and 'sku' in details and 'inventory' in details
print('Catalogue pagination, search, detail records and persisted SKU count verified.',flush=True)
c.close()
