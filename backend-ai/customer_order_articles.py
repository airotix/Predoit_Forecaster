"""Whole order articles with recorded quantities and separate published demand forecasts."""
import json
import math
import sqlite3


def season_forecasts(conn,references):
    context=dict(scope='all_customers',scenario='base',available=False,seasonName=None,startDate=None,endDate=None)
    try:
        row=conn.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()
    except sqlite3.OperationalError:return {},context
    lineage=json.loads(row[0]) if row else {}
    if not lineage.get('runId'):return {},context
    context.update(seasonName=(lineage.get('plan') or {}).get('name'),startDate=lineage.get('forecastStart'),endDate=lineage.get('forecastEnd'))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='planning_state'").fetchone():
        from planning import active_plan
        plan=active_plan(conn)
        if plan and (lineage.get('seasonId')!=plan['id'] or any(plan[k]!=(lineage.get('plan') or {}).get(k) for k in ('startDate','endDate'))):
            return {},context
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='recommendations'").fetchone():return {},context
    context['available']=True
    forecasts={}
    if not references:return forecasts,context
    query='SELECT reference,couleur,taille,forecast_base FROM recommendations WHERE reference IN ('+','.join('?' for _ in references)+')'
    for reference,color,size,value in conn.execute(query,sorted(references)):
        key=(color or 'Unknown',size or 'Unknown');values=forecasts.setdefault(str(reference),{})
        # A missing or ambiguous prediction must not be displayed as zero.
        values[key]=None if key in values or value is None or not math.isfinite(value) or value<0 else value
    return forecasts,context


def articles(conn,customer,offset=0,limit=20):
    source="""SELECT json_extract(payload,'$.Reference_CDE') AS order_id,
        substr(json_extract(payload,'$.Date_Commande'),1,10) AS date,
        json_extract(payload,'$.Reference') AS reference,
        json_extract(payload,'$.Designation') AS name,
        json_extract(payload,'$.Couleur') AS color,json_extract(payload,'$.Taille') AS size,
        json_extract(payload,'$.CDE_qte') AS ordered,json_extract(payload,'$.LIV_qte') AS delivered
        FROM order_lines WHERE CAST(json_extract(payload,'$.Client') AS TEXT)=?"""
    total=conn.execute('WITH source AS ('+source+') SELECT COUNT(*) FROM (SELECT order_id,date,reference FROM source GROUP BY order_id,date,reference)',(customer,)).fetchone()[0]
    query='WITH source AS ('+source+'''), page AS (
        SELECT order_id,date,reference FROM source GROUP BY order_id,date,reference
        ORDER BY date DESC,CAST(order_id AS TEXT),reference LIMIT ? OFFSET ?)
        SELECT s.order_id,s.date,s.reference,MAX(s.name),s.color,s.size,SUM(s.ordered),SUM(s.delivered),COUNT(*)
        FROM source s JOIN page p ON s.order_id IS p.order_id AND s.date IS p.date AND s.reference IS p.reference
        GROUP BY s.order_id,s.date,s.reference,s.color,s.size
        ORDER BY s.date DESC,CAST(s.order_id AS TEXT),s.reference,s.color,s.size'''
    grouped={}
    for order,date,reference,name,color,size,ordered,delivered,count in conn.execute(query,(customer,limit,offset)):
        key=(order,date,reference)
        article=grouped.setdefault(key,dict(orderId=order,date=date,reference=reference,name=name or '',variants=[],lineCount=0))
        article['variants'].append(dict(color=color or 'Unknown',size=size or 'Unknown',ordered=ordered,delivered=delivered,lineCount=count))
        article['lineCount']+=count
        if name:article['name']=name
    forecasts,context=season_forecasts(conn,{str(a['reference']) for a in grouped.values()})
    for article in grouped.values():
        for field in ('ordered','delivered'):
            article[field]=sum(v[field] for v in article['variants']) if all(v[field] is not None for v in article['variants']) else None
        variants={(v['color'],v['size']):v for v in article['variants']}
        predicted=forecasts.get(str(article['reference']),{})
        for key,value in predicted.items():
            variants.setdefault(key,dict(color=key[0],size=key[1],ordered=None,delivered=None,lineCount=0))['forecast']=value
        for key,variant in variants.items():variant.setdefault('forecast',None)
        article['variants']=list(variants.values())
        article['forecast']=sum(v['forecast'] for v in variants.values()) if variants and all(v['forecast'] is not None for v in variants.values()) else None
    return dict(articles=list(grouped.values()),total=total,forecastContext=context)
