"""Read-only live verification of article grouping and complete variant totals."""
import json,sqlite3,urllib.request,urllib.parse
c=sqlite3.connect('file:data/joolan_live.db?mode=ro',uri=True)
def get(offset):
 params=urllib.parse.urlencode(dict(customer='1172',offset=offset,limit=20))
 with urllib.request.urlopen('http://127.0.0.1:4000/api/orders/articles?'+params,timeout=90) as response:return json.load(response)
result=get(0)
assert len(result['articles'])>0
for article in result['articles']:
 total=c.execute("""SELECT SUM(json_extract(payload,'$.CDE_qte')),SUM(json_extract(payload,'$.LIV_qte')),COUNT(*) FROM order_lines WHERE CAST(json_extract(payload,'$.Client') AS TEXT)=? AND json_extract(payload,'$.Reference_CDE') IS ? AND substr(json_extract(payload,'$.Date_Commande'),1,10) IS ? AND json_extract(payload,'$.Reference') IS ?""",('1172',article['orderId'],article['date'],article['reference'])).fetchone()
 assert abs(article['ordered']-total[0])<.0001 and abs(article['delivered']-total[1])<.0001 and article['lineCount']==total[2]
 assert abs(sum(v['ordered'] for v in article['variants'])-article['ordered'])<.0001
 assert len({(v['color'],v['size']) for v in article['variants']})==len(article['variants'])
keys=lambda r:{(a['orderId'],a['date'],a['reference']) for a in r['articles']}
next_page=get(20)
assert not keys(result)&keys(next_page)
print('Customer 1172:',result['total'],'order articles; first',len(result['articles']),'article totals and full variant breakdowns match raw ledger; pages have no overlapping articles.')
c.close()
