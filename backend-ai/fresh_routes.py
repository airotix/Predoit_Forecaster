"""Fresh Joolan control plane. Durable run state, process isolation, no ERP writes."""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel,SecretStr,Field
from starlette.responses import JSONResponse
import paths
import fresh_joolan as fresh

class FreshRequest(BaseModel):
    apiKey: SecretStr
    enseigne: str=Field(default='legend73',min_length=1,max_length=80)
    documentType: str='COMMANDE'
    throughDate: dt.date
    warehouses: list[str]=Field(min_length=1,max_length=100)
    brands: list[str]=Field(default_factory=lambda:['DAYTONA73'],min_length=1,max_length=100)

class ResumeRequest(BaseModel):
    apiKey: SecretStr

WORKER_MODULE='fresh_worker'

def worker_command(rid):
    return [sys.executable,'-B','-u','-m',WORKER_MODULE,rid]

def launch(rid,key):
    if not key.strip():raise ValueError('Enter an API key.')
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    try:
        p=subprocess.Popen(worker_command(rid),
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,
            cwd=paths.CODE_DIR,creationflags=flags)
        p.stdin.write(json.dumps({'apiKey':key})+'\n');p.stdin.close()
    except Exception:
        c=fresh.connect();fresh.update(c,rid,status='needs_credentials',error='Worker could not start. Re-enter the key to resume.');c.close()
        raise ValueError('Could not start the export worker.') from None

def install(app,connection):
    @app.middleware('http')
    async def fresh_only(request,call_next):
        path=request.url.path
        # Policy is persisted per serving database so isolated test stores remain usable.
        c=connection()
        try:
            state=dict(c.execute('SELECT key,value FROM joolan_state'))
        except Exception:state={}
        finally:c.close()
        if state.get('source_policy')=='fresh_only' and request.method!='OPTIONS':
            blocked=('/api/history/','/api/ingest/file','/api/ingest/erp','/api/joolan/file','/api/joolan/sync','/api/joolan/source','/api/joolan/forecast-source','/api/joolan/order-type','/api/planning/inputs')
            if any(path.startswith(p) for p in blocked):return JSONResponse({'detail':'Fresh Joolan API exports are the only allowed data source. Open Setup.'},409)
            if path=='/api/export' and request.query_params.get('purpose')=='approved':
                return JSONResponse({'detail':'Purchase approval requires verified Joolan supply, cost, currency and lead-time mappings. Demand-only review is available after a validated import.'},409)
            serving=('/api/dashboard','/api/products','/api/articles','/api/projections','/api/recommendations','/api/customer','/api/orders','/api/filter-options','/api/budget','/api/validation','/api/export')
            if any(path.startswith(p) for p in serving) and path not in ('/api/budget/options','/api/budget/settings','/api/budget/currencies'):
                c=connection()
                try:
                    meta=dict(c.execute('SELECT key,value FROM pipeline_metadata'))
                    lineage=json.loads(meta.get('lineage','{}'))
                finally:c.close()
                if not state.get('fresh_run') or lineage.get('freshRun')!=state['fresh_run']:
                    return JSONResponse({'detail':'Import fresh Joolan data in Setup, activate it and run a forecast. Previous data is excluded.'},409)
                c=connection()
                try:
                    from operating_scope import revision
                    scope_revision=revision(c)
                finally:c.close()
                if scope_revision and lineage.get('operatingScopeRevision')!=scope_revision:
                    return JSONResponse({'detail':'Business scope changed. Run a new forecast in Setup to publish matching brands and warehouse rules.'},409)
        return await call_next(request)

    @app.get('/api/joolan/fresh')
    def get_status():return fresh.status()

    @app.post('/api/joolan/fresh/preflight')
    def preflight(body:ResumeRequest,enseigne:str='legend73'):
        client=fresh.Client('https://go.joolan.com',enseigne,body.apiKey.get_secret_value())
        try:
            schema=fresh.discover(client)
            names={str(col['name']).lower() for col in schema.get('magasins',[])}
            query='SELECT DISTINCT Magasin FROM magasins ORDER BY Magasin' if 'magasin' in names else "SELECT DISTINCT Magasin FROM negoce_entetes WHERE Nature='COMMANDE' ORDER BY Magasin"
            warehouses=[str(fresh.field(r,'Magasin')) for r in client.query(query) if fresh.field(r,'Magasin') is not None]
            detail_fields=[name for name in ('Magasin','Nom','Groupe','Societe','Depot','Etat','magasin_ferme') if name.lower() in names]
            details=client.query('SELECT '+', '.join(map(fresh.identifier,detail_fields))+' FROM magasins ORDER BY Magasin') if detail_fields else []
            stock_names={str(col['name']).lower() for col in schema.get('stocks',[])}
            balances=client.query('SELECT Magasin, COUNT(*) AS variants, SUM(En_Stock) AS physical, SUM(Disponible) AS available FROM stocks GROUP BY Magasin') if {'magasin','en_stock','disponible'}<=stock_names else []
            brands=client.query('SELECT Marque, COUNT(*) AS products FROM produits GROUP BY Marque ORDER BY COUNT(*) DESC')
            result=dict(enseigne=enseigne,warehouses=warehouses,warehouseDetails=details,warehouseBalances=balances,brands=brands,tables=schema,contract=fresh.FIELD_CONTRACT,notice='Review depot status and inventory totals to identify supplying warehouses. Verify the brand scope before exporting.')
            c=fresh.connect()
            try:
                with c:c.execute("INSERT OR REPLACE INTO state VALUES('discovery',?)",(fresh.encode(result),))
            finally:c.close()
            return result
        except Exception:
            raise HTTPException(400,'Could not discover Joolan fields. Check the key, enseigne and api_query permission.') from None
        finally:client.close()

    @app.post('/api/joolan/fresh')
    def start(body:FreshRequest):
        if not body.apiKey.get_secret_value().strip():raise HTTPException(400,'Enter an API key.')
        config=dict(enseigne=body.enseigne.strip(),documentType=body.documentType,throughDate=body.throughDate.isoformat(),warehouses=sorted(set(v.strip() for v in body.warehouses if v.strip())),brands=sorted(set(v.strip() for v in body.brands if v.strip())))
        try:
            rid=fresh.create_run(config);launch(rid,body.apiKey.get_secret_value())
            return dict(runId=rid,status='queued')
        except ValueError as e:raise HTTPException(409,str(e)) from None

    @app.post('/api/joolan/fresh/{rid}/resume')
    def resume(rid:str,body:ResumeRequest):
        if not body.apiKey.get_secret_value().strip():raise HTTPException(400,'Enter an API key.')
        try:
            fresh.claim_resume(rid)
            launch(rid,body.apiKey.get_secret_value());return dict(runId=rid,status='queued')
        except ValueError as e:raise HTTPException(409,str(e)) from None

    @app.post('/api/joolan/fresh/{rid}/activate')
    def activate(rid:str):
        c=connection()
        try:return fresh.activate(rid,c)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.get('/api/health')
    def health():return dict(status='ok',sourcePolicy='fresh_only')
