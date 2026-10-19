"""Customer ordering activity; purchases never imply a sales-representative visit."""
import calendar
import datetime as dt
import json
import threading
from planning import active_plan

_cache={}
_lock=threading.Lock()

def subtract_months(date,months):
    index=date.year*12+date.month-1-months
    year,month=divmod(index,12);month+=1
    return dt.date(year,month,min(date.day,calendar.monthrange(year,month)[1]))

def report(conn):
    metadata=dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
    lineage=json.loads(metadata.get('lineage','{}'));plan=active_plan(conn) or {}
    path=conn.execute('PRAGMA database_list').fetchone()[2]
    start,end=plan.get('startDate'),plan.get('endDate')
    exported_through=lineage.get('freshReport',{}).get('exportedThrough')
    from planning import order_ledger_revision
    key=(path,metadata.get('last_run'),metadata.get('last_import'),metadata.get('lineage'),start,end,order_ledger_revision(conn))
    with _lock:
        if path and key in _cache:activity=_cache[key]
        else:
            activity={str(r[0]):dict(seasonUnits=float(r[1] or 0),lastPositiveOrder=r[2],seasonOrderCount=r[3]) for r in conn.execute("""
                WITH lines AS (SELECT CAST(json_extract(payload,'$.Client') AS TEXT) AS client,
                    substr(json_extract(payload,'$.Date_Commande'),1,10) AS date,
                    json_extract(payload,'$.true_demand') AS quantity,
                    json_extract(payload,'$.Reference_CDE') AS order_id FROM order_lines)
                SELECT client,SUM(CASE WHEN date BETWEEN ? AND ? AND quantity>0 THEN quantity ELSE 0 END),
                    MAX(CASE WHEN quantity>0 THEN date END),
                    COUNT(DISTINCT CASE WHEN date BETWEEN ? AND ? AND quantity>0 THEN order_id END)
                FROM lines WHERE date<=COALESCE(?,date) GROUP BY client
            """,(start,end,start,end,exported_through))}
            if path:_cache.clear();_cache[key]=activity
    as_of=exported_through or max((v['lastPositiveOrder'] or '' for v in activity.values()),default='') or None
    cutoff=subtract_months(dt.date.fromisoformat(as_of),24).isoformat() if as_of else None
    customers=[]
    for r in conn.execute('SELECT client_id,client_name,total_units,total_spend,num_skus,first_order,last_order,pays FROM clients ORDER BY total_units DESC,client_id'):
        a=activity.get(str(r[0]),dict(seasonUnits=0,lastPositiveOrder=None,seasonOrderCount=0))
        active=bool(cutoff and a['lastPositiveOrder'] and cutoff<=a['lastPositiveOrder']<=as_of)
        customers.append(dict(id=r[0],name=r[1],totalUnits=r[2],totalSpend=r[3],productCount=r[4],firstOrder=r[5],lastOrder=r[6],country=r[7],
            **a,active=active,orderedInSeason=a['seasonUnits']>0))
    base=[c for c in customers if c['active']]
    ordered=sum(c['orderedInSeason'] for c in base)
    return dict(customers=customers,total=len(customers),coverage=dict(activeCustomers=len(base),orderedActiveCustomers=ordered,
        orderingCoverage=ordered/len(base) if base else None,seasonCustomers=sum(c['orderedInSeason'] for c in customers),
        seasonUnits=round(sum(c['seasonUnits'] for c in customers),4),asOf=as_of,activeSince=cutoff,
        seasonStart=start,seasonEnd=end,seasonName=plan.get('name'),
        definition='Ordering coverage: active customers with positive booked demand in the selected season / customers with positive demand in the last 24 data months. Not visit coverage or a forecast.'))

def repair_totals(conn):
    """Repair derived customer totals from the published ledger, preserving orders."""
    rows=conn.execute("""SELECT CAST(json_extract(payload,'$.Client') AS TEXT),SUM(json_extract(payload,'$.true_demand')),
        COUNT(DISTINCT json_extract(payload,'$.Reference')),COUNT(DISTINCT substr(json_extract(payload,'$.Date_Commande'),1,7))
        FROM order_lines GROUP BY CAST(json_extract(payload,'$.Client') AS TEXT)""").fetchall()
    with conn:conn.executemany('UPDATE clients SET total_units=?,num_skus=?,active_months=? WHERE client_id=?',[(r[1],r[2],r[3],r[0]) for r in rows])
    return len(rows)
