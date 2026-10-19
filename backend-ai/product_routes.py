"""Local planning, source scope, inputs and order-ledger routes."""
import datetime as dt
import io
import json
import math
import os
import secrets
import threading
import pandas as pd
from fastapi import Body,File,HTTPException,Query,UploadFile
from starlette.responses import JSONResponse
from planning import seasons,save_season,active_plan,save_inputs,input_rows,financial_summary,inputs_fingerprint
from joolan import confirm_order_type

def install(app,connection):
    from product_kpis import install as install_product_history
    install_product_history(app,connection)

    @app.middleware('http')
    async def access_control(request,call_next):
        origin=request.headers.get('origin')
        token=os.environ.get('FORECASTER_API_TOKEN','')
        client=request.client.host if request.client else ''
        host=request.url.hostname
        allowed={'localhost','127.0.0.1','::1','testserver'}
        if origin and origin not in ('http://localhost:3000','http://127.0.0.1:3000'):
            return JSONResponse({'detail':'This origin is not allowed.'},403)
        if request.method!='OPTIONS':
            if token:
                supplied=request.headers.get('authorization','')
                if not secrets.compare_digest(supplied,'Bearer '+token):return JSONResponse({'detail':'Authentication required.'},401)
            elif client not in allowed|{'testclient'} or host not in allowed:
                return JSONResponse({'detail':'Local access only. Configure FORECASTER_API_TOKEN for shared access.'},403)
        return await call_next(request)

    @app.get('/api/seasons')
    def list_seasons():
        conn=connection()
        try:return seasons(conn)
        finally:conn.close()

    @app.get('/api/seasons/active')
    def selected_season():
        conn=connection()
        try:return active_plan(conn)
        finally:conn.close()

    @app.post('/api/seasons')
    def create_season(body:dict=Body(...)):
        conn=connection()
        try:return save_season(conn,body)
        except (ValueError,KeyError) as e:raise HTTPException(400,str(e)) from None
        finally:conn.close()

    @app.post('/api/seasons/{season_id}/activate')
    def activate_season(season_id:str):
        conn=connection()
        try:
            row=conn.execute('SELECT payload FROM planning_seasons WHERE id=?',(season_id,)).fetchone()
            if not row:raise HTTPException(404,'Season not found.')
            with conn:conn.execute("INSERT OR REPLACE INTO planning_state VALUES('active_season',?)",(season_id,))
            return json.loads(row[0])
        finally:conn.close()

    @app.get('/api/seasons/{season_id}')
    def get_season(season_id:str):
        conn=connection()
        try:
            row=conn.execute('SELECT payload FROM planning_seasons WHERE id=?',(season_id,)).fetchone()
            if not row:raise HTTPException(404,'Season not found.')
            return json.loads(row[0])
        finally:conn.close()

    @app.patch('/api/seasons/{season_id}')
    def update_season(season_id:str,body:dict=Body(...)):
        conn=connection()
        try:
            row=conn.execute('SELECT payload FROM planning_seasons WHERE id=?',(season_id,)).fetchone()
            if not row:raise HTTPException(404,'Season not found.')
            data=json.loads(row[0]);data.update({k:v for k,v in body.items() if k!='status'})
            if 'status' in body:raise HTTPException(400,'Season validation occurs only after a successful approved export.')
            return save_season(conn,data,season_id)
        except ValueError as e:raise HTTPException(400,str(e)) from None
        finally:conn.close()

    @app.post('/api/joolan/order-type')
    def set_order_type(body:dict=Body(...)):
        conn=connection()
        try:return confirm_order_type(conn,body.get('documentType',''))
        except ValueError as e:raise HTTPException(400,str(e)) from None
        finally:conn.close()

    @app.get('/api/planning/inputs')
    def get_inputs():
        conn=connection()
        try:return dict(rows=input_rows(conn))
        finally:conn.close()

    @app.post('/api/planning/inputs')
    def import_inputs(file:UploadFile=File(...)):
        conn=connection()
        try:
            raw=file.file.read(20*1024*1024+1)
            if len(raw)>20*1024*1024:raise ValueError('Input file is too large (maximum 20 MB).')
            frame=pd.read_excel(io.BytesIO(raw),dtype=str) if str(file.filename).endswith('.xlsx') else pd.read_csv(io.BytesIO(raw),dtype=str,keep_default_na=False)
            rows=frame.where(frame.notna(),None).to_dict('records')
            return dict(imported=save_inputs(conn,rows),notice='Refresh forecasts to apply these inputs to the published plan.')
        except (ValueError,KeyError) as e:raise HTTPException(400,str(e)) from None
        finally:conn.close();file.file.close()

    @app.get('/api/orders/articles')
    def customer_articles(customer:str=Query(...,min_length=1),offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
        from customer_order_articles import articles
        conn=connection()
        try:return articles(conn,customer,offset,limit)
        finally:conn.close()

    @app.get('/api/orders')
    def order_ledger(customer:str=Query(None),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=500)):
        conn=connection()
        try:
            where="WHERE json_extract(payload,'$.Client')=?" if customer else ''
            params=(customer,) if customer else ()
            total=conn.execute('SELECT COUNT(*) FROM order_lines '+where,params).fetchone()[0]
            rows=[json.loads(r[0]) for r in conn.execute("SELECT payload FROM order_lines "+where+" ORDER BY json_extract(payload,'$.Date_Commande') DESC,line_key LIMIT ? OFFSET ?",params+(limit,offset))]
            return dict(rows=rows,total=total)
        finally:conn.close()

    @app.delete('/api/recommendations/{reference}/{couleur}/override')
    def clear_override(reference:str,couleur:str,scenario:str=Query('base'),draftVersion:int=Query(None),forecastRun:str=Query(None)):
        conn=connection()
        try:
            locked=conn.execute('SELECT locked FROM sku_locks WHERE reference=? AND couleur=?',(reference,couleur)).fetchone()
            if locked and locked[0]:raise HTTPException(409,'Unlock this recommendation before resetting it.')
            plan=active_plan(conn)
            if scenario not in ('base','conservative','optimistic'):raise HTTPException(400,'Invalid scenario.')
            if __import__("purchase_draft").enabled(conn):
                import budgeting,purchase_draft
                from catalogue import sync
                sync(conn)
                try:
                    with conn:
                        conn.execute('BEGIN IMMEDIATE')
                        report=budgeting.build_report(conn,scenario,sync_catalogue=False)
                        current=purchase_draft.view(conn,report)
                        if current['draft']['stale']:raise ValueError('Prices or settings changed. Review and save the draft in Budget Tracker first.')
                        edits=[]
                        for edit in current['draft']['edits']:
                            item=dict(edit)
                            if json.loads(item['id'])[:2]==[reference,couleur]:item.pop('quantity',None)
                            edits.append(item)
                        # Explicit forecast defaults also retire migrated legacy quantity overrides.
                        for row in report['rows']:
                            if row['reference']==reference and row['color']==couleur:
                                import buying,math
                                ident=buying.identity(row)
                                item=next((e for e in edits if e['id']==ident),None)
                                if item is None:item={'id':ident};edits.append(item)
                                item.update(quantity=math.ceil(row['forecast']),reason='Reset quantity to forecast')
                        result=purchase_draft.store(conn,report,dict(version=draftVersion,forecastRun=forecastRun,
                            revision=current['revision'],edits=edits,selected=current['draft']['selected']))
                    return dict(status='ok',draftVersion=result['draft']['version'])
                except ValueError as e:raise HTTPException(409,str(e)) from None
            with conn:
                conn.execute('DELETE FROM user_overrides WHERE reference=? AND couleur=? AND scenario=? AND plan_id=?',(reference,couleur,scenario,plan['id'] if plan else ''))
                conn.execute('INSERT INTO audit_log(timestamp,user,action,entity_type,entity_id,entity_name,details) VALUES(?,?,?,?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),'authenticated' if os.environ.get('FORECASTER_API_TOKEN') else 'local','reset','recommendation',reference+'|'+couleur,reference,scenario))
            return dict(status='ok')
        finally:conn.close()

    @app.get('/api/pipeline/lineage')
    def lineage():
        conn=connection()
        try:
            meta=dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
            result=json.loads(meta.get('lineage','{}'))
            result['inputsChanged']=result.get('inputsHash')!=inputs_fingerprint(input_rows(conn))
            result['historyChanged']=meta.get('last_import','')>result.get('createdAt','')
            state=dict(conn.execute('SELECT key,value FROM joolan_state'))
            result['sourceGenerationChanged']=state.get('source_policy')=='fresh_only' and result.get('freshRun')!=state.get('fresh_run')
            from operating_scope import revision
            current=revision(conn)
            result['operatingScopeChanged']=bool(current and result.get('operatingScopeRevision')!=current)
            return result
        finally:conn.close()
