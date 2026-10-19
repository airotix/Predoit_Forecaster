"""One durable purchase draft per published forecast, season and scenario.

Catalogue values are defaults; only explicit draft assumptions are stored here.
Writes use optimistic versions inside the caller's transaction.
"""
import datetime as dt
import hashlib
import json
import buying
import price_review
from planning import SCENARIOS, active_plan


def enabled(conn):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='joolan_state'").fetchone() and
                dict(conn.execute('SELECT key,value FROM joolan_state')).get('source_policy')=='fresh_only')


def context(conn, scenario):
    if scenario not in SCENARIOS: raise ValueError('Unknown scenario.')
    meta = dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
    lineage = json.loads(meta.get('lineage', '{}'))
    plan = active_plan(conn)
    if not plan or not lineage.get('runId'): raise ValueError('Publish a forecast for the selected season first.')
    if lineage.get('seasonId') != plan['id']: raise ValueError('Publish a forecast for the selected season first.')
    return dict(seasonId=plan['id'], forecastRun=lineage['runId'], sourceRun=lineage.get('freshRun'),
                scopeRevision=lineage.get('operatingScopeRevision'), scenario=scenario)


def key(ctx):
    return 'purchase_draft:' + hashlib.sha256(json.dumps(ctx, sort_keys=True).encode()).hexdigest()


def read(conn, scenario):
    ctx = context(conn, scenario)
    row = conn.execute('SELECT value FROM planning_state WHERE key=?', (key(ctx),)).fetchone()
    return json.loads(row[0]) if row else dict(**ctx, version=0, edits=[], selected=[], revision=None, updatedAt=None)


def view(conn, report):
    draft = read(conn, report['scenario'])
    # Retain previous recommendation adjustments as the initial draft assumptions.
    if not draft['version']:
        draft['edits'] = [dict(id=buying.identity(r), quantity=r['manualOverride'], reason='Previously saved recommendation')
                          for r in report['rows'] if r.get('manualOverride') is not None]
    valid = {buying.identity(r) for r in report['rows']}
    edits = [e for e in draft['edits'] if e['id'] in valid]
    orphaned = len(draft['edits']) - len(edits)
    currency_changed=bool(draft.get('currency') and draft['currency']!=report['summary']['currency'])
    # Migrate older snapshots that predate explicit quote identity storage.
    for edit in edits:
        if edit['id'] in draft.get('resolvedInputs',{}):
            draft['resolvedInputs'][edit['id']].setdefault('quoteId',edit.get('quoteId',''))
    if currency_changed:
        edits=[{k:v for k,v in e.items() if k not in ('unitCost','unitPrice','quoteId','supplier')} for e in edits]
    # A removed supplier quote remains visible as a change requiring review.
    try:
        result = buying.simulate(report, edits, 'forecast', None if currency_changed else draft.get('resolvedInputs'), price_review.approvals(conn,record_context(draft)))
        invalid_quote = False
    except ValueError as e:
        if 'Supplier price changed' not in str(e): raise
        edits = [{k:v for k,v in e.items() if k != 'quoteId'} for e in edits]
        result = buying.simulate(report, edits, 'forecast', None if currency_changed else draft.get('resolvedInputs'), price_review.approvals(conn,record_context(draft)))
        invalid_quote = True
    draft = dict(draft, edits=edits, selected=[s for s in draft['selected'] if s in valid],
                 stale=bool(draft['version'] and (draft['revision'] != result['revision'] or orphaned or invalid_quote or currency_changed)),
                 excludedEdits=orphaned, supplierPriceChanged=invalid_quote, currencyChanged=currency_changed)
    return dict(result, draft=draft)


