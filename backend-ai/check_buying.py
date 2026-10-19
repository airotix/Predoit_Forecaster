"""Read-only live check of buying-plan simulation and its validation gate."""
import json
import urllib.request
import urllib.error

def post(path,body):
 request=urllib.request.Request('http://127.0.0.1:4000/api/budget/'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=300) as response:return json.load(response)

if __name__=='__main__':
 result=post('simulate',dict(scenario='base',edits=[],quantityBasis='forecast'))
 assert result['quantityBasis']=='forecast'
 assert all(r['quantity']==__import__('math').ceil(r['forecast']) for r in result['rows'])
 print('Whole article groups:',len(result['articlePlan']['articles']),flush=True)
 print(json.dumps(dict(rows=len(result['rows']),summary=result['summary'],covered={k:v for k,v in result['covered'].items() if k not in ('supplierOrders','rowIds')},blockers=result['blockers'],supplierPriceVariants=sum(bool(r['quotes']) for r in result['rows'])),indent=2),flush=True)
 # Empty selection must be refused before any review is written.
 try:post('validate',dict(scenario='base',edits=[],selected=[],revision=result['revision'],quantityBasis='forecast'))
 except urllib.error.HTTPError as e:
  print('Empty-selection validation gate:',e.code,e.read().decode())
 else:raise AssertionError('Empty selection was incorrectly validated.')
