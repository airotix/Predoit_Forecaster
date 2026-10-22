"""Durable SKU catalogue and currency-specific prices, independent of forecast runs."""
import datetime as dt
import hashlib,json,math,threading
_lock=threading.Lock()

def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_skus(sku TEXT PRIMARY KEY,reference TEXT,color TEXT,size TEXT,name TEXT,brand TEXT,category TEXT,supplier TEXT,current INTEGER,source_run TEXT,updated_at TEXT,details TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_prices(sku TEXT,currency TEXT,purchase REAL,selling REAL,purchase_source TEXT,selling_source TEXT,updated_at TEXT,PRIMARY KEY(sku,currency))''')
    conn.execute('CREATE INDEX IF NOT EXISTS catalogue_variant ON catalogue_skus(reference,color,size)')
    conn.execute('CREATE INDEX IF NOT EXISTS catalogue_listing ON catalogue_skus(current,reference,color,size,sku)')
    conn.execute('CREATE INDEX IF NOT EXISTS catalogue_brand_listing ON catalogue_skus(current,brand,reference,sku)')

def sync(conn,path=None,force=False):
    import budgeting as b
    import fresh_joolan as fresh
    ensure(conn)
    rid,export,metadata,revision=b.source_identity(conn,path)
    try:config,_=b.settings(conn)
    except ValueError:config=b.DEFAULTS
    fingerprint=hashlib.sha256(json.dumps([rid,revision,config],sort_keys=True).encode()).hexdigest()
    with _lock:
        previous=conn.execute("SELECT value FROM planning_state WHERE key='catalogue_source'").fetchone()
        if not force and previous and previous[0]==fingerprint:
            from catalogue_status import sync_sources
            sync_sources(conn)
            from order_prices import sync as sync_order_prices
            imported=sync_order_prices(conn,path)
            return dict(count=conn.execute('SELECT COUNT(*) FROM catalogue_skus WHERE current=1').fetchone()[0],sourceRun=rid,orderPriceImport=imported)
        source=fresh.connect(path)
        try:
            products={b.text(fresh.field(r,'Produit')):r for r in fresh.rows(source,rid,'produits')}
            stocks={}
            for row in fresh.rows(source,rid,'inventory'):stocks.setdefault(b.key(row),[]).append(row)
            entries=[];seen=set();now=dt.datetime.now(dt.timezone.utc).isoformat()
            for row in fresh.rows(source,rid,'skus'):
                sku=b.text(fresh.field(row,'Sku'));key=b.key(row);product=products.get(key[0],{})
                if not sku or sku in seen:raise ValueError('Missing or duplicate SKU identifiers in the fresh catalogue.')
                seen.add(sku)
                details=json.dumps(dict(product=product,sku=row,inventory=stocks.get(key,[]),inventoryAsOf=json.loads(metadata.get('inventory','{}')).get('fetchedAt')),ensure_ascii=False)
                entries.append((sku,*key,b.text(fresh.field(product,'Designation')),b.text(fresh.field(product,'Marque')),b.text(fresh.field(product,'Famille')),b.text(fresh.field(product,'Fournisseur')),1,rid,now,details))
            with conn:
                conn.execute('UPDATE catalogue_skus SET current=0')
                conn.executemany('INSERT INTO catalogue_skus VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(sku) DO UPDATE SET reference=excluded.reference,color=excluded.color,size=excluded.size,name=excluded.name,brand=excluded.brand,category=excluded.category,supplier=excluded.supplier,current=1,source_run=excluded.source_run,updated_at=excluded.updated_at,details=excluded.details',entries)
                conn.execute("INSERT OR REPLACE INTO planning_state VALUES('catalogue_source',?)",(fingerprint,))
            from catalogue_status import sync_sources
            sync_sources(conn)
            from order_prices import sync as sync_order_prices
            return dict(count=len(entries),sourceRun=rid,orderPriceImport=sync_order_prices(conn,path))
        finally:source.close()

def price_map(conn,currency):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_prices'").fetchone():return {}
    values={};ambiguous=set()
    evidence={}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_order_prices'").fetchone():
        evidence={(r[0],r[1]):json.loads(r[2]) for r in conn.execute('SELECT sku,side,payload FROM catalogue_order_prices WHERE currency=?',(currency,))}
    for ref,color,size,purchase,selling,sku,purchase_source,selling_source in conn.execute('SELECT s.reference,s.color,s.size,p.purchase,p.selling,s.sku,p.purchase_source,p.selling_source FROM catalogue_skus s JOIN catalogue_prices p ON p.sku=s.sku WHERE s.current=1 AND p.currency=?',(currency,)):
        key=(ref,color,size)
        if key in values:ambiguous.add(key)
        values[key]=dict(purchase=purchase,selling=selling,sku=sku,purchase_source=purchase_source,selling_source=selling_source,purchase_details=evidence.get((sku,'purchase')),selling_details=evidence.get((sku,'selling')))
    for key in ambiguous:values.pop(key,None)
    return values

def save_prices(conn,edits,currency):
    import budgeting as b
    ensure(conn)
    if currency not in b.SUPPORTED_CURRENCIES:raise ValueError('Select a supported currency.')
    if not isinstance(edits,list) or not edits or len(edits)>1000:raise ValueError('Save between 1 and 1000 SKU price rows.')
    validated=[];seen=set()
    for row in edits:
        if not isinstance(row,dict) or set(row)-{'sku','purchase','selling'}:raise ValueError('Unsupported price fields.')
        sku=row.get('sku')
        if sku in seen or not conn.execute('SELECT 1 FROM catalogue_skus WHERE sku=?',(sku,)).fetchone():raise ValueError('Unknown or duplicate SKU.')
        seen.add(sku);existing=conn.execute('SELECT purchase,selling,purchase_source,selling_source FROM catalogue_prices WHERE sku=? AND currency=?',(sku,currency)).fetchone() or (None,None,'joolan','joolan')
        values=list(existing)
        for index,name in enumerate(('purchase','selling')):
            if name not in row:continue
            value=row[name]
            if value is not None and (isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or value<0):raise ValueError('Prices must be finite, nonnegative numbers or blank.')
            values[index]=value;values[index+2]='manual'
        validated.append((sku,currency,*values,dt.datetime.now(dt.timezone.utc).isoformat()))
    with conn:
        conn.executemany('INSERT OR REPLACE INTO catalogue_prices VALUES(?,?,?,?,?,?,?)',validated)
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('catalogue_prices_updated',?)",(dt.datetime.now(dt.timezone.utc).isoformat(),))
    return dict(saved=len(validated),notice='Catalogue prices saved permanently. Budget draft edits remain separate. New forecasts use these prices.')

def listing(conn,currency,search='',brand='',offset=0,limit=50,grouped=False,status=''):
    ensure(conn)
    where=['s.current=1'];params=[currency]
    if search.strip():where.append('(s.reference LIKE ? OR s.name LIKE ? OR s.sku LIKE ? OR s.color LIKE ? OR s.size LIKE ?)');params.extend(['%'+search.strip()+'%']*5)
    if brand:where.append('s.brand=?');params.append(brand)
    if status:
        if status not in ('active','inactive','unknown'):raise ValueError('Select a supported catalogue status.')
        from catalogue_status import sync_sources
        sync_sources(conn)
        where.append('s.sku IN (SELECT sku FROM catalogue_effective_status WHERE active '+('IS NULL' if status=='unknown' else '= '+('1' if status=='active' else '0'))+')')
    from article_activity import catalogue_sort,attach
    activity_order=catalogue_sort(conn)
    query=' FROM catalogue_skus s LEFT JOIN catalogue_prices p ON p.sku=s.sku AND p.currency=? WHERE '+' AND '.join(where)
    total=conn.execute('SELECT COUNT(*)'+query,params).fetchone()[0]
    sku_total=total
    if grouped:
        total=conn.execute('SELECT COUNT(DISTINCT s.reference)'+query,params).fetchone()[0]
        references=[r[0] for r in conn.execute('SELECT DISTINCT s.reference'+query+' ORDER BY '+activity_order+',s.reference LIMIT ? OFFSET ?',(*params,limit,offset))]
        # Paginate articles, then fetch every colour and size in each article.
        # A colour/size search finds the article without truncating its breakdown.
        query=' FROM catalogue_skus s LEFT JOIN catalogue_prices p ON p.sku=s.sku AND p.currency=? WHERE s.current=1 AND s.reference IN ('+','.join('?' for _ in references)+')'
        params=[currency,*references]
        if brand:query+=' AND s.brand=?';params.append(brand)
        suffix=' ORDER BY s.reference,s.color,s.size,s.sku'
    else:
        suffix=' ORDER BY '+activity_order+',s.reference,s.color,s.size,s.sku LIMIT ? OFFSET ?'
        params=[*params,limit,offset]
    rows=[dict(zip(('sku','reference','color','size','name','brand','category','supplier','purchase','selling','purchaseSource','sellingSource','updatedAt'),r)) for r in conn.execute('SELECT s.sku,s.reference,s.color,s.size,s.name,s.brand,s.category,s.supplier,p.purchase,p.selling,p.purchase_source,p.selling_source,p.updated_at'+query+suffix,params)]
    attach(conn,rows)
    evidence={}
    if rows and conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_order_prices'").fetchone():
        page_skus=[r['sku'] for r in rows]
        evidence={(r[0],r[1]):json.loads(r[2]) for r in conn.execute('SELECT sku,side,payload FROM catalogue_order_prices WHERE currency=? AND sku IN ('+','.join('?' for _ in page_skus)+')',(currency,*page_skus))}
    from catalogue_status import lookup
    statuses=lookup(conn,[row['sku'] for row in rows])
    for row in rows:
        row['status']=statuses.get(row['sku'])
        row['purchasePriceDetails']=evidence.get((row['sku'],'purchase'))
        row['sellingPriceDetails']=evidence.get((row['sku'],'selling'))
    stats=conn.execute('SELECT COUNT(*),COUNT(p.purchase),COUNT(p.selling) FROM catalogue_skus s LEFT JOIN catalogue_prices p ON p.sku=s.sku AND p.currency=? WHERE s.current=1',(currency,)).fetchone()
    period=conn.execute("SELECT value FROM planning_state WHERE key='order_price_import'").fetchone()
    return dict(rows=rows,total=total,skuTotal=sku_total,currency=currency,orderPriceImport=json.loads(period[0]) if period else None,brands=[r[0] for r in conn.execute("SELECT DISTINCT brand FROM catalogue_skus WHERE current=1 AND brand<>'' ORDER BY brand")],summary=dict(skus=stats[0],purchaseKnown=stats[1],sellingKnown=stats[2]))

def install(app,connection):
    from fastapi import Body,HTTPException,Query
    @app.get('/api/catalogue')
    def get_catalogue(currency:str='EUR',search:str='',brand:str='',offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=200),grouped:bool=False,status:str=''):
        c=connection()
        try:sync(c);return listing(c,currency,search,brand,offset,limit,grouped,status)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()
    @app.get('/api/catalogue/sku/{sku}')
    def get_details(sku:str):
        c=connection()
        try:
            ensure(c);row=c.execute('SELECT details,reference FROM catalogue_skus WHERE sku=?',(sku,)).fetchone()
            if not row:raise HTTPException(404,'SKU not found.')
            from catalogue_status import lookup,history
            return dict(json.loads(row[0]),status=lookup(c,[sku]).get(sku),statusHistory=history(c,sku,row[1]))
        finally:c.close()
    @app.put('/api/catalogue/status')
    def put_status(body:dict=Body(...)):
        c=connection()
        try:
            sync(c)
            from catalogue_status import save
            return save(c,body.get('updates'))
        except (ValueError,TypeError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()
    @app.post('/api/catalogue/prices/reset')
    def reset_prices(body:dict=Body(...)):
        c=connection()
        try:
            sync(c)
            from order_prices import reset
            return reset(c,body.get('rows'),body.get('currency'))
        except (ValueError,TypeError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()
    @app.put('/api/catalogue/prices')
    def put_prices(body:dict=Body(...)):
        c=connection()
        try:return save_prices(c,body.get('rows'),body.get('currency'))
        except (ValueError,TypeError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()
