"""Repeat buying from dated, distinct customer orders, never catalogue seasons."""
import datetime as dt
import math

DEFINITION='Buyers with distinct orders in at least two dated buying seasons / buyers with positive booked demand. Seasons: April–September and October–March (labelled by October year).'

def buying_season(value):
    date=dt.date.fromisoformat(str(value).strip()[:10])
    return ('summer',date.year) if 4<=date.month<=9 else ('winter',date.year if date.month>=10 else date.year-1)

def token(value):
    if value is None:return ''
    result=str(value).strip()
    return '' if result.lower() in ('','nan','none','unknown','nat') else result

def compute_reorders(records):
    groups={}
    for row in records:
        try:quantity=float(row.get('true_demand') or 0)
        except (ValueError,TypeError):continue
        if not math.isfinite(quantity) or quantity<=0:continue
        reference,color=token(row.get('Reference')),token(row.get('Couleur'))
        if not reference or not color:continue
        group=groups.setdefault((reference,color),dict(buyers={},missing=0))
        client,order=token(row.get('Client')),token(row.get('Reference_CDE'))
        if not client:
            group['missing']+=1
            continue
        orders=group['buyers'].setdefault(client,{})
        try:period=buying_season(row.get('Date_Commande'))
        except (ValueError,TypeError):
            group['missing']+=1
            continue
        if not order:
            group['missing']+=1
            continue
        if order in orders and orders[order]!=period:
            group['missing']+=1
            continue
        orders[order]=period
    result={}
    for key,group in groups.items():
        buyers=group['buyers'];count=len(buyers)
        seasonal=sum(len(set(orders.values()))>=2 for orders in buyers.values())
        repeat=sum(len(orders)>=2 for orders in buyers.values())
        complete=not group['missing'] and count>0
        result[key]=dict(buyingCustomers=count,reorderCustomers=seasonal,repeatOrderCustomers=repeat,
            reorderRate=seasonal/count if complete else None,repeatOrderRate=repeat/count if complete else None,
            reorderMissingLines=group['missing'],reorderDefinition=DEFINITION)
    return result

def frame_reorders(frame):
    """Shared implementation for the pipeline and the saved raw order ledger."""
    return compute_reorders(frame[['Reference','Couleur','Client','Reference_CDE','Date_Commande','true_demand']].to_dict('records'))

def refresh_saved_rates(conn):
    """Repair saved KPI values only; leave forecasts and raw exports untouched."""
    import json
    rates=compute_reorders(json.loads(row[0]) for row in conn.execute('SELECT payload FROM order_lines'))
    with conn:
        conn.execute('UPDATE recommendations SET reorder_rate=NULL')
        conn.executemany('UPDATE recommendations SET reorder_rate=? WHERE reference=? AND couleur=?',
            [(value['reorderRate'],reference,color) for (reference,color),value in rates.items()])
        conn.execute('INSERT OR REPLACE INTO pipeline_metadata(key,value,updated_at) VALUES(?,?,?)',
            ('reorder_kpi_version','dated-orders-v1',dt.datetime.now(dt.timezone.utc).isoformat()))
    return rates
