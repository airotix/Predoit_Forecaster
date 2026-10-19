"""Fresh-only, versioned Joolan extraction. No access to legacy CSVs or snapshots."""
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sqlite3
import uuid
import urllib.error
import urllib.parse
import urllib.request

from joolan_client import Client, ExportError, SourceChangedError, RateLimitError, field, spool_value, unspool_value, identifier, sql_value

BASE=Path(__file__).resolve().parent
SOURCE_DB=BASE/'data/joolan_source.db'
REQUIRED_TABLES=('negoce_entetes','negoce_lignes','produits','skus','negoce_clients')
OPTIONAL_TABLES=('fournisseurs','tarifs','tarifsproduits','produits_min_max','magasins','commandes','commandes_magasins','commandes_produits','commandes_quantites','devises')
SECRET_FIELDS=('motpasse','password','mot_de_passe','api_key','api-key','secret','token','logo')
REQUIRED_FIELDS={
 'negoce_entetes':['Entete','Date','Nature','Client','Magasin'],
 'negoce_lignes':['Ligne','Entete','Produit','Couleur','Taille','Quantite','Quantite_Livree'],
 'produits':['Produit'], 'skus':['Produit','Couleur','Taille'], 'negoce_clients':['Client']}
FIELD_CONTRACT={
 'orders':dict(source='query.do: negoce_entetes + negoce_lignes',fields=['Entete','Ligne','Date','Nature','Client','Magasin','Produit','Couleur','Taille','Quantite','Quantite_Livree','Quantite_Annulee','Statut','Date_Livraison_Souhaitee','Date_Livraison_Prevue']),
 'catalogue':dict(source='query.do: produits + skus (includes non-ecommerce products)',fields=['Produit','Couleur','Taille','Sku','EAN','Designation','Saison','Collection','Marque','Famille','Modele','Matiere','Actif','Fournisseur','Conditionnement_Achat','Prix_Achat','Prix_Vente','Devise']),
 'inventory':dict(source='GET image-full-stocks.do',fields=['Magasin','Produit','Couleur','Taille','Sku','En_Stock','Disponible','En_Reservation','Attribue','En_Preparation','En_Livraison','Reliquat_Fournisseur','En_BL']),
 'supply':dict(source='query.do: live schema discovery; mappings require review',fields=['Fournisseur','Magasin','Produit','Couleur','Taille','Quantite','Quantite_Livree','Date_Livraison','Statut','Prix_Achat','Devise']),
}

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def encode(value): return json.dumps(value,ensure_ascii=False,default=spool_value,allow_nan=False)
def connect(path=None):
    path=Path(path or SOURCE_DB);path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path,timeout=30);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA temp_store=MEMORY');c.execute('PRAGMA cache_size=-64000')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,status TEXT NOT NULL,config TEXT NOT NULL,created_at TEXT,updated_at TEXT,phase TEXT,error TEXT,report TEXT,pid INTEGER);
      CREATE UNIQUE INDEX IF NOT EXISTS one_live_export ON runs((1)) WHERE status IN ('queued','running');
      CREATE TABLE IF NOT EXISTS datasets(run_id TEXT,dataset TEXT,metadata TEXT NOT NULL,PRIMARY KEY(run_id,dataset));
      CREATE TABLE IF NOT EXISTS records(run_id TEXT,dataset TEXT,record_key TEXT,payload TEXT NOT NULL,PRIMARY KEY(run_id,dataset,record_key));
      CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
    ''');return c

def create_run(config,path=None):
    # Keys never enter durable configuration.
    config={k:config[k] for k in ('enseigne','documentType','throughDate','warehouses','brands') if k in config}
    config.setdefault('brands',['DAYTONA73'])
    if not config['brands']:raise ValueError('Select at least one product brand.')
    date=dt.date.fromisoformat(config['throughDate'])
    if date>dt.datetime.now(dt.timezone.utc).date():raise ValueError('Export end date cannot be in the future.')
    if config['documentType']!='COMMANDE':raise ValueError('This source is configured for COMMANDE customer orders.')
    if not config.get('warehouses'):raise ValueError('Specify the Joolan warehouses supplying Daytona 73; retail stock must not be silently pooled.')
    c=connect(path);rid=uuid.uuid4().hex
    try:
        with c:c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',(rid,'queued',encode(config),now(),now(),'waiting for worker',None,None,None))
    except sqlite3.IntegrityError:raise ValueError('Another fresh export is already running.') from None
    finally:c.close()
    return rid

def update(c,rid,**changes):
    changes['updated_at']=now()
    with c:c.execute('UPDATE runs SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',(*changes.values(),rid))

def status(path=None):
    c=connect(path)
    try:
        recover_interrupted(c)
        row=c.execute('SELECT id,status,config,created_at,updated_at,phase,error,report FROM runs ORDER BY created_at DESC LIMIT 1').fetchone()
        active=c.execute("SELECT value FROM state WHERE key='active_run'").fetchone()
        result=dict(mode='joolan_fresh',activeRun=active[0] if active else None,contract=FIELD_CONTRACT,run=None)
        discovery=c.execute("SELECT value FROM state WHERE key='discovery'").fetchone()
        result['discovery']=json.loads(discovery[0]) if discovery else None
        if row:
            result['run']=dict(zip(('id','status','config','createdAt','updatedAt','phase','error','report'),row))
            for key in ('config','report'):
                result['run'][key]=json.loads(result['run'][key]) if result['run'][key] else None
            result['run']['datasets']=[dict(name=d,**json.loads(m)) for d,m in c.execute('SELECT dataset,metadata FROM datasets WHERE run_id=?',(row[0],))]
        return result
    finally:c.close()

def process_alive(pid):
    if not pid:return False
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ctypes.get_last_error()!=87 # Access denied is not evidence of death.
        try:
            code=wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle,ctypes.byref(code)) or code.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

def recover_interrupted(c):
    for rid,pid,updated in c.execute("SELECT id,pid,updated_at FROM runs WHERE status IN ('queued','running')").fetchall():
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(updated)).total_seconds()
        if age>60 and not process_alive(pid):
            update(c,rid,status='needs_credentials',phase='Worker interrupted',error='The export worker stopped. Re-enter the key to resume saved pages.')

def claim_resume(rid,path=None):
    c=connect(path)
    try:
        with c:
            changed=c.execute("UPDATE runs SET status='queued',pid=NULL,updated_at=? WHERE id=? AND status='needs_credentials'",(now(),rid)).rowcount
            if changed!=1:raise ValueError('This run is not waiting to resume.')
    except sqlite3.IntegrityError:raise ValueError('Another export is already running.') from None
    finally:c.close()

def rows(c,rid,dataset):
    for (payload,) in c.execute('SELECT payload FROM records WHERE run_id=? AND dataset=? ORDER BY record_key',(rid,dataset)):yield json.loads(payload,object_hook=unspool_value)

def discover(client):
    tables={}
    for r in client.query('SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COLUMN_KEY FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION'):
        tables.setdefault(str(field(r,'TABLE_NAME')),[]).append(dict(name=field(r,'COLUMN_NAME'),type=field(r,'DATA_TYPE'),key=field(r,'COLUMN_KEY')))
    if not tables:raise ValueError('No schema metadata returned. Enable api_query and metadata access.')
    return tables

def brand_scope(table,brands):
    brand_filter='`Marque` IN ('+', '.join(sql_value(v) for v in brands)+')'
    if table=='produits':return brand_filter
    if table in ('skus','negoce_lignes','tarifsproduits','produits_min_max','commandes_produits','commandes_quantites'):
        return '`Produit` IN (SELECT `Produit` FROM `produits` WHERE '+brand_filter+')'
    return ''

def table_scope(table,config):
    scope=brand_scope(table,config.get('brands',['DAYTONA73']))
    if table=='stocks':
        warehouses='`Magasin` IN ('+', '.join(sql_value(v) for v in config['warehouses'])+')'
        products='`Produit` IN (SELECT `Produit` FROM `produits` WHERE '+brand_scope('produits',config.get('brands',['DAYTONA73']))+')'
        scope=warehouses+' AND '+products
    return scope

def export_table(c,rid,client,table,config):
    prior=c.execute('SELECT metadata FROM datasets WHERE run_id=? AND dataset=?',(rid,table)).fetchone()
    meta=json.loads(prior[0]) if prior else None
    if meta:
        stored=c.execute('SELECT COUNT(*) FROM records WHERE run_id=? AND dataset=?',(rid,table)).fetchone()[0]
        if meta.get('complete'):
            # Completed datasets are immutable pages of this export generation.
            # Retrying inventory must not redownload history because the ERP changed.
            if stored!=meta.get('exported',0) or stored!=meta['expected']:
                raise ValueError(f'{table}: saved complete export has inconsistent row counts. Start a new export; saved data was preserved.')
            return
        if stored!=meta.get('exported',0) or client.count(table,meta['where'])!=meta['expected']:
            with c:
                c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,table))
                c.execute('DELETE FROM datasets WHERE run_id=? AND dataset=?',(rid,table))
            meta=None
    if meta and meta.get('complete'):return
    if not meta:
        # New run IDs always get new remote boundaries; never reuse old checkpoints.
        trade=table in ('negoce_entetes','negoce_lignes')
        meta=client.table_snapshot(table,lambda message:None,config['documentType'] if trade else '',end_date=config['throughDate'] if trade else '',extra_where=table_scope(table,config))
        meta['projection']=[name for name in meta['columns'] if str(name).lower() not in SECRET_FIELDS]
        meta['complete']=False
    if not meta.get('primary') and meta.get('exported'):
        with c:c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,table))
        meta['exported']=0;meta['cursor']=None
    buffer=[];seq=int(meta.get('exported',0))
    def checkpoint():
        with c:
            c.executemany('INSERT INTO records VALUES(?,?,?,?)',buffer)
            c.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(rid,table,encode(meta)))
        buffer.clear()
        update(c,rid,phase=f'{table}: {meta.get("exported",0):,} / {meta["expected"]:,}')
    try:
        for record in client.table_rows(table,10000,lambda message:None,meta,checkpoint=checkpoint):
            key=encode([record[k] for k in meta['primary']]) if meta.get('primary') else str(seq)
            buffer.append((rid,table,key,encode(record)));seq+=1
    except SourceChangedError:
        with c:
            c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,table))
            c.execute('DELETE FROM datasets WHERE run_id=? AND dataset=?',(rid,table))
        raise
    meta['complete']=True;meta['completedAt']=now();checkpoint()

def full_stock(key,config):
    params=urllib.parse.urlencode({'enseigne':config['enseigne'],'api-key':key,'Magasins':';'.join(config['warehouses'])})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    try:
        request=urllib.request.Request('https://go.joolan.com/api/v2/image-full-stocks.do?'+params,headers={'Accept':'application/json'})
        with urllib.request.build_opener(NoRedirect).open(request,timeout=120) as response:payload=json.load(response)
    except urllib.error.HTTPError as e:
        if e.code==429:raise RateLimitError('Stock export quota reached. Resume after the quota resets.') from None
        raise ValueError(f'Stock export returned HTTP {e.code}; check api_stock permission.') from None
    except (OSError,ValueError):raise ValueError('Stock export failed or returned invalid JSON.') from None
    if not isinstance(payload,dict) or payload.get('result')!='ok':
        reason=str(payload.get('error_message','Unexpected response')) if isinstance(payload,dict) else 'Unexpected response'
        reason=re.sub(r'https?://\S+','[upstream URL hidden]',reason.replace(key,'[hidden]'))[:300]
        if re.search(r'hourly limit|rate.?limit|quota|too many requests',reason,re.I):
            raise RateLimitError('Stock export quota reached. Resume after the quota resets.')
        raise ValueError('Joolan stock endpoint rejected the request: '+reason)
    if not isinstance(payload.get('data'),list) or any(not isinstance(r,dict) for r in payload['data']):
        raise ValueError('Stock endpoint returned an unexpected data structure.')
    return payload['data']

def fetch_inventory(c,rid,client,key,config,schema,stock_fetch):
    """Fetch fresh balances with the stock endpoint or the permitted Query API.

    The SQL table may be sparse. Missing warehouse/SKU rows remain unknown;
    only the dedicated full-stock endpoint promises explicit zero rows.
    """
    try:
        stock=stock_fetch(key,config)
        return iter(stock),dict(source='image-full-stocks.do',explicitZeroCoverage=True,fetchedAt=now())
    except ValueError as error:
        names={str(col['name']).lower() for col in schema.get('stocks',[])}
        required={'magasin','produit','couleur','taille','en_stock','disponible','en_reservation'}
        if not required<=names:raise error
        update(c,rid,phase='Stock endpoint unavailable; downloading fresh stock through Query API')
        # The Query API permission already grants read access to these tables.
        # Only selected stores and brands are read; no old stock cache is used.
        export_table(c,rid,client,'stocks',config)
        meta=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='stocks'",(rid,)).fetchone()[0])
        previous=c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='inventory'",(rid,)).fetchone()
        captured=meta.get('completedAt') or (json.loads(previous[0]).get('fetchedAt') if previous else None)
        return rows(c,rid,'stocks'),dict(source='query.do:stocks',explicitZeroCoverage=False,
            fetchedAt=captured,endpointWarning=str(error)[:400],notice='Missing stock rows are unknown, not assumed zero.')

def number(value,allow_negative=False):
    if value is None or isinstance(value,bool) or str(value).strip()=='':raise ValueError('Missing numeric value')
    n=float(value)
    if not math.isfinite(n) or (not allow_negative and n<0):raise ValueError('Invalid quantity')
    return n

def variant(r):
    key=tuple(str(field(r,k) or '').strip() for k in ('Produit','Couleur','Taille'))
    if not key[0]:raise ValueError('Missing product identity')
    return key

def warehouse_code(value,selected):
    raw=str(value or '').strip()
    if raw in selected:return raw
    matches=[code for code in selected if str(code).strip().casefold()==raw.casefold()]
    if len(matches)!=1:raise ValueError('Unexpected or ambiguous warehouse code')
    return matches[0]

class NegativeOrderAdjustment(ValueError):
    """Signed adjustment kept raw but not used as positive booked-order demand."""

def available_stock(c,rid,warehouses):
    """Only explicit coverage of every selected warehouse produces a balance."""
    values={}
    for r in rows(c,rid,'inventory'):
        raw_warehouse=str(field(r,'Magasin') or '').strip()
        if not any(raw_warehouse.casefold()==w.casefold() for w in warehouses):continue
        k=variant(r);warehouse=warehouse_code(raw_warehouse,warehouses)
        if warehouse in warehouses:
            balances=values.setdefault(k,{})
            if warehouse in balances:raise ValueError('Duplicate warehouse/SKU stock row.')
            balances[warehouse]=number(field(r,'Disponible'),True)
    return {k:sum(v.values()) for k,v in values.items() if set(v)==set(warehouses)}

def order_quantities(line,header):
    """Documented 0=draft, 1=confirmed, 2=cancelled, 3=closed.

    Closed does not specify why the remainder was unfulfilled. Preserve booked
    demand and mark cancellation completeness unknown, rather than inventing it.
    """
    ordered=number(field(line,'Quantite'),True);delivered=number(field(line,'Quantite_Livree'))
    if ordered<0:raise NegativeOrderAdjustment('Negative ordered quantity is a signed adjustment, not a positive booked order.')
    status=field(line,'Statut')
    if status is None:status=field(header,'Statut')
    if status is not None:
        status=number(status)
        if status not in (0,1,2,3):raise ValueError('Unknown order status')
        if status==0 and delivered:raise ValueError('Unconfirmed order has deliveries')
    cancelled=field(line,'Quantite_Annulee')
    if cancelled is not None:
        cancelled=number(cancelled);known=True
    elif status is None:raise ValueError('No Quantite_Annulee or documented Statut mapping')
    elif status==2:
        cancelled=max(0.,ordered-delivered);known=True
    else:
        cancelled=0.;known=delivered>=ordered
    if cancelled>ordered or (cancelled>0 and cancelled+delivered>ordered):raise ValueError('Cancelled quantities conflict with ordered/delivered quantities')
    remaining=0. if status in (0,2,3) else max(0.,ordered-delivered-cancelled)
    return dict(ordered=ordered,delivered=delivered,cancelled=cancelled,known=known,status=status,eligible=status!=0,remaining=remaining,overdelivered=max(0.,delivered-ordered))

def validate(c,rid,schema,config):
    blockers=[];warnings=[];coverage={};issues=[]
    for table,required in REQUIRED_FIELDS.items():
        names={str(col['name']).lower() for col in schema.get(table,[])}
        missing=[name for name in required if name.lower() not in names]
        coverage[table]=dict(columns=sorted(names),missing=missing)
        if missing:blockers.append(table+': missing '+', '.join(missing))
    catalogue={}
    for r in rows(c,rid,'skus'):
        try:k=variant(r)
        except ValueError:
            blockers.append('Catalogue row has no product identity.');continue
        if k in catalogue:blockers.append('Duplicate catalogue variant identity');break
        catalogue[k]=r
    stocks={};stock_count=0
    for r in rows(c,rid,'inventory'):
        stock_count+=1
        try:
            warehouse=warehouse_code(field(r,'Magasin'),config['warehouses'])
            k=variant(r)
            number(field(r,'En_Stock'),True);available=number(field(r,'Disponible'),True)
            number(field(r,'En_Reservation'),True)
            if warehouse not in config['warehouses']:raise ValueError('Unexpected warehouse')
            if warehouse in stocks.get(k,set()):raise ValueError('Duplicate stock row')
            stocks.setdefault(k,set()).add(warehouse)
        except (ValueError,TypeError):issues.append('Invalid stock row')
    if not catalogue:blockers.append('Full SKU catalogue is empty.')
    if not stock_count:blockers.append('Full stock export is empty.')
    absent=sum(set(config['warehouses'])-stocks.get(k,set())!=set() for k in catalogue)
    if absent:warnings.append(f'{absent} catalogue variants lack an explicit row for every requested warehouse; their stock remains unknown.')
    # Validate unique compatible headers in SQL, without multiplying reused IDs.
    c.execute('DROP TABLE IF EXISTS temp.order_headers')
    c.execute('CREATE TEMP TABLE order_headers(id TEXT,store TEXT,customer TEXT,payload TEXT)')
    c.executemany('INSERT INTO order_headers VALUES(?,?,?,?)',((str(field(r,'Entete')),str(field(r,'Magasin')),str(field(r,'Client')),encode(r)) for r in rows(c,rid,'negoce_entetes')))
    c.execute('CREATE INDEX temp.header_key ON order_headers(id,store,customer)')
    resolve_header=header_resolver(c)
    valid=0;unknown_cancellations=0;missing_catalogue=0;invalid=0;drafts=0;status_counts={}
    adjustments=0;adjustment_units=0.;adjustment_examples=[];overdeliveries=0;ordered_units=0.
    customers={str(field(r,'Client')) for r in rows(c,rid,'negoce_clients')}
    product_ids=[str(field(r,'Produit')) for r in rows(c,rid,'produits')]
    product_set=set(product_ids)
    if len(product_ids)!=len(product_set):blockers.append('Duplicate product identities need a catalogue mapping.')
    if any(k[0] not in product_set for k in catalogue):blockers.append('SKU catalogue contains unmatched products.')
    for r in rows(c,rid,'negoce_lignes'):
        try:
            h=resolve_header(r)
            order_date=dt.date.fromisoformat(str(field(h,'Date'))[:10])
            if order_date>dt.date.fromisoformat(config['throughDate']):raise ValueError('Order outside export dates')
            if field(h,'Nature')!=config['documentType']:raise ValueError('Wrong document type')
            if str(field(h,'Client')) not in customers:raise ValueError('Unmatched customer')
            q=order_quantities(r,h)
            status_counts[str(q['status'])]=status_counts.get(str(q['status']),0)+1
            if not q['eligible']:drafts+=1;continue
            ordered_units+=q['ordered']
            if q['overdelivered']:overdeliveries+=1
            if not q['known']:unknown_cancellations+=1
            if variant(r) not in catalogue:missing_catalogue+=1
            valid+=1
        except NegativeOrderAdjustment:
            adjustments+=1;adjustment_units+=abs(number(field(r,'Quantite'),True))
            if len(adjustment_examples)<20:adjustment_examples.append(dict(line=field(r,'Ligne'),ordered=field(r,'Quantite'),delivered=field(r,'Quantite_Livree')))
        except (ValueError,TypeError):invalid+=1
    if invalid:blockers.append(f'{invalid} order lines have invalid quantities/dates or ambiguous/unmatched headers. All are retained in raw data.')
    if not valid:blockers.append('No valid customer order lines.')
    if adjustments:
        warnings.append(f'{adjustments} negative adjustment lines ({adjustment_units:g} absolute units) are retained raw and excluded from the positive booked-order forecast; review them before using a net-sales target.')
        if adjustments/max(1,valid+adjustments)>0.001 or adjustment_units/max(1.,ordered_units)>0.001:
            blockers.append('Negative adjustments exceed 0.1% of lines or ordered units. Review the signed-demand mapping before forecasting.')
    if overdeliveries:warnings.append(f'{overdeliveries} over-delivered lines retain actual delivered quantities. Booked demand uses the original ordered amount and open balance is clamped to zero.')
    if unknown_cancellations:warnings.append(f'{unknown_cancellations} confirmed/closed lines lack explicit partial-cancellation quantities. Forecasts use booked order demand, not certified net sales. Closed orders have zero open balance.')
    if drafts:warnings.append(f'{drafts} unconfirmed order lines are retained in raw storage and excluded from training.')
    line_fields={str(col['name']).lower() for col in schema.get('negoce_lignes',[])}
    header_fields={str(col['name']).lower() for col in schema.get('negoce_entetes',[])}
    if 'quantite_annulee' not in line_fields and 'statut' not in line_fields|header_fields:blockers.append('Quantite_Annulee or the documented Statut field is required to interpret orders.')
    if missing_catalogue:blockers.append(f'{missing_catalogue} order lines do not match the full SKU catalogue.')
    if issues:blockers.append(f'{len(issues)} invalid inventory rows.')
    warnings.extend(['Stock quantities are preserved separately; supplier backlog and goods in delivery are not added without receipt dates and overlap rules.',
      'Purchase costs, price tax/currency basis, supplier receipt dates, lead times and product lifecycle require live mapping review before purchase approval.',
      'Remote tables are count-verified reads, not a transactional Joolan snapshot.'])
    return dict(readyForForecast=not blockers,readyForPurchasing=False,blockers=list(dict.fromkeys(blockers)),warnings=warnings,fieldCoverage=coverage,
      catalogueVariants=len(catalogue),stockRows=stock_count,orderLines=valid,invalidOrderLines=invalid,missingStockVariants=absent,excludedDraftLines=drafts,statusCounts=status_counts,cancellationsComplete=not unknown_cancellations,
      excludedAdjustmentLines=adjustments,excludedAdjustmentUnits=adjustment_units,adjustmentExamples=adjustment_examples,overdeliveredLines=overdeliveries,
      demandDefinition='Booked customer-order demand; drafts excluded, cancelled remainders excluded, unknown partial cancellations disclosed.' if unknown_cancellations else 'Customer ordered units minus explicit or status-confirmed cancelled quantities.',
      exportedThrough=config['throughDate'],enseigne=config['enseigne'],warehouses=config['warehouses'],brands=config.get('brands',['DAYTONA73']),orderType=config['documentType'],source='joolan_fresh')

def matching_header(c,r):
    query='SELECT payload FROM order_headers WHERE id=?';params=[str(field(r,'Entete'))]
    for col,fieldname in [('store','Magasin'),('customer','Client')]:
        if field(r,fieldname) is not None:query+=' AND '+col+'=?';params.append(str(field(r,fieldname)))
    found=c.execute(query+' LIMIT 2',params).fetchall()
    if len(found)!=1:raise ValueError('No unique header')
    return json.loads(found[0][0],object_hook=unspool_value)

def header_resolver(c):
    """Bounded per-validation cache; repeated item lines share their header read."""
    cache={}
    def resolve(r):
        key=tuple(None if field(r,name) is None else str(field(r,name)) for name in ('Entete','Magasin','Client'))
        if key not in cache:
            value=matching_header(c,r)
            if len(cache)>=10000:cache.clear()
            cache[key]=value
        return cache[key]
    return resolve

def reconcile_exports(c,rid,client,config,schema):
    """Recheck full scoped boundaries, counts and captured fields before activation."""
    audit=[];changed=[];extensions={}
    downloaded={r[0] for r in c.execute('SELECT dataset FROM datasets WHERE run_id=?',(rid,))}
    missing=[t for t in (*REQUIRED_TABLES,*OPTIONAL_TABLES) if t in schema and t not in downloaded]
    if missing:raise ValueError('Source changed or saved export incomplete; automatic repair required for: '+', '.join(missing))
    for table,text in c.execute("SELECT dataset,metadata FROM datasets WHERE run_id=? AND dataset NOT IN ('schema','inventory')",(rid,)).fetchall():
        meta=json.loads(text)
        stored=c.execute('SELECT COUNT(*) FROM records WHERE run_id=? AND dataset=?',(rid,table)).fetchone()[0]
        trade=table in ('negoce_entetes','negoce_lignes')
        current=client.table_snapshot(table,lambda message:None,config['documentType'] if trade else '',
            end_date=config['throughDate'] if trade else '',extra_where=table_scope(table,config))
        sample=c.execute('SELECT payload FROM records WHERE run_id=? AND dataset=? LIMIT 1',(rid,table)).fetchone()
        expected_fields={str(f).casefold() for f in current.get('columns',[]) if str(f).lower() not in SECRET_FIELDS}
        captured_fields={str(f).casefold() for f in json.loads(sample[0])} if sample else set()
        match=(meta.get('complete') and stored==meta.get('expected')==current.get('expected') and
               (not stored or expected_fields<=captured_fields) and
               meta.get('upper')==current.get('upper') and set(meta.get('columns',[]))==set(current.get('columns',[])))
        audit.append(dict(table=table,stored=stored,expected=current['expected'],complete=bool(match),missingFields=sorted(expected_fields-captured_fields) if stored else [],checkedAt=now()))
        if not match:
            changed.append(table)
            # The first pass always reads the full history. Extend a completed
            # keyset only when the old bounded count is unchanged and the new
            # scoped count grew: never use max-ID-only sync across generations.
            if (meta.get('complete') and meta.get('primary') and stored==meta.get('expected') and stored>0 and
                current.get('primary')==meta['primary'] and current.get('expected',0)>stored and
                set(meta.get('columns',[]))==set(current.get('columns',[])) and expected_fields<=captured_fields and
                meta.get('cursor')==meta.get('upper') and client.count(table,meta['where'])==stored):
                extensions[table]={**meta,'complete':False,'expected':current['expected'],'upper':current['upper'],
                    'where':current['where'],'extendedFrom':stored,'extensionCount':meta.get('extensionCount',0)+1}
    if changed:
        with c:
            for table in changed:
                if table in extensions:
                    c.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(rid,table,encode(extensions[table])))
                else:
                    c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,table))
                    c.execute('DELETE FROM datasets WHERE run_id=? AND dataset=?',(rid,table))
        raise ValueError('Source changed or saved export incomplete; automatic repair required for: '+', '.join(changed))
    groups=dict(orders=(('negoce_entetes','negoce_lignes'),('Statut','Quantite_Annulee','Prix_HT_Devise','Remise','Total_HT_Devise','Date_Livraison_Souhaitee','Date_Livraison_Prevue')),
        catalogue=(('produits','skus'),('Saison','Collection','Actif','Conditionnement_Achat','Prix_Achat','Devise')),
        supply=(('commandes','commandes_produits','commandes_quantites'),('Fournisseur','Statut','Devise','Date_Livraison','Quantite','Quantite_Livree','Prix_Achat_Devise')))
    field_audit={}
    for name,(tables,fields) in groups.items():
        exposed={str(col['name']).casefold() for table in tables for col in schema.get(table,[])}
        field_audit[name]=dict(available=[f for f in fields if f.casefold() in exposed],unavailable=[f for f in fields if f.casefold() not in exposed])
    return dict(checkedAt=now(),tables=audit,allComplete=True,fieldAudit=field_audit,
                unavailableTables=[t for t in OPTIONAL_TABLES if t not in schema],
                notice='Fresh full extraction and repeated scoped counts/primary-key boundaries. Joolan does not provide a cross-table transaction snapshot.')


def run_export(rid,key,path=None,client_factory=Client,stock_fetch=full_stock,reconcile=False):
    c=connect(path);client=None
    try:
        row=c.execute('SELECT config,status FROM runs WHERE id=?',(rid,)).fetchone()
        if not row or row[1]!='queued':return
        config=json.loads(row[0])
        with c:
            if c.execute("UPDATE runs SET status='running',pid=?,updated_at=?,phase='Discovering live schema',error=NULL WHERE id=? AND status='queued'",(os.getpid(),now(),rid)).rowcount!=1:return
        client=client_factory('https://go.joolan.com',config['enseigne'],key)
        saved=c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='schema'",(rid,)).fetchone()
        if saved and not reconcile:schema=json.loads(saved[0])['tables']
        else:
            schema=discover(client)
            with c:
                if saved:
                    previous=json.loads(saved[0])['tables']
                    for table in set(previous)|set(schema):
                        if previous.get(table)!=schema.get(table):
                            c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,table))
                            c.execute('DELETE FROM datasets WHERE run_id=? AND dataset=?',(rid,table))
                c.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(rid,'schema',encode(dict(complete=True,tables=schema))))
        absent=[t for t in REQUIRED_TABLES if t not in schema]
        if absent:raise ValueError('Required tables unavailable: '+', '.join(absent)+'. Review the live schema mapping.')
        optional=[t for t in OPTIONAL_TABLES if t in schema]
        # Only export relevant procurement tables discovered by their fields.
        supply=[t for t,cols in schema.items() if {'fournisseur','produit','quantite','quantite_livree','date_livraison'}<={str(col['name']).lower() for col in cols} and t not in REQUIRED_TABLES]
        for table in dict.fromkeys(list(REQUIRED_TABLES)+optional+supply):
            if reconcile:
                prior=c.execute('SELECT metadata FROM datasets WHERE run_id=? AND dataset=?',(rid,table)).fetchone()
                if prior:
                    meta=json.loads(prior[0])
                    stored=c.execute('SELECT COUNT(*) FROM records WHERE run_id=? AND dataset=?',(rid,table)).fetchone()[0]
                    sample=c.execute('SELECT payload FROM records WHERE run_id=? AND dataset=? LIMIT 1',(rid,table)).fetchone()
                    expected_fields={str(f).casefold() for f in meta.get('columns',[]) if str(f).lower() not in SECRET_FIELDS}
                    fields={str(f).casefold() for f in json.loads(sample[0])} if sample else set()
                    if meta.get('complete') and (stored!=meta.get('expected') or (stored and not expected_fields<=fields)):
                        with c:
                            c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,table))
                            c.execute('DELETE FROM datasets WHERE run_id=? AND dataset=?',(rid,table))
            export_table(c,rid,client,table,config)
        update(c,rid,phase='Fetching current full stock (including zeros)')
        stock,inventory_meta=fetch_inventory(c,rid,client,key,config,schema,stock_fetch)
        product_ids={str(field(r,'Produit')) for r in rows(c,rid,'produits')}
        stock_count=0
        with c:
            c.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(rid,'inventory'))
            for r in stock:
                if variant(r)[0] not in product_ids:continue
                k=encode([field(r,'Magasin'),*variant(r)])
                c.execute('INSERT INTO records VALUES(?,?,?,?)',(rid,'inventory',k,encode(r)))
                stock_count+=1
            c.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(rid,'inventory',encode(dict(complete=True,count=stock_count,**inventory_meta))))
        audit=None
        if reconcile:
            update(c,rid,phase='Reconciling all exported tables against live counts and fields')
            audit=reconcile_exports(c,rid,client,config,schema)
        update(c,rid,phase='Validating joins, quantities, catalogue and warehouse coverage')
        report=validate(c,rid,schema,config)
        report['inventorySource']=inventory_meta['source']
        report['inventoryAsOf']=inventory_meta.get('fetchedAt')
        if audit:report['exportAudit']=audit
        if inventory_meta.get('endpointWarning'):report['warnings'].append('Stock endpoint unavailable; fresh Query API balances used. Missing warehouse/SKU rows remain unknown.')
        update(c,rid,status='validated' if report['readyForForecast'] else 'needs_mapping',phase='Review data contract',report=encode(report))
    except SourceChangedError:
        update(c,rid,status='needs_credentials',phase='Source changed; automatic repair required',error='Source changed during export. Retry the affected saved table before forecasting.')
    except RateLimitError:
        update(c,rid,status='needs_credentials',phase='Paused at Joolan quota',error='Quota reached. Resume this new export after reset; re-enter the API key.')
    except ExportError as error:
        message=re.sub(r'https?://\S+','[upstream URL hidden]',str(error).replace(key,'[hidden]'))
        message=re.split(r'\s*:\s*SELECT\s',message,flags=re.I)[0]
        phase='Transient connection failure' if 'Connection failed' in message or 'valid JSON' in message else 'Joolan access or query needs attention'
        update(c,rid,status='needs_credentials',phase=phase,error=message[:600])
    except Exception as error:
        # Do not persist upstream SQL, URLs or credentials.
        message=str(error).replace(key,'[hidden]') if isinstance(error,ValueError) else 'Fresh export failed ('+type(error).__name__+'). Check permissions, source stability and connectivity; saved pages are retained.'
        update(c,rid,status='needs_credentials',phase='Export needs attention',error=message[:600])
    finally:
        if client:client.close()
        c.close()

def revalidate_run(rid,path=None):
    """Recheck saved fresh records after a mapping fix; no credentials or ERP reads."""
    c=connect(path);claimed=False
    try:
        row=c.execute('SELECT config,status FROM runs WHERE id=?',(rid,)).fetchone()
        if not row or row[1] not in ('queued','needs_mapping'):raise ValueError('This export is not awaiting data validation.')
        with c:
            changed=c.execute("UPDATE runs SET status='running',pid=?,updated_at=?,phase='Revalidating saved fresh data',error=NULL WHERE id=? AND status IN ('queued','needs_mapping')",(os.getpid(),now(),rid)).rowcount
            if changed!=1:raise ValueError('Another worker already claimed this export.')
        claimed=True
        config=json.loads(row[0])
        datasets={name:json.loads(meta) for name,meta in c.execute('SELECT dataset,metadata FROM datasets WHERE run_id=?',(rid,))}
        for table in (*REQUIRED_TABLES,'inventory'):
            meta=datasets.get(table,{})
            count=c.execute('SELECT COUNT(*) FROM records WHERE run_id=? AND dataset=?',(rid,table)).fetchone()[0]
            expected=meta.get('expected',meta.get('count'))
            if not meta.get('complete') or expected!=count:raise ValueError('Saved '+table+' dataset is incomplete. Resume the export before validation.')
        report=validate(c,rid,datasets['schema']['tables'],config)
        inventory=datasets['inventory']
        report['inventorySource']=inventory.get('source','image-full-stocks.do')
        report['inventoryAsOf']=inventory.get('fetchedAt')
        if inventory.get('endpointWarning'):report['warnings'].append('Stock endpoint unavailable; fresh Query API balances used. Missing warehouse/SKU rows remain unknown.')
        update(c,rid,status='validated' if report['readyForForecast'] else 'needs_mapping',phase='Review data contract',report=encode(report))
        return report
    except Exception as error:
        if claimed:update(c,rid,status='needs_mapping',phase='Validation needs attention',error=str(error)[:400] if isinstance(error,ValueError) else 'Saved-data validation failed.')
        raise
    finally:c.close()

def activate(rid,serving,path=None):
    c=connect(path)
    try:
        row=c.execute('SELECT status,report FROM runs WHERE id=?',(rid,)).fetchone()
        if not row or row[0]!='validated':raise ValueError('A complete, validated fresh export is required.')
        report=json.loads(row[1])
        # Clear old operational inputs; these cannot be carried into a new source generation.
        with serving:
            serving.execute('DELETE FROM planning_inputs')
            serving.execute("INSERT OR REPLACE INTO joolan_state VALUES('forecast_source','fresh')")
            serving.execute("INSERT OR REPLACE INTO joolan_state VALUES('fresh_run',?)",(rid,))
            serving.execute("INSERT OR REPLACE INTO joolan_state VALUES('fresh_report',?)",(encode(report),))
        with c:c.execute("INSERT OR REPLACE INTO state VALUES('active_run',?)",(rid,))
        return report
    finally:c.close()

def export_pipeline(serving,destination,path=None):
    state=dict(serving.execute('SELECT key,value FROM joolan_state'))
    rid=state.get('fresh_run')
    if not rid:raise ValueError('Import and activate a fresh Joolan export first.')
    c=connect(path)
    from m1_data_preparation import EXPECTED_COLUMNS
    target=Path(destination).with_name('.fresh_joolan_pipeline.csv');target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.tmp')
    try:
        run=c.execute('SELECT status,config FROM runs WHERE id=?',(rid,)).fetchone()
        if not run or run[0]!='validated':raise ValueError('Active source is not validated.')
        schema=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='schema'",(rid,)).fetchone()[0])['tables']
        report=validate(c,rid,schema,json.loads(run[1]))
        if not report['readyForForecast']:raise ValueError('Fresh source validation failed.')
        products={str(field(r,'Produit')):r for r in rows(c,rid,'produits')}
        from operating_scope import read,primary,eligible_order
        operating=read(serving)
        supply_warehouses=json.loads(run[1])['warehouses']
        if operating:
            exported_brands={str(field(p,'Marque') or '').strip() for p in products.values()}
            if not set(operating['brands'])<=exported_brands:raise ValueError('Export all brand codes selected in Business Scope before forecasting.')
            products={k:p for k,p in products.items() if str(field(p,'Marque') or '').strip() in operating['brands']}
            supply_warehouses=primary(operating)
            if not products:raise ValueError('Selected business brands have no products in this export.')
            if not set(supply_warehouses)<=set(json.loads(run[1])['warehouses']):raise ValueError('Export the primary warehouses selected in Business Scope before forecasting.')
        customers={str(field(r,'Client')):r for r in rows(c,rid,'negoce_clients')}
        skus={variant(r):r for r in rows(c,rid,'skus')}
        stock=available_stock(c,rid,supply_warehouses)
        resolve_header=header_resolver(c)
        with temporary.open('w',newline='',encoding='utf-8') as stream:
            names=list(EXPECTED_COLUMNS)+['Data_Source','Source_Line_Key','Cancellations_Known','Order_Status','Planned_Delivery_Date','Requested_Delivery_Date','Catalog_Brand','Catalog_Collection']
            writer=csv.DictWriter(stream,fieldnames=names);writer.writeheader()
            for raw in rows(c,rid,'negoce_lignes'):
                header=resolve_header(raw);p=products.get(str(field(raw,'Produit')),{})
                if operating and (not p or not eligible_order(operating,field(header,'Magasin'))):continue
                try:quantities=order_quantities(raw,header)
                except NegativeOrderAdjustment:continue
                if not quantities['eligible']:continue
                row={name:'' for name in names}
                row.update(Client=field(header,'Client'),Nom=field(header,'Client'),Reference=field(raw,'Produit'),Couleur=field(raw,'Couleur'),Taille=field(raw,'Taille'),
                    Date_Commande=str(field(header,'Date'))[:10],Reference_CDE=field(header,'Entete'),Piece=field(header,'Entete'),Magasin=field(header,'Magasin'),
                    Planned_Delivery_Date=field(header,'Date_Livraison_Prevue') or '',Requested_Delivery_Date=field(header,'Date_Livraison_Souhaitee') or '',
                    Catalog_Brand=field(p,'Marque') or '',Catalog_Collection=field(p,'Collection') or '',
                    CDE_qte=quantities['ordered'],LIV_qte=quantities['delivered'],ANN_qte=quantities['cancelled'],
                    Data_Source='joolan',Source_Line_Key=encode([field(raw,'Ligne'),field(header,'Entete'),field(header,'Magasin'),field(header,'Client')]),Cancellations_Known=quantities['known'],Order_Status=quantities['status'])
                row['RELIQUAT_qte']=quantities['remaining']
                customer=customers.get(str(field(header,'Client')),{})
                for name in ('Nom','Adresse1','Adresse2','CP','Ville','Pays','Secteur','Famille_client'):
                    if field(customer,name) is not None:row[name]=field(customer,name)
                row['Gencod']=field(skus.get(variant(raw),{}),'EAN') or ''
                for name in ('Designation','Famille','Rayon','Modele','Matiere','Fournisseur'):
                    if name in row:row[name]=field(p,name) or ''
                row['Critere']=field(p,'Saison') or 'Joolan'
                row['Saison']=field(p,'Saison') or ''
                row['STOCK']=stock.get(variant(raw),'')
                # Disponible is the available balance; never add overlapping stock buckets.
                # Unknown incoming supply, cost and price remain blank.
                writer.writerow({k:v for k,v in row.items() if k in names})
        os.replace(temporary,target)
        return str(target)
    finally:
        c.close();temporary.unlink(missing_ok=True)
