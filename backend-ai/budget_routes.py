"""Local financial configuration and a small read-only currency reference import."""
import json
from fastapi import Body,HTTPException,Query
from pydantic import BaseModel,SecretStr
import budgeting
import buying
import fresh_joolan as fresh
import purchase_draft
import price_review

class CurrencyRequest(BaseModel):
    apiKey:SecretStr

def install(app,connection):
    @app.get('/api/budget/reconciliation')
    def purchasing_inputs(scenario:str='base',issue:str='all',search:str='',offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
        c=connection()
        try:
            from purchasing_inputs import view
            return view(purchase_draft.view(c,budgeting.build_report(c,scenario)),issue,search,offset,limit)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.get('/api/budget/draft')
    def draft(scenario:str='base'):
        c=connection()
        try:return purchase_draft.view(c,budgeting.build_report(c,scenario))
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.put('/api/budget/draft')
    def save_draft(body:dict=Body(...)):
        c=connection()
        try:
            from catalogue import sync
            sync(c)
            with c:
                c.execute('BEGIN IMMEDIATE')
                report=budgeting.build_report(c,body.get('scenario','base'),sync_catalogue=False)
                return purchase_draft.store(c,report,body)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.post('/api/budget/draft/review')
    def review_draft(body:dict=Body(...)):
        c=connection()
        try:
            from catalogue import sync
            sync(c)
            with c:
                c.execute('BEGIN IMMEDIATE')
                report=budgeting.build_report(c,body.get('scenario','base'),sync_catalogue=False)
                current=purchase_draft.view(c,report);draft=current['draft']
                if not draft['version'] or draft['stale'] or body.get('version')!=draft['version'] or body.get('forecastRun')!=draft['forecastRun']:
                    raise ValueError('Draft changed. Save and review its latest version first.')
                record=buying.validate(c,report,draft['edits'],draft['selected'],draft['revision'],'forecast',commit=False,saved_inputs=draft.get('resolvedInputs'),price_reviews=price_review.approvals(c,purchase_draft.record_context(draft)))
                record.update(draftVersion=draft['version'],forecastRun=draft['forecastRun'])
                c.execute('INSERT OR REPLACE INTO planning_state VALUES(?,?)',('buying_review:'+record['id'],json.dumps(record)))
                return record
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.post('/api/budget/draft/prices/review')
    def review_prices(body:dict=Body(...)):
        c=connection()
        try:
            from catalogue import sync
            sync(c)
            with c:
                c.execute('BEGIN IMMEDIATE')
                report=budgeting.build_report(c,body.get('scenario','base'),sync_catalogue=False)
                current=purchase_draft.view(c,report)
                price_review.record(c,purchase_draft.record_context(current['draft']),current,body)
                return purchase_draft.view(c,report)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.post('/api/budget/simulate')
    def simulate_orders(body:dict=Body(...)):
        c=connection()
        try:return buying.simulate(budgeting.build_report(c,body.get('scenario','base')),body.get('edits',[]),body.get('quantityBasis','net'))
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()

    @app.post('/api/budget/validate')
    def validate_orders(body:dict=Body(...)):
        c=connection()
        try:
            if dict(c.execute('SELECT key,value FROM joolan_state')).get('source_policy')=='fresh_only':
                raise ValueError('Save the shared purchase draft and validate it from Order Review.')
            return buying.validate(c,budgeting.build_report(c,body.get('scenario','base')),body.get('edits',[]),body.get('selected',[]),body.get('revision'),body.get('quantityBasis','net'))
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.get('/api/budget/reviews')
    def reviewed_orders():
        c=connection()
        try:return [json.loads(r[0]) for r in c.execute("SELECT value FROM planning_state WHERE key LIKE 'buying_review:%' ORDER BY rowid DESC LIMIT 20")]
        finally:c.close()

    @app.get('/api/budget/options')
    def budget_options():
        c=connection()
        try:return budgeting.options(c)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.put('/api/budget/settings')
    def budget_settings(body:dict=Body(...)):
        c=connection()
        try:return budgeting.save_settings(c,body)
        except (ValueError,TypeError,KeyError) as e:raise HTTPException(400,str(e)) from None
        finally:c.close()

    @app.post('/api/budget/currencies')
    def refresh_currencies(body:CurrencyRequest):
        key=body.apiKey.get_secret_value().strip()
        if not key:raise HTTPException(400,'Enter the Joolan API key.')
        c=connection();client=None;source=None
        try:
            rid,config,metadata,_=budgeting.source_identity(c)
            schema=json.loads(metadata.get('schema','{}')).get('tables',{})
            fields={str(col['name']).lower():col['name'] for col in schema.get('devises',[])}
            if 'devise' not in fields:raise ValueError('The Joolan currency reference table is unavailable.')
            selected=[fields[name] for name in ('devise','nom','code','currency_code') if name in fields]
            client=fresh.Client('https://go.joolan.com',config['enseigne'],key)
            count=client.count('devises')
            if not 0<count<=1000:raise ValueError('Unexpected currency table size. No reference data was replaced.')
            records=client.query('SELECT '+', '.join(map(fresh.identifier,selected))+' FROM `devises` ORDER BY `Devise` LIMIT 1000')
            if len(records)!=count or client.count('devises')!=count:raise ValueError('Currency records changed during import; retry the lookup.')
            if dict(c.execute('SELECT key,value FROM joolan_state')).get('fresh_run')!=rid:raise ValueError('The active source changed. Retry the currency lookup.')
            ids=[budgeting.text(fresh.field(r,'Devise')) for r in records]
            if len(set(ids))!=len(ids):raise ValueError('Ambiguous currency reference codes.')
            source=fresh.connect()
            with source:
                source.execute("DELETE FROM records WHERE run_id=? AND dataset='devises'",(rid,))
                source.executemany('INSERT INTO records VALUES(?,?,?,?)',[(rid,'devises',fresh.encode([fresh.field(r,'Devise')]),fresh.encode(r)) for r in records])
                source.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(rid,'devises',fresh.encode(dict(complete=True,count=count,expected=count,exported=count,fetchedAt=fresh.now(),source='query.do:devises',purpose='currency reference; no exchange-rate conversion'))))
            return dict(imported=count,notice='Currency labels imported from Joolan. Conversion uses only verified recorded order rates; unknown currencies or rates remain unresolved.')
        except fresh.RateLimitError:raise HTTPException(429,'Joolan quota reached. Retry the currency lookup after reset.') from None
        except (ValueError,fresh.ExportError):raise HTTPException(400,'Currency lookup failed. Check api_query permission, the key and the currency reference table; saved export data was preserved.') from None
        finally:
            c.close()
            if source:source.close()
            if client:client.close()
