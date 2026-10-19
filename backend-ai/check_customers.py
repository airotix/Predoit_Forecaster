"""Read-only customer API and raw-ledger reconciliation."""
import json,sqlite3,urllib.request,urllib.parse
from pathlib import Path
c=sqlite3.connect(f"file:{Path('data/joolan_live.db').resolve().as_posix()}?mode=ro",uri=True)
def get(path):
 with urllib.request.urlopen('http://127.0.0.1:4000/api/'+path,timeout=90) as response:return json.load(response)
data=get('customers');customers=data['customers']
print('Customers',len(customers),'zero demand',sum(not r['totalUnits'] for r in customers),'zero products',sum(not r['productCount'] for r in customers))
if 'coverage' in data:
 coverage=data['coverage'];base=[r for r in customers if r['active']]
 assert coverage['activeCustomers']==len(base)
 assert coverage['orderedActiveCustomers']==sum(r['orderedInSeason'] for r in base)
 assert abs(coverage['seasonUnits']-sum(r['seasonUnits'] for r in customers))<.0001
 assert len({r['id'] for r in customers})==len(customers)
 print('Coverage reconciled:',coverage)
print('Client columns',c.execute('SELECT client_id,total_units,num_skus,first_order,last_order FROM clients ORDER BY total_units DESC LIMIT 3').fetchall())
sample=customers[:1]+[r for r in customers if r['id']=='10'][:1]
for customer in sample:
 key=customer['id'];params=urllib.parse.urlencode(dict(customer=key,offset=0,limit=50))
 orders=get('orders?'+params)
 totals=c.execute("SELECT COUNT(*),SUM(json_extract(payload,'$.true_demand')),COUNT(DISTINCT json_extract(payload,'$.Reference')),MIN(substr(json_extract(payload,'$.Date_Commande'),1,10)),MAX(substr(json_extract(payload,'$.Date_Commande'),1,10)) FROM order_lines WHERE json_extract(payload,'$.Client')=?",(key,)).fetchone()
 print('Customer',key,'API',customer,'ledger',totals,'returned order lines',len(orders['rows']),orders['total'])
 assert abs(customer['totalUnits']-totals[1])<.0001 and customer['productCount']==totals[2]
 assert orders['total']==totals[0] and all(str(r['Client'])==key for r in orders['rows'])
 if totals[0]>50:
  page=get('orders?'+urllib.parse.urlencode(dict(customer=key,offset=50,limit=50)))
  assert len(page['rows'])==min(50,totals[0]-50) and all(str(r['Client'])==key for r in page['rows'])
 print('Customer totals and order pagination passed:',key)
c.close()
