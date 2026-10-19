"""Read-only audit of season metadata versus distinct dated repeat orders."""
import json,sqlite3
from pathlib import Path
c=sqlite3.connect(f"file:{Path('data/joolan_live.db').resolve().as_posix()}?mode=ro",uri=True)
print('Saved rates',c.execute('SELECT MIN(reorder_rate),MAX(reorder_rate),SUM(reorder_rate>0),COUNT(*) FROM recommendations').fetchone())
print('Season metadata',c.execute('SELECT season_type,season_year,COUNT(*) FROM client_orders GROUP BY season_type,season_year ORDER BY COUNT(*) DESC LIMIT 12').fetchall())
print('Dates',c.execute('SELECT MIN(date_commande),MAX(date_commande) FROM client_orders').fetchone())
repeats=c.execute("""WITH pairs AS (SELECT client_id,reference,couleur,COUNT(DISTINCT season_type||'_'||COALESCE(season_year,'missing')) AS metadata_seasons,COUNT(DISTINCT substr(date_commande,1,4)) AS years FROM client_orders WHERE true_demand>0 GROUP BY client_id,reference,couleur) SELECT COUNT(*),SUM(metadata_seasons>=2),SUM(years>=2) FROM pairs""").fetchone()
print('Buyer/article/colour pairs; repeat metadata seasons; repeat calendar years',repeats)
examples=c.execute("""SELECT reference,couleur,client_id,COUNT(DISTINCT substr(date_commande,1,4)) AS years FROM client_orders WHERE true_demand>0 GROUP BY reference,couleur,client_id HAVING years>=2 ORDER BY years DESC LIMIT 3""").fetchall()
print('Dated examples',examples)
# Ledger preserves individual document IDs and dates; the client_orders table is aggregated.
counts={};examples=[]
for (payload,) in c.execute('SELECT payload FROM order_lines'):
 r=json.loads(payload)
 if float(r.get('true_demand',0) or 0)<=0:continue
 date=str(r.get('Date_Commande',''))[:10]
 if len(date)!=10:continue
 key=(str(r.get('Reference')),str(r.get('Couleur')),str(r.get('Client')))
 counts.setdefault(key,set()).add(date[:4])
print('Ledger buyer/article/colour pairs buying in 2+ calendar years',sum(len(years)>=2 for years in counts.values()),'of',len(counts))
c.close()
