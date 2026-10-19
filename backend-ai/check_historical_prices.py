"""Read-only discovery of saved customer-order price fields."""
import json,sqlite3
from pathlib import Path

if __name__=='__main__':
 c=sqlite3.connect('file:'+str(Path(__file__).parent/'data/joolan_source.db')+'?mode=ro',uri=True)
 print('Tables',c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
 print('Records schema',c.execute('PRAGMA table_info(records)').fetchall())
 rid='a5bf7a0c74c34ba0bffe1a60d380a5ce'
 for dataset in ('negoce_entetes','negoce_lignes','tarifs','devises'):
  sample=c.execute('SELECT payload FROM records WHERE run_id=? AND dataset=? LIMIT 1',(rid,dataset)).fetchone()
  if not sample:continue
  r=json.loads(sample[0]);print(dataset,'fields',list(r))
  print('Financial field sample',{k:v for k,v in r.items() if any(t in k.lower() for t in ('prix','remis','devise','tva','ht','ttc','montant','nature','date'))})
 print('Currency references',[json.loads(r[0]) for r in c.execute("SELECT payload FROM records WHERE run_id=? AND dataset='devises'",(rid,))])
 live=sqlite3.connect('file:'+str(Path(__file__).parent/'data/joolan_live.db')+'?mode=ro',uri=True)
 variants={tuple(r) for r in live.execute('SELECT reference,couleur,taille FROM recommendations WHERE forecast_base>0')}
 headers={str(r['Entete']):r for (raw,) in c.execute("SELECT payload FROM records WHERE run_id=? AND dataset='negoce_entetes'",(rid,)) for r in [json.loads(raw)]}
 periods={name:dict(lines=0,variants=set(),comparable=0,mismatch=0,statuses={}) for name in ('Winter 2025-26','Summer 2026')}
 for (raw,) in c.execute("SELECT payload FROM records WHERE run_id=? AND dataset='negoce_lignes'",(rid,)):
  r=json.loads(raw);h=headers.get(str(r.get('Entete')),{});date=str(h.get('Date',''))[:10]
  name='Winter 2025-26' if '2025-10-01'<=date<='2026-03-31' else 'Summer 2026' if '2026-04-01'<=date<='2026-09-30' else None
  k=tuple(str(r.get(f) or 'UNKNOWN') for f in ('Produit','Couleur','Taille'))
  if not name or k not in variants or h.get('Nature')!='COMMANDE' or str(h.get('Magasin','')).upper()!='CENTRAL':continue
  p=periods[name];status=str(r.get('Statut',''));p['statuses'][status]=p['statuses'].get(status,0)+1
  try:
   qty=float(r.get('Quantite') or 0);price=float(r.get('Prix_HT_Devise') or 0);discount=float(r.get('Remise') or 0);value=float(r.get('Total_HT_Devise') or 0)
  except (ValueError,TypeError):continue
  if qty<=0 or price<=0 or value<=0 or str(r.get('Devise') or h.get('Devise'))!='01':continue
  p['lines']+=1;p['variants'].add(k);p['comparable']+=1
  if abs(value-qty*price*(1-discount/100))>.02:p['mismatch']+=1
 print('Current positive base-forecast variants',len(variants))
 for name,p in periods.items():print(name,{**p,'variants':len(p['variants']),'coveragePercent':round(len(p['variants'])/len(variants)*100,1)})
 live.close();c.close()