def store(conn, report, body):
    previous = read(conn, report['scenario'])
    if type(body.get('version')) is not int or body['version'] != previous['version']:
        raise ValueError('This draft was changed in another page. Reload before saving your changes.')
    edits = body.get('edits', [])
    if type(body.get('refreshPrices',False)) is not bool:
        raise ValueError('Refresh prices must be true or false.')
    snapshot={k:dict(v) for k,v in previous.get('resolvedInputs',{}).items()} if previous.get('currency')==report['summary']['currency'] else {}
    for edit in previous['edits']:
        if edit['id'] in snapshot:
            snapshot[edit['id']].setdefault('quoteId',edit.get('quoteId',''))
    if body.get('refreshPrices'):
        snapshot={k:{f:v for f,v in row.items() if f not in ('cost','price')} for k,row in snapshot.items()}
    old_edits = {e['id']:e for e in previous['edits']}
    if isinstance(edits,list):
        for edit in edits:
            if isinstance(edit,dict) and edit.get('quoteId') and 'unitCost' not in edit and 'unitCost' in old_edits.get(edit.get('id'),{}):
                # Removing an explicit override by selecting the supplier quote
                # must adopt its price, even when the quote identity is unchanged.
                snapshot.get(edit['id'],{}).pop('cost',None)
    result = buying.simulate(report, edits, 'forecast', snapshot, price_review.approvals(conn,record_context(previous)))
    calculated={r['id']:r for r in result['rows']}
    fields=dict(quantity='quantity',unitCost='orderUnitCost',unitPrice='orderUnitPrice',sellThrough='sellThrough')
    edits=[{k:calculated[e['id']][fields[k]] if k in fields else calculated[e['id']]['quoteId'] if k=='quoteId' else v for k,v in e.items()} for e in edits]
    if body.get('revision') != result['revision']:
        raise ValueError('Prices, settings or forecast changed. Reload and review before saving.')
    if body.get('forecastRun') != previous['forecastRun']:
        raise ValueError('The published forecast changed. Reload the draft.')
    selected = body.get('selected', [])
    allowed = {r['id'] for r in result['rows']}
    if not isinstance(selected, list) or any(not isinstance(s,str) or s not in allowed for s in selected) or len(set(selected)) != len(selected):
        raise ValueError('Select variants from the current draft.')
    new_edits = {e['id']:e for e in edits}
    for ident in old_edits.keys() | new_edits.keys():
        if old_edits.get(ident) == new_edits.get(ident): continue
        reference, color, _ = json.loads(ident)
        locked = conn.execute('SELECT locked FROM sku_locks WHERE reference=? AND couleur=?',(reference,color)).fetchone()
        if locked and locked[0]: raise ValueError('Unlock this recommendation before editing its draft assumptions.')
    record = dict(**context(conn, report['scenario']), version=previous['version']+1,
                  edits=edits, selected=selected, revision=result['revision'],
                  resolvedInputs={r['id']:dict(quantity=r['quantity'],cost=r['orderUnitCost'],price=r['orderUnitPrice'],stock=r['stock'],incoming=r['incoming'],sellThrough=r['sellThrough'],quoteId=r['quoteId']) for r in result['rows']},
                  currency=result['currency'], updatedAt=dt.datetime.now(dt.timezone.utc).isoformat())
    if previous['version']:
        conn.execute('INSERT OR IGNORE INTO planning_state VALUES(?,?)',
                     (key(record_context(previous))+':version:'+str(previous['version']),json.dumps(previous)))
    conn.execute('INSERT OR REPLACE INTO planning_state VALUES(?,?)', (key(record_context(record)), json.dumps(record)))
    return dict(result, draft=dict(record, stale=False, excludedEdits=0, supplierPriceChanged=False))


def record_context(record):
    return {k:record[k] for k in ('seasonId','forecastRun','sourceRun','scopeRevision','scenario')}


def recommendation_edit(conn, report, reference, color, quantities, reason, version, forecast_run):
    current = view(conn, report)
    if current['draft']['stale']:
        raise ValueError('Prices or settings changed. Review and save the draft in Budget Tracker before editing recommendations.')
    edits = {e['id']:e for e in current['draft']['edits']}
    for size, quantity in quantities:
        ident = buying.identity(dict(reference=reference, color=color, size=size))
        edits[ident] = dict(edits.get(ident, {}), id=ident, quantity=quantity, reason=reason)
    return store(conn, report, dict(version=version, forecastRun=forecast_run,
        revision=current['revision'], edits=list(edits.values()), selected=current['draft']['selected']))
