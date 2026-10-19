"""Durable server-managed Joolan refresh -> validation -> forecast workflow."""
import calendar
import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
import fresh_joolan as fresh
import server_credentials

BUSY=('queued','running','waiting')

def ensure(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS automatic_jobs(id TEXT PRIMARY KEY,status TEXT,payload TEXT NOT NULL,pid INTEGER,updated_at TEXT);
      CREATE UNIQUE INDEX IF NOT EXISTS one_automatic_job ON automatic_jobs((1)) WHERE status IN ('queued','running','waiting','paused');''')

def read(c,jid):
    row=c.execute('SELECT payload,status,pid FROM automatic_jobs WHERE id=?',(jid,)).fetchone()
    if not row:raise ValueError('Automatic forecast job not found.')
    return dict(json.loads(row[0]),status=row[1],pid=row[2])

def update(c,jid,**changes):
    record=read(c,jid);record.update(changes,updatedAt=fresh.now())
    with c:c.execute('UPDATE automatic_jobs SET status=?,payload=?,pid=?,updated_at=? WHERE id=?',
        (record['status'],json.dumps(record),record.get('pid'),record['updatedAt'],jid))
    return record

def public(record):
    return {k:v for k,v in record.items() if k not in ('pid','rollback','scope')}

def latest(c):
    ensure(c)
    row=c.execute('SELECT id FROM automatic_jobs ORDER BY rowid DESC LIMIT 1').fetchone()
    return read(c,row[0]) if row else None

def busy(path=None,serving=None):
    jid=None
    if serving is not None:
        try:row=serving.execute("SELECT value FROM planning_state WHERE key='automatic_job'").fetchone()
        except __import__('sqlite3').OperationalError:return False
        if not row:return False
        jid=row[0]
    c=fresh.connect(path)
    try:
        ensure(c)
        return c.execute("SELECT 1 FROM automatic_jobs WHERE status IN ('queued','running','waiting')"+(' AND id=?' if jid else ''),(jid,) if jid else ()).fetchone() is not None
    finally:c.close()

def dates(start,end,today=None):
    today=today or dt.datetime.now(dt.timezone.utc).date()
    start=dt.date.fromisoformat(str(start));end=dt.date.fromisoformat(str(end))
    if start.day!=1 or end.day!=calendar.monthrange(end.year,end.month)[1]:raise ValueError('Select full forecast months: the first day through the final day of a month.')
    months=(end.year-start.year)*12+end.month-start.month+1
    if end<start or not 1<=months<=24:raise ValueError('Select between 1 and 24 forecast months.')
    if start<today.replace(day=1):raise ValueError('Select the current month or a future month. Historical evaluation uses a separate backtest.')
    return start.isoformat(),end.isoformat(),today.isoformat()

def create(serving,start,end,path=None):
    server_credentials.credentials() # Never persist credentials in the job.
    start,end,through=dates(start,end)
    from operating_scope import read as scope_read
    scope=scope_read(serving)
    if not scope:raise ValueError('Save the client brand/warehouse scope once before using automatic forecasts.')
    if not any(r=='primary' for r in scope['warehouseRoles'].values()):raise ValueError('A primary warehouse is required.')
    if serving.execute("SELECT 1 FROM import_jobs WHERE job_type='forecast' AND status='running'").fetchone():raise ValueError('Another forecast is already running.')
    c=fresh.connect(path)
    try:
        ensure(c)
        if c.execute("SELECT 1 FROM runs WHERE status IN ('queued','running')").fetchone():raise ValueError('Another Joolan export is running. Let it finish first.')
        jid=uuid.uuid4().hex
        record=dict(id=jid,status='queued',phase='Queued',startDate=start,endDate=end,throughDate=through,
                    scope=scope,createdAt=fresh.now(),updatedAt=fresh.now(),runId=None,seasonId=None,
                    forecastRun=None,error=None,retryAt=None,attempts=0)
        try:
            with c:c.execute('INSERT INTO automatic_jobs VALUES(?,?,?,?,?)',(jid,'queued',json.dumps(record),None,fresh.now()))
        except __import__('sqlite3').IntegrityError:raise ValueError('An automatic forecast is already running or paused. Resume or dismiss it first.') from None
        with serving:serving.execute("INSERT OR REPLACE INTO planning_state VALUES('automatic_job',?)",(jid,))
        return record
    finally:c.close()

def launch(jid):
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    try:
        process=subprocess.Popen([sys.executable,'-B','-u',str(Path(__file__).with_name('automatic_worker.py')),jid],
            cwd=Path(__file__).parent,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
        c=fresh.connect()
        try:
            ensure(c);record=read(c,jid)
            if not record.get('pid'):update(c,jid,pid=process.pid)
        finally:c.close()
    except OSError:
        c=fresh.connect()
        try:update(c,jid,status='paused',phase='Worker could not start',error='Retry the automatic forecast job.')
        finally:c.close()
        raise ValueError('Could not start the automatic forecast worker.') from None

def restore(serving,job,path=None):
    previous=job.get('rollback')
    if not previous:return
    meta=dict(serving.execute('SELECT key,value FROM pipeline_metadata'))
    lineage=json.loads(meta.get('lineage','{}'))
    if lineage.get('freshRun')==job.get('runId') and lineage.get('seasonId')==job.get('seasonId') and lineage.get('createdAt','')>=job['createdAt']:return
    state=dict(serving.execute('SELECT key,value FROM joolan_state'))
    if state.get('fresh_run') not in (job.get('runId'),previous['state'].get('fresh_run')):return
    with serving:
        for k,v in previous['state'].items():
            if v is None:serving.execute('DELETE FROM joolan_state WHERE key=?',(k,))
            else:serving.execute('INSERT OR REPLACE INTO joolan_state VALUES(?,?)',(k,v))
        if previous['season'] is None:serving.execute("DELETE FROM planning_state WHERE key='active_season'")
        else:serving.execute("INSERT OR REPLACE INTO planning_state VALUES('active_season',?)",(previous['season'],))
    c=fresh.connect(path)
    try:
        with c:
            old=previous['state'].get('fresh_run')
            if old:c.execute("INSERT OR REPLACE INTO state VALUES('active_run',?)",(old,))
            else:c.execute("DELETE FROM state WHERE key='active_run'")
    finally:c.close()

def recover(serving,c):
    ensure(c)
    for (jid,) in c.execute("SELECT id FROM automatic_jobs WHERE status IN ('queued','running','waiting')").fetchall():
        job=read(c,jid)
        if fresh.process_alive(job.get('pid')):continue
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(job['updatedAt'])).total_seconds()
        if job['status']=='queued' and age<120:continue
        meta=dict(serving.execute('SELECT key,value FROM pipeline_metadata'));lineage=json.loads(meta.get('lineage','{}'))
        if job.get('runId') and lineage.get('freshRun')==job['runId'] and lineage.get('seasonId')==job.get('seasonId') and lineage.get('createdAt','')>=job['createdAt']:
            update(c,jid,status='complete',phase='Forecast published',forecastRun=lineage['runId'],finishedAt=fresh.now())
        else:
            restore(serving,job)
            update(c,jid,status='paused',phase='Worker interrupted',error='Resume to continue saved export pages. The previous forecast was retained.')

def execute(jid,connection,path=None,exporter=None,pipeline=None,sleep=time.sleep,retry_seconds=3600):
    """Only the background process calls this. All stage state is durable."""
    c=fresh.connect(path);serving=connection();ensure(c);key=''
    try:
        with c:
            if c.execute("UPDATE automatic_jobs SET status='running',pid=? WHERE id=? AND status='queued'",(os.getpid(),jid)).rowcount!=1:return
        job=read(c,jid)
        from operating_scope import read as scope_read,primary
        if (scope_read(serving) or {}).get('revision')!=job['scope'].get('revision'):raise ValueError('Business scope changed. Dismiss this job and start a new forecast.')
        key,enseigne=server_credentials.credentials()
        config=dict(enseigne=enseigne,documentType='COMMANDE',throughDate=job['throughDate'],brands=job['scope']['brands'],
                    warehouses=primary(job['scope']))
        rid=job.get('runId')
        if not rid:
            rid=fresh.create_run(config,path);job=update(c,jid,runId=rid)
        rounds=0
        network_retries=0
        while True:
            key,_=server_credentials.credentials()
            state=c.execute('SELECT status FROM runs WHERE id=?',(rid,)).fetchone()[0]
            if state=='running':
                owner=c.execute('SELECT pid FROM runs WHERE id=?',(rid,)).fetchone()[0]
                if owner and not fresh.process_alive(owner):
                    fresh.update(c,rid,status='needs_credentials',phase='Resuming saved checkpoint after interruption')
                    state='needs_credentials'
            if state=='validated':break
            if state=='needs_mapping':raise ValueError('The export requires a data mapping review before it can be used for forecasts.')
            if state=='needs_credentials':
                fresh.claim_resume(rid,path)
            update(c,jid,status='running',phase='Downloading and reconciling Joolan data',error=None,retryAt=None)
            (exporter or fresh.run_export)(rid,key,path=path,reconcile=True)
            state,phase,error,report=c.execute('SELECT status,phase,error,report FROM runs WHERE id=?',(rid,)).fetchone()
            if state=='validated':break
            if phase=='Paused at Joolan quota':
                update(c,jid,status='waiting',phase='Waiting for Joolan quota reset; resumes automatically',
                    retryAt=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=retry_seconds)).isoformat(),attempts=read(c,jid)['attempts']+1)
                sleep(retry_seconds);continue
            if phase=='Transient connection failure' and network_retries<3:
                network_retries+=1;delay=30*network_retries
                update(c,jid,status='waiting',phase='Connection interrupted; retrying automatically',
                    retryAt=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=delay)).isoformat())
                sleep(delay);continue
            if error and ('Source changed' in error or 'automatic repair required' in error) and rounds<5:
                rounds+=1;update(c,jid,repairAttempts=rounds);continue
            raise ValueError(' '.join(json.loads(report or '{}').get('blockers',[])) or error or 'Export requires a mapping or permission review.')
        job=read(c,jid)
        update(c,jid,phase='Selecting forecast season and preparing catalogue prices')
        from planning import seasons,save_season,active_plan
        plans=seasons(serving)
        current=active_plan(serving)
        previous_mappings=None
        if current:
            from budgeting import settings
            previous_mappings=settings(serving)[0]
        chosen=current if current and current['startDate']==job['startDate'] and current['endDate']==job['endDate'] else next((s for s in plans if s['startDate']==job['startDate'] and s['endDate']==job['endDate']),None)
        state=dict(serving.execute('SELECT key,value FROM joolan_state'))
        active=serving.execute("SELECT value FROM planning_state WHERE key='active_season'").fetchone()
        if not job.get('rollback'):
            job=update(c,jid,rollback=dict(season=active[0] if active else None,state={k:state.get(k) for k in ('forecast_source','fresh_run','fresh_report')}))
        if chosen:
            with serving:serving.execute("INSERT OR REPLACE INTO planning_state VALUES('active_season',?)",(chosen['id'],))
        else:
            chosen=save_season(serving,dict(name=f"{job['startDate']} to {job['endDate']}",startDate=job['startDate'],endDate=job['endDate'],currency=current['currency'] if current else 'EUR',budget=0,targetMargin=0))
            if previous_mappings:
                from budgeting import save_settings
                save_settings(serving,{**previous_mappings,'budgetConfigured':False})
        job=update(c,jid,seasonId=chosen['id'])
        fresh.activate(rid,serving,path)
        import catalogue
        catalogue.sync(serving,path)
        from workflow import readiness
        checked=readiness(serving)
        if not checked['ready']:raise ValueError(' '.join(checked['blockers']))
        update(c,jid,phase='Training, validating and publishing forecast',warnings=checked['warnings'])
        if pipeline:pipeline()
        else:
            from main import run_phase1
            run_phase1()
        meta=dict(serving.execute('SELECT key,value FROM pipeline_metadata'));lineage=json.loads(meta.get('lineage','{}'))
        if lineage.get('freshRun')!=rid or lineage.get('seasonId')!=chosen['id']:raise ValueError('Forecast publication did not match the requested source and season.')
        update(c,jid,status='complete',phase='Forecast published',forecastRun=lineage['runId'],finishedAt=fresh.now(),error=None)
    except Exception as error:
        job=read(c,jid);restore(serving,job,path)
        message=(str(error).replace(key,'[hidden]') if key else str(error)) if isinstance(error,ValueError) else 'Automatic forecast failed. Saved export pages and the previous published forecast were retained. Retry or review the data-quality report.'
        update(c,jid,status='paused',phase='Needs attention',error=message[:800],retryAt=None)
    finally:serving.close();c.close()

def install(app,connection):
    from fastapi import Body,HTTPException
    from starlette.responses import JSONResponse
    @app.middleware('http')
    async def managed_job_guard(request,call_next):
        path=request.url.path
        if request.method not in ('GET','OPTIONS') and not path.startswith('/api/automatic') and (
            path.startswith('/api/seasons') or path.startswith('/api/joolan/') or path in ('/api/operating-scope','/api/forecast/refresh','/api/catalogue/prices','/api/budget/settings')):
            c=connection()
            try:locked=busy(serving=c)
            finally:c.close()
            if locked:return JSONResponse({'detail':'An automatic forecast is managing this data and season. Wait for it to finish.'},409)
        return await call_next(request)

    @app.get('/api/automatic')
    def status():
        c=fresh.connect();s=connection()
        try:
            recover(s,c);job=latest(c)
            source=fresh.status()
            export=source['run'] if job and source['run'] and source['run']['id']==job.get('runId') else None
            return dict(configured=server_credentials.configured(),enseigne=server_credentials.settings()['JOOLAN_ENSEIGNE'],
                job=public(job) if job else None,export=export)
        finally:s.close();c.close()

    @app.post('/api/automatic')
    def start(body:dict=Body(...)):
        s=connection()
        try:
            if set(body)!={'startDate','endDate'}:raise ValueError('Only forecast startDate and endDate are accepted. Configure credentials on the server.')
            job=create(s,body['startDate'],body['endDate']);launch(job['id']);return public(job)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:s.close()

    @app.post('/api/automatic/{jid}/resume')
    def resume(jid:str):
        c=fresh.connect()
        try:
            server_credentials.credentials()
            ensure(c)
            with c:
                if c.execute("UPDATE automatic_jobs SET status='queued',pid=NULL,updated_at=? WHERE id=? AND status='paused'",(fresh.now(),jid)).rowcount!=1:raise ValueError('Only a paused job can be resumed.')
            update(c,jid,error=None,phase='Queued to resume',pid=None);launch(jid);return public(read(c,jid))
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.post('/api/automatic/{jid}/dismiss')
    def dismiss(jid:str):
        c=fresh.connect()
        try:
            ensure(c)
            with c:
                if c.execute("UPDATE automatic_jobs SET status='cancelled' WHERE id=? AND status='paused'",(jid,)).rowcount!=1:raise ValueError('Only a paused job can be dismissed.')
            return dict(status='cancelled')
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()
