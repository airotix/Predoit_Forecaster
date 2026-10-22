"""Article season labels filter published monthly forecasts; they never date orders."""
import datetime as dt
import json
import re
from collections import defaultdict
from planning import active_plan,SCENARIOS

CURRENT_CODES=('H26','FW27','P27','CORE','RECONDUIT')


def month(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',value):raise ValueError('Choose a valid forecast month (YYYY-MM).')
    date=dt.date.fromisoformat(value+'-01')
    return date.year*12+date.month


def validate(value,available,allow_empty=False):
    if not isinstance(value,dict) or set(value)-{'startMonth','endMonth','codes'}:raise ValueError('Unsupported seasonal allocation fields.')
    start=value.get('startMonth');end=value.get('endMonth');codes=value.get('codes')
    count=month(end)-month(start)+1
    if not 1<=count<=24:raise ValueError('Select an interval of 1 to 24 whole forecast months.')
    if not isinstance(codes,list) or any(not isinstance(c,str) or c not in available for c in codes) or len(set(codes))!=len(codes) or (not codes and not allow_empty):raise ValueError('Select article season codes from the current catalogue.')
    return dict(startMonth=start,endMonth=end,codes=sorted(codes))


def context(conn):
    from catalogue import ensure
    from operating_scope import read
    ensure(conn)
    plan=active_plan(conn)
    row=conn.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()
    lineage=json.loads(row[0]) if row else {}
    scope=read(conn)
    brands=scope['brands'] if scope else ['DAYTONA73','D73','IRON AND RESIN','IRON&RESIN']
    # Parse one product record per article; SKU detail JSON repeats the product.
    facts={}
    # Group in article order. A brand-first scan forces SQLite to sort the large
    # repeated SKU detail JSON before grouping, which can consume hundreds of MB.
    query='SELECT reference,MAX(name),MAX(brand),MAX(details),MIN(source_run),MAX(source_run),COUNT(DISTINCT json_array(color,size)) FROM catalogue_skus INDEXED BY catalogue_listing WHERE current=1 AND brand IN ('+','.join('?' for _ in brands)+') GROUP BY reference'
    from joolan_client import field
    for ref,name,brand,details,first_source,last_source,count in conn.execute(query,brands):
        try:product=json.loads(details or '{}').get('product',{});code=str(field(product,'Saison') or '').strip() or 'UNKNOWN'
        except (ValueError,TypeError,AttributeError):code='UNKNOWN'
        facts[ref]=dict(reference=ref,name=name or ref,brand=brand,code=code,variants=count,sourceRun=first_source if first_source==last_source else None)
    if not facts:raise ValueError('Load the Joolan catalogue for the selected business brands in Setup first.')
    options=defaultdict(lambda:dict(articles=0,variants=0))
    for fact in facts.values():options[fact['code']]['articles']+=1;options[fact['code']]['variants']+=fact['variants']
    saved=conn.execute('SELECT value FROM planning_state WHERE key=?',('seasonal_allocation:'+(plan or {}).get('id',''),)).fetchone()
    saved=json.loads(saved[0]) if saved else None
    defaults=dict(startMonth=(plan or {}).get('startDate',lineage.get('forecastStart',''))[:7],endMonth=(plan or {}).get('endDate',lineage.get('forecastEnd',''))[:7],codes=[c for c in CURRENT_CODES if c in options])
    if saved:defaults=saved
    return plan,lineage,scope,facts,dict(options),defaults,bool(saved)


def save(conn,value):
    plan,_,_,_,options,_,_=context(conn)
    if not plan:raise ValueError('Select a planning season in Setup before saving an allocation.')
    selected=validate(value,options)
    with conn:conn.execute('INSERT OR REPLACE INTO planning_state VALUES(?,?)',('seasonal_allocation:'+plan['id'],json.dumps(selected)))
    return dict(saved=True,allocation=selected,notice='Seasonal allocation saved for this planning season. Article labels and order dates remain separate.')


def listing(conn,start=None,end=None,codes=None,scenario='base',search='',offset=0,limit=20):
    if scenario not in SCENARIOS:raise ValueError('Unknown demand scenario.')
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50:raise ValueError('Invalid article page.')
    plan,lineage,scope,facts,options,defaults,saved=context(conn)
    unavailable=[c for c in defaults['codes'] if c not in options] if codes is None else []
    selected=validate(dict(startMonth=start or defaults['startMonth'],endMonth=end or defaults['endMonth'],codes=codes if codes is not None else [c for c in defaults['codes'] if c in options]),options,allow_empty=True)
    start=selected['startMonth'];end=selected['endMonth'];expected=month(end)-month(start)+1
    selected_codes=set(selected['codes']);query=search.strip().casefold()
    matching=[f for f in facts.values() if f['code'] in selected_codes and (not query or query in (f['reference']+' '+f['name']+' '+f['brand']).casefold())]
    matching.sort(key=lambda f:(f['code'],f['reference']))
    references={f['reference'] for f in matching}
    sources={f['sourceRun'] for f in facts.values()}
    source_matches=bool(lineage.get('freshRun') and sources=={lineage['freshRun']})
    plan_matches=(lineage.get('seasonId')==(plan or {}).get('id') and all((lineage.get('plan') or {}).get(k)==(plan or {}).get(k) for k in ('startDate','endDate')))
    scope_matches=(lineage.get('operatingScopeRevision')==(scope or {}).get('revision'))
    range_matches=bool(lineage.get('forecastStart') and lineage['forecastStart']<=start<=end<=lineage.get('forecastEnd',''))
    usable=source_matches and plan_matches and scope_matches and range_matches
    forecasts={}
    if usable:
        columns={r[1] for r in conn.execute('PRAGMA table_info(forecast_monthly)')}
        booked='SUM(season_booked)' if 'season_booked' in columns else 'NULL'
        for ref,color,size,quantity,count,known,booked_qty in conn.execute(f'SELECT reference,couleur,taille,SUM(forecast_{scenario}),COUNT(DISTINCT forecast_month),COUNT(forecast_{scenario}),{booked} FROM forecast_monthly WHERE forecast_month BETWEEN ? AND ? GROUP BY reference,couleur,taille',(start,end)):
            if ref in references:forecasts[(ref,color,size)]=dict(quantity=round(quantity,4) if quantity is not None and count==expected and known==expected else None,booked=booked_qty)
    variants=defaultdict(dict)
    if references:
        refs=sorted(references)
        for ref,color,size,sku in conn.execute('SELECT reference,color,size,sku FROM catalogue_skus WHERE current=1 AND reference IN ('+','.join('?' for _ in refs)+') ORDER BY reference,color,size,sku',refs):
            key=(ref,color,size);item=variants[ref].setdefault(key,dict(color=color,size=size,skus=[],forecast=forecasts.get(key,{}).get('quantity'),booked=forecasts.get(key,{}).get('booked')))
            item['skus'].append(sku)
    articles=[];known_variants=0;total_variants=0;known_units=0.;complete_articles=0
    for fact in matching:
        rows=list(variants[fact['reference']].values());known=[v for v in rows if v['forecast'] is not None]
        complete=bool(rows) and len(known)==len(rows);subtotal=round(sum(v['forecast'] for v in known),4)
        known_variants+=len(known);total_variants+=len(rows);known_units+=subtotal;complete_articles+=int(complete)
        articles.append(dict(**fact,forecast=subtotal if complete else None,knownForecast=subtotal,forecastedVariants=len(known),missingVariants=len(rows)-len(known),colors=len({v['color'] for v in rows}),rows=rows))
    from article_activity import attach
    attach(conn,articles)
    notices=[]
    if unavailable:notices.append('Saved article codes are absent from the current catalogue: '+', '.join(unavailable)+'. Choose the available codes and save the updated selection.')
    if not source_matches:notices.append('The catalogue and published forecast use different Joolan snapshots. Refresh the forecast in Setup.')
    if not plan_matches or not scope_matches:notices.append('Publish a forecast matching the selected planning season and business scope.')
    if not range_matches:notices.append('The selected interval is outside the published forecast. Generate that interval in Setup.')
    if total_variants>known_variants:notices.append('Some catalogue variants have no complete forecast for this interval. Their quantity stays unknown; they need estimation before allocation.')
    return dict(allocation=selected,saved=saved,scenario=scenario,planId=(plan or {}).get('id'),options=[dict(code=c,**v) for c,v in sorted(options.items())],
        published=dict(runId=lineage.get('runId'),startMonth=lineage.get('forecastStart'),endMonth=lineage.get('forecastEnd'),sourceRun=lineage.get('freshRun'),matching=usable),
        rows=articles[offset:offset+limit],total=len(articles),summary=dict(articles=len(articles),fullyForecastedArticles=complete_articles,variants=total_variants,forecastedVariants=known_variants,missingVariants=total_variants-known_variants,knownForecastUnits=round(known_units,4),totalForecastUnits=round(known_units,4) if total_variants and total_variants==known_variants else None),notices=notices)


def install(app,connection):
    from fastapi import Body,HTTPException,Query
    @app.get('/api/seasonal-allocation')
    def get(startMonth:str=None,endMonth:str=None,codes:str=None,scenario:str='base',search:str='',offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=50)):
        c=connection()
        try:return listing(c,startMonth,endMonth,json.loads(codes) if codes is not None else None,scenario,search,offset,limit)
        except (ValueError,TypeError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()
    @app.put('/api/seasonal-allocation')
    def put(body:dict=Body(...)):
        c=connection()
        try:return save(c,body)
        except (ValueError,TypeError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()
