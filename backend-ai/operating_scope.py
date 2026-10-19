"""Client-confirmed brand/warehouse roles; separate ownership from supply availability."""
import datetime as dt
import hashlib
import json

ROLES=('primary','clearance','faulty','consignment','unclassified')
CONFIRMED={'CENTRAL':'primary','DESTOCK_VD':'clearance','DEFECTUEUX':'faulty'}
KEY='operating_scope'

def read(conn):
    row=conn.execute('SELECT value FROM planning_state WHERE key=?',(KEY,)).fetchone()
    return json.loads(row[0]) if row else None

def revision(conn):
    scope=read(conn)
    return scope['revision'] if scope else None

def primary(scope):return sorted(w for w,r in scope['warehouseRoles'].items() if r=='primary')

def role(scope,warehouse):
    roles={w.casefold():r for w,r in scope['warehouseRoles'].items()}
    return roles.get(str(warehouse or '').strip().casefold(),'unclassified')

def eligible_order(scope,warehouse):
    # No consignment sell-through mapping has been confirmed. Preserve its raw
    # records but exclude those COMMANDE documents from the wholesale series.
    return role(scope,warehouse) not in ('clearance','faulty','consignment')

def save(conn,data,brands,warehouses):
    if not isinstance(data,dict) or set(data)-{'brands','warehouseRoles'}:raise ValueError('Unsupported scope fields.')
    selected=data.get('brands');roles=data.get('warehouseRoles')
    if not isinstance(selected,list) or not selected or any(not isinstance(b,str) or b not in brands for b in selected):raise ValueError('Select exported brand codes.')
    if not isinstance(roles,dict) or set(roles)-set(warehouses) or any(r not in ROLES for r in roles.values()):raise ValueError('Select valid exported warehouse roles.')
    roles={w:roles.get(w,CONFIRMED.get(w.upper(),'unclassified')) for w in warehouses}
    for warehouse,value in roles.items():
        expected=CONFIRMED.get(warehouse.upper())
        if expected and value!=expected:raise ValueError(warehouse+' must retain its client-confirmed '+expected+' role.')
    if not any(r=='primary' for r in roles.values()):raise ValueError('Select a primary supply warehouse.')
    scope=dict(brands=sorted(set(selected)),warehouseRoles=roles)
    scope['revision']=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()
    scope['updatedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
    with conn:conn.execute('INSERT OR REPLACE INTO planning_state VALUES(?,?)',(KEY,json.dumps(scope)))
    return scope

def options(conn,path=None):
    from catalogue import sync
    import budgeting as b
    sync(conn,path)
    rid,export,metadata,_=b.source_identity(conn,path)
    import fresh_joolan as fresh
    source=fresh.connect(path)
    try:warehouses=sorted(set(export['warehouses'])|{b.text(fresh.field(r,'Magasin')) for r in fresh.rows(source,rid,'magasins') if b.text(fresh.field(r,'Magasin'))})
    finally:source.close()
    brands=[dict(code=r[0],articles=r[1],skus=r[2]) for r in conn.execute('SELECT brand,COUNT(DISTINCT reference),COUNT(*) FROM catalogue_skus WHERE current=1 GROUP BY brand ORDER BY brand') if r[0]]
    profile=read(conn)
    proposed=profile or dict(brands=[b['code'] for b in brands if b['code'] in ('DAYTONA73','D73','IRON AND RESIN','IRON&RESIN')],warehouseRoles={})
    proposed={**proposed,'warehouseRoles':{w:proposed['warehouseRoles'].get(w,CONFIRMED.get(w.upper(),'unclassified')) for w in warehouses}}
    return dict(saved=bool(profile),scope=proposed,brands=brands,warehouses=warehouses,sourceRun=rid,inventoryAsOf=json.loads(metadata.get('inventory','{}')).get('fetchedAt'),
        notice='CENTRAL supplies normal orders. Clearance, faulty and consignment stock are separate. Unclassified stores are not assumed to supply normal orders. Consignment sales still require mapping. The four agreed brand codes remain separate.')

def balances(conn,path=None):
    import budgeting as b
    import fresh_joolan as fresh
    opts=options(conn,path);scope=opts['scope']
    refs={r[0] for r in conn.execute('SELECT DISTINCT reference,brand FROM catalogue_skus WHERE current=1') if r[1] in scope['brands']}
    counts={w:dict(warehouse=w,role=role(scope,w),records=0,physical=None,available=None,invalidRecords=0,physicalUnknown=False,availableUnknown=False) for w in opts['warehouses']}
    source=fresh.connect(path)
    try:
        seen=set()
        for raw in fresh.rows(source,opts['sourceRun'],'inventory'):
            if b.key(raw)[0] not in refs:continue
            warehouse=b.text(fresh.field(raw,'Magasin'))
            matching=next((w for w in counts if w.casefold()==warehouse.casefold()),None)
            if matching is None:continue
            row=counts[matching];key=(matching,*b.key(raw))
            physical=b.numeric(fresh.field(raw,'En_Stock'),True);available=b.numeric(fresh.field(raw,'Disponible'),True)
            row['records']+=1
            duplicate=key in seen
            if duplicate or physical is None or available is None:row['invalidRecords']+=1
            if duplicate or physical is None:row['physicalUnknown']=True
            else:row['physical']=(row['physical'] or 0)+physical
            if duplicate or available is None:row['availableUnknown']=True
            else:row['available']=(row['available'] or 0)+available
            seen.add(key)
        for row in counts.values():
            if row.pop('physicalUnknown'):row['physical']=None
            if row.pop('availableUnknown'):row['available']=None
    finally:source.close()
    return dict(**opts,balances=list(counts.values()),balanceNotice='These are recorded subtotals for selected brands, not complete stock for every SKU. Missing rows remain unknown. Consignment is company-owned but is not pooled into CENTRAL availability.')

def install(app,connection):
    from fastapi import Body,HTTPException
    @app.get('/api/operating-scope')
    def get_scope():
        c=connection()
        try:return balances(c)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()
    @app.put('/api/operating-scope')
    def put_scope(body:dict=Body(...)):
        c=connection()
        try:
            opts=options(c)
            scope=save(c,body,[b['code'] for b in opts['brands']],opts['warehouses'])
            return dict(scope=scope,notice='Scope saved. Run a new forecast in Setup to publish matching insights. Raw exports and saved catalogue prices are retained.')
        except (ValueError,TypeError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()
