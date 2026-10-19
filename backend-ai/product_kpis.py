"""Attach recorded demand to published product KPIs, separately from forecasts."""
import datetime as dt
import json
import threading
from reorder_kpis import compute_reorders,DEFINITION

_repeat_cache={}
_repeat_lock=threading.Lock()


def recent_size_history(conn, reference, color):
    """Six complete calendar months preceding the published forecast, chart only."""
    metadata=dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
    try:
        lineage=json.loads(metadata.get('lineage','{}'))
        anchor=dt.date.fromisoformat(lineage['forecastStart']+'-01')
        year,month=divmod(anchor.year*12+anchor.month-1-6,12)
        start=dt.date(year,month+1,1)
    except (KeyError,ValueError,TypeError):
        raise ValueError('Publish a forecast with a valid start month before viewing recent size demand.') from None
    end=anchor-dt.timedelta(days=1)
    rows=conn.execute('''SELECT taille,SUM(true_demand) FROM historical_demand
        WHERE reference=? AND couleur=? AND year_month>=? AND year_month<?
        GROUP BY taille HAVING COUNT(true_demand)>0 ORDER BY taille''',
        (reference,color,start.strftime('%Y-%m'),anchor.strftime('%Y-%m'))).fetchall()
    sizes={size:round(float(quantity),4) for size,quantity in rows}
    return dict(reference=reference,color=color,startDate=start.isoformat(),endDate=end.isoformat(),
                forecastStart=anchor.isoformat(),sizeBreakdown=sizes,totalUnits=round(sum(sizes.values()),4),
                definition='Booked units by size in the six complete calendar months before the published forecast.')


def install(app,connection):
    from fastapi import HTTPException,Query

    @app.get('/api/products/size-history')
    def size_history(reference:str=Query(...,min_length=1,max_length=200),color:str=Query(...,min_length=1,max_length=200)):
        conn=connection()
        try:return recent_size_history(conn,reference,color)
        except ValueError as error:raise HTTPException(409,str(error)) from None
        finally:conn.close()

def ledger_reorders(conn, metadata):
    path=conn.execute('PRAGMA database_list').fetchone()[2]
    from planning import order_ledger_revision
    key=(path,metadata.get('lineage'),metadata.get('last_run'),metadata.get('last_import'),metadata.get('reorder_kpi_version'),order_ledger_revision(conn))
    # In-memory fixture connections must never share data through the live cache.
    if not path:return compute_reorders(json.loads(r[0]) for r in conn.execute('SELECT payload FROM order_lines'))
    with _repeat_lock:
        if key not in _repeat_cache:
            from derived_cache import load,store
            signature=json.dumps([key,'reorders-v1',DEFINITION],sort_keys=True)
            saved=load(path,'reorders',signature)
            try:result={tuple(k):v for k,v in saved} if isinstance(saved,list) else None
            except (TypeError,ValueError):result=None
            if result is None:
                result=compute_reorders(json.loads(r[0]) for r in conn.execute('SELECT payload FROM order_lines'))
                if len(result)>=100:store(path,'reorders',signature,list(result.items()))
            _repeat_cache.clear();_repeat_cache[key]=result
        return _repeat_cache[key]

def attach_history(conn, products):
    history={}
    for reference,color,size,demand in conn.execute('SELECT reference,couleur,taille,SUM(true_demand) FROM historical_demand GROUP BY reference,couleur,taille'):
        if demand is not None:
            history.setdefault((reference,color),{})[size]=round(float(demand),4)
    start,end=conn.execute('SELECT MIN(year_month),MAX(year_month) FROM historical_demand').fetchone()
    metadata=dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
    try:lineage=json.loads(metadata.get('lineage','{}'))
    except (ValueError,TypeError):lineage={}
    repeats=ledger_reorders(conn,metadata)
    for product in products:
        reference,color=product['skuId'].split('|',1)
        sizes=history.get((reference,color),{})
        total=round(sum(sizes.values()),4) if sizes else None
        product.update(historicalDemand=total,totalUnitsSold=total,sizeBreakdown=sizes,
            historyStart=start,historyEnd=end,forecastStart=lineage.get('forecastStart'),forecastEnd=lineage.get('forecastEnd'),
            trainingCutoff=lineage.get('cutoff'),ordersThrough=lineage.get('freshReport',{}).get('exportedThrough'),
            demandDefinition=lineage.get('demandDefinition') or 'Recorded historical demand; not certified net sales.')
        repeat=repeats.get((reference,color),dict(reorderRate=None,repeatOrderRate=None,reorderCustomers=0,repeatOrderCustomers=0,reorderMissingLines=0,reorderDefinition=DEFINITION))
        product.update({k:v for k,v in repeat.items() if k!='buyingCustomers'})
        product['reorderBuyingCustomers']=repeat.get('buyingCustomers',0)
    return products
