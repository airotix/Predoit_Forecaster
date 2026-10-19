"""Seed reviewable catalogue prices from one explicitly chosen order season."""
import datetime as dt
import json
import math
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_HALF_UP
import budgeting as b
import fresh_joolan as fresh


def aggregate(headers,lines,variants,currencies,start,end,warehouses):
    groups={};excluded=Counter()
    allowed={w.casefold() for w in warehouses}
    for line in lines:
        header=headers.get(b.text(fresh.field(line,'Entete')))
        if not header:continue
        date=b.text(fresh.field(header,'Date'))[:10]
        if not start<=date<=end:continue
        key=b.key(line)
        if key not in variants:continue
        if fresh.field(header,'Nature')!='COMMANDE' or fresh.field(line,'Nature')!='COMMANDE':excluded['not_customer_order']+=1;continue
        if b.text(fresh.field(header,'Magasin')).casefold() not in allowed:excluded['other_warehouse']+=1;continue
        # Swagger: 0 unconfirmed, 1 confirmed, 2 cancelled, 3 closed.
        if any(b.text(fresh.field(r,'Statut')) not in ('1','3') for r in (header,line)):excluded['unconfirmed_cancelled_or_unknown_status']+=1;continue
        if fresh.field(header,'non_facturable') not in (0,False,'0'):excluded['non_billable_or_unknown']+=1;continue
        code=b.text(fresh.field(line,'Devise'));header_code=b.text(fresh.field(header,'Devise'))
        currency=currencies.get(code)
        if not currency or currencies.get(header_code)!=currency:excluded['unknown_or_conflicting_currency']+=1;continue
        qty=b.numeric(fresh.field(line,'Quantite'));unit=b.numeric(fresh.field(line,'Prix_HT_Devise'))
        discount=b.numeric(fresh.field(line,'Remise'));value=b.numeric(fresh.field(line,'Total_HT_Devise'))
        if any(v is None for v in (qty,unit,discount,value)) or qty<=0 or unit<=0 or value<=0 or discount>100:excluded['missing_or_nonpositive_price_quantity']+=1;continue
        if abs(value-qty*unit*(1-discount/100))>.02:excluded['line_total_does_not_reconcile']+=1;continue
        group=groups.setdefault((key,currency),dict(value=Decimal(0),units=Decimal(0),lines=0,orders=set(),min=None,max=None))
        net=Decimal(str(value))/Decimal(str(qty))
        group['value']+=Decimal(str(value));group['units']+=Decimal(str(qty));group['lines']+=1
        group['orders'].add(b.text(fresh.field(line,'Entete')))
        group['min']=min(group['min'],net) if group['min'] is not None else net
        group['max']=max(group['max'],net) if group['max'] is not None else net
    result={}
    for key,g in groups.items():
        price=float((g['value']/g['units']).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
        if not math.isfinite(price) or price<=0:continue
        result[key]=dict(price=price,units=float(g['units']),lines=g['lines'],orders=len(g['orders']),
                         minPrice=float(g['min']),maxPrice=float(g['max']))
    return result,dict(excluded)


def import_season(conn,start,end,path=None):
    """Apply historical defaults; never replace manual prices or explicit blanks."""
    import catalogue
    catalogue.sync(conn,path)
    dt.date.fromisoformat(start);dt.date.fromisoformat(end)
    if start>end:raise ValueError('Invalid historical price period.')
    config,plan=b.settings(conn)
    if end>=plan['startDate']:raise ValueError('Historical prices must precede the forecast season.')
    rid,_,metadata,_=b.source_identity(conn,path)
    if any(not json.loads(metadata.get(name,'{}')).get('complete') for name in ('negoce_entetes','negoce_lignes')):
        raise ValueError('Complete customer-order source tables are required.')
    entries=defaultdict(list)
    for sku,ref,color,size in conn.execute('SELECT sku,reference,color,size FROM catalogue_skus WHERE current=1 AND brand IN ('+','.join('?' for _ in config['brands'])+')',config['brands']):
        entries[(ref,color,size)].append(sku)
    variants={k:v[0] for k,v in entries.items() if len(v)==1}
    source=fresh.connect(path)
    try:
        currencies={}
        for r in fresh.rows(source,rid,'devises'):
            code=b.text(fresh.field(r,'Devise'));iso=b.text(fresh.field(r,'Code')).upper()
            if iso in b.SUPPORTED_CURRENCIES:currencies[code]=iso
        headers={b.text(fresh.field(r,'Entete')):r for r in fresh.rows(source,rid,'negoce_entetes')}
        prices,excluded=aggregate(headers,fresh.rows(source,rid,'negoce_lignes'),variants,currencies,start,end,config['warehouses'])
    finally:source.close()
    tag=f'historical:{start}:{end}';now=dt.datetime.now(dt.timezone.utc).isoformat()
    saved=0;manual=0
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        current_config,current_plan=b.settings(conn)
        if b.source_identity(conn,path)[0]!=rid or current_config!=config or current_plan!=plan:
            raise ValueError('Source or season settings changed during price import. Retry the import.')
        for (key,currency),evidence in prices.items():
            sku=variants[key]
            current=conn.execute('SELECT selling_source FROM catalogue_prices WHERE sku=? AND currency=?',(sku,currency)).fetchone()
            if current and current[0]=='manual':manual+=1;continue
            conn.execute('''INSERT INTO catalogue_prices VALUES(?,?,NULL,?,'joolan',?,?)
              ON CONFLICT(sku,currency) DO UPDATE SET selling=excluded.selling,selling_source=excluded.selling_source,updated_at=excluded.updated_at''',
                         (sku,currency,evidence['price'],tag,now))
            record=dict(**evidence,sku=sku,currency=currency,sourceRun=rid,startDate=start,endDate=end,
                        method='Ordered-unit-weighted net customer-order price, excluding VAT',warehouses=config['warehouses'],updatedAt=now)
            conn.execute('INSERT OR REPLACE INTO planning_state VALUES(?,?)',('historical_price:'+sku+':'+currency,json.dumps(record)))
            saved+=1
        summary=dict(startDate=start,endDate=end,sourceRun=rid,saved=saved,preservedManual=manual,
                     matchedVariants=len(prices),excluded=excluded,brands=config['brands'],warehouses=config['warehouses'],updatedAt=now)
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('historical_price_import',?)",(json.dumps(summary),))
        # Legacy explicit imports cannot pin old averages as automatic defaults.
        conn.execute("DELETE FROM planning_state WHERE key='order_price_import'")
    return summary


if __name__=='__main__':
    import argparse
    from database import get_connection
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start',required=True);parser.add_argument('--end',required=True)
    args=parser.parse_args()
    connection=get_connection()
    try:print(json.dumps(import_season(connection,args.start,args.end),indent=2),flush=True)
    finally:connection.close()
