"""Traceable supplier-order defaults for missing catalogue purchase costs."""
import datetime as dt
import hashlib
import json
from collections import defaultdict,Counter


def match(source,config,through,currency):
    import budgeting as b
    import fresh_joolan as f
    result={};excluded=Counter();groups=defaultdict(list)
    if not config['poCostsVerified']:return {},dict(unverified_supplier_cost_basis=1)
    currencies=b._currency_map(source)
    for (order,*variant),line in source['poPrices'].items():
        key=tuple(variant);header=source['headers'].get(order,{})
        if b.status(f.field(header,'Statut')) not in ('open','closed'):excluded['draft_cancelled_or_unknown']+=1;continue
        try:date=dt.date.fromisoformat(str(f.field(header,'Date'))[:10]).isoformat()
        except ValueError:excluded['missing_order_date']+=1;continue
        if date>through:excluded['after_snapshot']+=1;continue
        native=currencies.get(b.text(f.field(header,'Devise')))
        if native!=currency:excluded['other_or_unknown_currency']+=1;continue
        product=source['products'].get(key[0],{})
        preferred=b.text(f.field(product,'Fournisseur'));supplier=b.text(f.field(header,'Fournisseur'))
        if not supplier or (preferred and preferred!=supplier):excluded['supplier_mismatch']+=1;continue
        price=b.net_price(f.field(line,'Prix_Achat_Devise'),f.field(line,'Remise_Achat'),*(f.field(header,'Remise'+str(i)) for i in range(1,6)))
        if price is None:excluded['invalid_price_or_discounts']+=1;continue
        groups[key].append(dict(unitCost=price,currency=native,supplier=supplier,orderId=order,orderNumber=b.text(f.field(header,'Numero_Commande')),
            orderDate=date,source='Joolan supplier order',method='Latest confirmed/closed exact-variant purchase price, sequential discounts applied once; planning default, not a new supplier quote.'))
    for key,options in groups.items():
        newest=max(r['orderDate'] for r in options);latest=[r for r in options if r['orderDate']==newest]
        if len({(r['supplier'],round(r['unitCost'],8)) for r in latest})!=1:excluded['conflicting_latest_prices']+=1;continue
        result[key]=sorted(latest,key=lambda r:r['orderId'])[-1]
    return result,dict(excluded)


def sync_missing(conn,path=None,force=False):
    import budgeting as b
    import fresh_joolan as f
    from planning import active_plan
    if not active_plan(conn):return dict(matched=0,skipped='No planning season selected.')
    config,plan=b.settings(conn);rid,export,metadata,revision=b.source_identity(conn,path)
    stamp=hashlib.sha256(json.dumps([rid,revision,config,plan['currency'],'supplier-price-v1'],sort_keys=True).encode()).hexdigest()
    marker=conn.execute("SELECT value FROM planning_state WHERE key='supplier_price_import'").fetchone()
    if not force and marker and json.loads(marker[0]).get('fingerprint')==stamp:return json.loads(marker[0])
    source_path=str(path or f.SOURCE_DB)
    core=hashlib.sha256(json.dumps({k:v for k,v in metadata.items() if k!='devises'},sort_keys=True).encode()).hexdigest()
    with b._source_lock:
        source={**b._load_source(source_path,rid,core),'currencies':b._load_currencies(source_path,rid,metadata.get('devises',''))}
    matches,excluded=match(source,config,export['throughDate'],plan['currency'])
    conn.execute('CREATE TABLE IF NOT EXISTS catalogue_purchase_sources(sku TEXT,currency TEXT,payload TEXT,PRIMARY KEY(sku,currency))')
    updated=0;missing=0;now=dt.datetime.now(dt.timezone.utc).isoformat()
    with conn:
        for sku,ref,color,size,price,origin in conn.execute('SELECT s.sku,s.reference,s.color,s.size,p.purchase,p.purchase_source FROM catalogue_skus s JOIN catalogue_prices p ON p.sku=s.sku AND p.currency=? WHERE s.current=1',(plan['currency'],)).fetchall():
            if origin=='manual' or (price is not None and not str(origin).startswith('supplier:')):continue
            selected=matches.get((ref,color,size))
            if not selected:
                missing+=1
                if str(origin).startswith('supplier:'):
                    conn.execute("UPDATE catalogue_prices SET purchase=NULL,purchase_source='joolan',updated_at=? WHERE sku=? AND currency=?",(now,sku,plan['currency']))
                    conn.execute('DELETE FROM catalogue_purchase_sources WHERE sku=? AND currency=?',(sku,plan['currency']))
                continue
            provenance={**selected,'sourceRun':rid,'updatedAt':now}
            conn.execute('UPDATE catalogue_prices SET purchase=?,purchase_source=?,updated_at=? WHERE sku=? AND currency=?',(selected['unitCost'],'supplier:'+selected['orderId'],now,sku,plan['currency']))
            conn.execute('INSERT OR REPLACE INTO catalogue_purchase_sources VALUES(?,?,?)',(sku,plan['currency'],json.dumps(provenance)))
            updated+=1
        report=dict(fingerprint=stamp,sourceRun=rid,currency=plan['currency'],matched=updated,unmatched=missing,excluded=excluded,updatedAt=now)
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('supplier_price_import',?)",(json.dumps(report),))
    return report
