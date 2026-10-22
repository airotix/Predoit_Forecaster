"""Editable, local supplier PO drafts derived from the saved buying plan.

No Joolan writes or supplier communications. Budget snapshots, amendments and
line claims survive forecast publication; a source refresh never rewrites a PO.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
import uuid
from decimal import Decimal,ROUND_HALF_UP

import budgeting
import buying
import purchase_draft


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS supplier_purchase_orders(
        id TEXT PRIMARY KEY,number TEXT UNIQUE NOT NULL,context_key TEXT NOT NULL,
        season_id TEXT NOT NULL,scenario TEXT NOT NULL,status TEXT NOT NULL,
        version INTEGER NOT NULL,payload TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS supplier_po_versions(
        order_id TEXT,version INTEGER,payload TEXT NOT NULL,PRIMARY KEY(order_id,version))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS supplier_po_claims(
        context_key TEXT,line_id TEXT,order_id TEXT NOT NULL,PRIMARY KEY(context_key,line_id))''')
    conn.execute('CREATE TABLE IF NOT EXISTS supplier_po_sequences(year TEXT PRIMARY KEY,value INTEGER NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS supplier_po_season ON supplier_purchase_orders(season_id,scenario)')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def source_stamp(conn, scenario):
    config, plan = budgeting.settings(conn)
    context = purchase_draft.context(conn, scenario)
    _, _, _, revision = budgeting.source_identity(conn)
    markers = list(conn.execute("SELECT key,value FROM planning_state WHERE key IN ('catalogue_source','catalogue_prices_updated','historical_price_import','supplier_price_import','order_price_import','catalogue_status_source','catalogue_status_updated') ORDER BY key"))
    draft = purchase_draft.read(conn, scenario)
    return hashlib.sha256(json.dumps([context, config, plan, revision, markers, draft], sort_keys=True).encode()).hexdigest()


def supplier_options(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_skus'").fetchone():
        return []
    values = {r[0] for r in conn.execute("SELECT DISTINCT supplier FROM catalogue_skus WHERE current=1 AND supplier<>''")}
    import fresh_joolan as fresh
    state = dict(conn.execute('SELECT key,value FROM joolan_state'))
    if state.get('fresh_run'):
        source = fresh.connect()
        try:
            values.update(budgeting.text(fresh.field(r, 'Fournisseur')) for r in fresh.rows(source, state['fresh_run'], 'fournisseurs'))
        finally:
            source.close()
    return sorted(values - {''})


def line_totals(line):
    qty, cost, price = (line.get(k) for k in ('quantity', 'unitCost', 'unitPrice'))
    sold = qty * line['sellThrough'] / 100 if qty is not None else None
    purchase = budgeting.amount(qty, cost) if qty != 0 else 0.
    turnover = budgeting.amount(sold, price) if qty != 0 else 0.
    cogs = budgeting.amount(sold, cost) if qty != 0 else 0.
    margin = round(turnover - cogs, 2) if turnover is not None and cogs is not None else None
    return dict(purchaseCost=purchase, turnover=turnover, grossMargin=margin,
                marginRate=margin / turnover * 100 if margin is not None and turnover else None)


def selling_price_updates(conn, ident):
    """Preview current saved prices. Never change an existing PO on a read."""
    doc = _read(conn, ident)
    if doc['status'] not in ('draft', 'pending_validation'):
        raise ValueError('Only editable PO drafts can refresh selling prices.')
    from catalogue import price_map
    catalogue = price_map(conn, doc['currency'])
    try:
        draft = purchase_draft.read(conn, doc['scenario'])
    except (ValueError, KeyError):
        draft = {}
    matches = all(draft.get(k) == doc.get(k) for k in ('seasonId', 'forecastRun', 'sourceRun'))
    saved = draft.get('resolvedInputs', {}) if matches and draft.get('currency') == doc['currency'] else {}
    edits = {r['id']: r for r in draft.get('edits', [])} if saved else {}
    changes = []; protected = 0
    for line in doc['lines']:
        if line['unitPrice'] != line['original']['unitPrice']:
            protected += 1
            continue
        value = saved.get(line['id'], {}).get('price')
        if 'unitPrice' in edits.get(line['id'], {}):
            value = edits[line['id']]['unitPrice']
        source = 'Saved Budget Tracker selling price'
        if value is None:
            value = catalogue.get((line['reference'], line['color'], line['size']), {}).get('selling')
            source = 'Saved Catalogue selling price'
        if value is not None and value != line['unitPrice']:
            changes.append(dict(id=line['id'],reference=line['reference'],color=line['color'],size=line['size'],
                                previous=line['unitPrice'],unitPrice=value,source=source))
    return dict(version=doc['version'], changes=changes, protectedOverrides=protected,
                notice='Preview only. Apply and save to update this PO. Manual PO prices are retained.')


def native_unit(cost,fx):
    if cost is None:return None
    return float((Decimal(str(cost))*Decimal(str(fx['exchangeRate']))).quantize(Decimal('.000001'),rounding=ROUND_HALF_UP)) if fx else cost


def budget_unit(cost,fx):
    if cost is None:return None
    return float((Decimal(str(cost))/Decimal(str(fx['exchangeRate']))).quantize(Decimal('.000001'),rounding=ROUND_HALF_UP)) if fx else cost


def totals(lines):
    calculated = [line_totals(line) for line in lines]
    result = {}
    for field in ('purchaseCost', 'turnover', 'grossMargin'):
        result['known' + field[0].upper() + field[1:]] = round(sum(r[field] or 0 for r in calculated), 2)
        result[field] = result['known' + field[0].upper() + field[1:]] if all(r[field] is not None for r in calculated) else None
    result['marginRate'] = result['grossMargin'] / result['turnover'] * 100 if result['grossMargin'] is not None and result['turnover'] else None
    result['units'] = sum(line['quantity'] or 0 for line in lines) if all(line['quantity'] is not None for line in lines) else None
    result['articles'] = len({line['reference'] for line in lines})
    result['variants'] = len(lines)
    return result


def _read(conn, ident):
    row = conn.execute('SELECT payload FROM supplier_purchase_orders WHERE id=?', (ident,)).fetchone()
    if not row:
        raise ValueError('Purchase order not found.')
    return json.loads(row[0])


def _batch(conn, doc):
    peers = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM supplier_purchase_orders WHERE season_id=? AND status<>'cancelled'", (doc['seasonId'],))]
    peers = [peer for peer in peers if peer['scenario']==doc['scenario'] or peer['status']=='validated']
    peers = [peer for peer in peers if peer['currency'] == doc['currency']]
    lines = [line for peer in peers for line in peer['lines']]
    combined = totals(lines)
    baseline = max(peers, key=lambda p:p['createdAt'])['budget'] if peers else doc['budget']
    known = round(combined['knownPurchaseCost'] + baseline['knownCommitments'], 2)
    complete = combined['purchaseCost'] is not None and baseline['commitmentsComplete']
    return dict(**combined, orders=len(peers), currency=doc['currency'], buyingBudget=baseline['amount'],
                knownCommitments=baseline['knownCommitments'], commitmentsComplete=baseline['commitmentsComplete'],
                provisionalRemaining=round(baseline['amount'] - known, 2),
                remaining=round(baseline['amount'] - known, 2) if complete else None,
                overBudget=known > baseline['amount'])


def view(conn, ident):
    ensure(conn)
    doc = _read(conn, ident)
    try:
        changed = source_stamp(conn, doc['scenario']) != doc['sourceStamp']
    except (ValueError, KeyError):
        changed = True
    lines = [dict(line, **line_totals(line),supplierPurchaseCost=0. if line['quantity']==0 else budgeting.amount(line['quantity'],line.get('supplierUnitCost',line['unitCost']))) for line in doc['lines']]
    from catalogue_status import variant_map
    current_statuses=variant_map(conn,references=sorted({line['reference'] for line in lines}))
    checks = set()
    for line in lines:
        if line.get('priceReview') and (doc['supplier'] != line['sourceSupplier'] or
            any(line[field] != line['original'][field] for field in ('unitCost','unitPrice')) or
            line.get('supplierUnitCost')!=line['original'].get('supplierUnitCost',line.get('supplierUnitCost'))):
            line['budgetPriceReview']=line['priceReview']
            line['priceReview']=None
            checks.add('PO prices or supplier differ from the budget price confirmation. Review these changes before use.')
    for line in doc['lines']:
        checks.update(c for c in line['sourceChecks'] if c in (
            'Stock or incoming supply unresolved', 'Customer delivery commitments need reconciliation',
            'Launch/assortment estimate requires planner review',
            'Supplier lead time misses the next recorded customer delivery'))
    if changed:
        checks.add('The source budget, catalogue, scope or forecast changed. This PO retains its saved snapshot; compare it with Budget Tracker before using it.')
    if not doc['supplier']:
        checks.add('Assign a supplier.')
    if any(line.get('fx') for line in lines):
        checks.add('Financial totals use historical recorded order FX. Supplier documents retain native currency; actual settlement rates may differ.')
    for line in lines:
        if line['quantity'] is None:
            checks.add('Some order quantities are missing.')
        if not line['quantity']:
            continue
        status=current_statuses.get((line['reference'],line['color'],line['size']),{})
        if status.get('purchasingBlocked'):
            checks.add(f"{line['reference']} / {line['color']} / {line['size']}: {status['reason']}. Review or remove this purchase quantity.")
        if line['unitCost'] is None:
            checks.add('Some purchase prices are missing.')
        if line['unitPrice'] is None:
            checks.add('Some selling prices are missing for financial review.')
        if line['marginRate'] is None:
            checks.add('Some margin rates cannot be calculated.')
        elif line['marginRate'] < doc['budget']['targetMargin']:
            checks.add('Some lines are below the target gross margin.')
        from order_constraints import violations
        checks.update(violations(line['quantity'], line.get('orderingRules', {})))
    from order_constraints import article_violations
    checks.update(article_violations(lines).values())
    edited = any(any(line[field] != line['original'][field] for field in ('quantity','unitCost','unitPrice','sellThrough')) or
                 line.get('supplierUnitCost') != line['original'].get('supplierUnitCost',line.get('supplierUnitCost')) for line in lines)
    if edited and not doc['changeReason'].strip():
        checks.add('Record a reason for the PO quantity or price changes.')
    batch = _batch(conn, doc)
    if batch['overBudget']:
        checks.add('The combined supplier PO drafts and known existing commitments exceed the buying budget.')
    if not batch['commitmentsComplete']:
        checks.add('Existing supplier commitments are incomplete; the budget balance is provisional.')
    native_complete=all(line['supplierPurchaseCost'] is not None for line in lines)
    return dict(doc, lines=lines, totals=totals(lines), batch=batch, sourceChanged=changed,
                supplierTotals=dict(currency=doc.get('supplierCurrency',doc['currency']),purchaseCost=round(sum(line['supplierPurchaseCost'] or 0 for line in lines),2) if native_complete else None),
                checks=sorted(checks), history=[dict(version=r[0],updatedAt=json.loads(r[1])['updatedAt']) for r in conn.execute('SELECT version,payload FROM supplier_po_versions WHERE order_id=? ORDER BY version DESC', (ident,))])


def listing(conn, season_id, scenario):
    ensure(conn)
    docs = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM supplier_purchase_orders WHERE season_id=? AND scenario=? ORDER BY rowid DESC', (season_id, scenario))]
    return [dict(id=d['id'],number=d['number'],supplier=d['supplier'],status=d['status'],version=d['version'],
                 currency=d['currency'],forecastRun=d['forecastRun'],budgetVersion=d['budgetVersion'],
                 createdAt=d['createdAt'],updatedAt=d['updatedAt'],totals=totals(d['lines'])) for d in docs]


def create(conn, simulation, body, stamp):
    """Caller holds BEGIN IMMEDIATE; line claims make repeated imports idempotent."""
    ensure(conn)
    draft = simulation['draft']
    if not draft['version'] or draft['stale']:
        raise ValueError('Save and recalculate the current Budget Tracker draft before creating purchase orders.')
    if type(body.get('version')) is not int or body.get('version') != draft['version'] or body.get('forecastRun') != draft['forecastRun'] or body.get('revision') != simulation['revision']:
        raise ValueError('The budget draft changed. Reload before creating purchase orders.')
    mode = body.get('mode', 'all')
    if mode not in ('all', 'fitting', 'selected'):
        raise ValueError('Choose all quantities, articles fitting budget, or selected articles.')
    fitting = {a['reference'] for a in simulation['articlePlan']['articles'] if a['status'] == 'included'}
    selected = set(draft['selected'])
    ctx = purchase_draft.record_context(draft)
    # A later budget version cannot quietly order the same forecast variant twice.
    context_key = hashlib.sha256(json.dumps({k:ctx[k] for k in ('seasonId','forecastRun','scenario')},sort_keys=True).encode()).hexdigest()
    peers = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM supplier_purchase_orders WHERE context_key=? AND status<>'cancelled'", (context_key,))]
    if any(peer['currency'] != simulation['currency'] for peer in peers):
        raise ValueError('This forecast already has PO drafts in another currency. Cancel or reconcile those drafts before creating orders in the new currency.')
    claimed = dict(conn.execute('SELECT line_id,order_id FROM supplier_po_claims WHERE context_key=?', (context_key,)))
    suppliers = {}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_skus'").fetchone():
        for ref,color,size,supplier in conn.execute('SELECT reference,color,size,supplier FROM catalogue_skus WHERE current=1'):
            suppliers.setdefault((ref,color,size),set()).add(supplier)
    groups = {}; existing = set(); skipped = 0
    reasons = {a['reference']:a['reason'] for a in simulation['articlePlan']['articles']}
    for row in simulation['rows']:
        if mode == 'fitting' and row['reference'] not in fitting or mode == 'selected' and row['id'] not in selected:
            continue
        if row['quantity'] is None:
            raise ValueError(f"Set an order quantity for {row['reference']} / {row['color']} / {row['size']} before creating its PO.")
        if row['quantity'] <= 0:continue
        if row.get('purchasingBlocked') or row.get('orderingRules',{}).get('blocked'):
            raise ValueError(f"{row['reference']} / {row['color']} / {row['size']} is blocked for purchasing. Set its budget quantity to zero or review its Catalogue status before creating POs.")
        if row['id'] in claimed:
            existing.add(claimed[row['id']]); skipped += 1; continue
        quote = next((q for q in row['quotes'] if q['id'] == row['quoteId']), None)
        choices = suppliers.get((row['reference'],row['color'],row['size']),set()) - {''}
        supplier = row.get('supplier') or (quote['supplier'] if quote else row.get('purchasePriceDetails',{}).get('supplier') or (next(iter(choices)) if len(choices)==1 else ''))
        values = dict(quantity=row['quantity'],unitCost=row['orderUnitCost'],unitPrice=row['orderUnitPrice'],sellThrough=row['sellThrough'])
        detail=row.get('purchasePriceDetails') or {}
        fx=quote.get('fx') if quote else detail.get('fx') if detail.get('currency')==simulation['currency'] else None
        supplier_currency=fx['nativeCurrency'] if fx else simulation['currency']
        source_cost=quote.get('unitCost') if quote else detail.get('price')
        supplier_cost=fx['nativeUnitCost'] if fx and row['orderUnitCost']==source_cost else native_unit(row['orderUnitCost'],fx)
        values['supplierUnitCost']=supplier_cost
        line = dict(id=row['id'],reference=row['reference'],color=row['color'],size=row['size'],name=row['name'],
                    forecast=row['forecast'],budgetQuantity=row['quantity'],**values,original=values.copy(),
                    sourceSupplier=supplier,purchaseSource=row['costBasis'],sellingSource=row.get('priceBasis',''),
                    priceReview=row.get('priceReview'),supplierPrice=quote,fx=fx,supplierCurrency=supplier_currency,
                    purchasePriceDetails=detail,
                    assortmentReviewed='Launch/assortment estimate requires planner review' not in row['blockers'],
                    sourceChecks=row['blockers'],allocationReason=reasons.get(row['reference'],''),
                    orderingRules=row.get('orderingRules',{}))
        groups.setdefault((supplier,supplier_currency),[]).append(line)
    created = []; timestamp = now(); year = timestamp[:4]
    for (supplier,supplier_currency),lines in sorted(groups.items()):
        conn.execute('INSERT INTO supplier_po_sequences VALUES(?,1) ON CONFLICT(year) DO UPDATE SET value=value+1', (year,))
        number = f"PO-{year}-{conn.execute('SELECT value FROM supplier_po_sequences WHERE year=?',(year,)).fetchone()[0]:06d}"
        doc = dict(id=uuid.uuid4().hex,number=number,version=1,status='draft',contextKey=context_key,
                   seasonId=ctx['seasonId'],seasonName=simulation['context']['season']['name'],forecastRun=ctx['forecastRun'],
                   sourceRun=ctx['sourceRun'],scenario=ctx['scenario'],budgetVersion=draft['version'],sourceStamp=stamp,
                   supplier=supplier,currency=simulation['currency'],supplierCurrency=supplier_currency,orderDate=timestamp[:10],deliveryDate='',
                   shipTo=', '.join(simulation['context']['settings']['warehouses']),notes='',changeReason='',
                   createdAt=timestamp,updatedAt=timestamp,lines=lines,
                   budget=dict(amount=simulation['summary']['budget'],targetMargin=simulation['summary']['targetMargin'],
                               knownCommitments=simulation['summary']['knownCommitments'],commitmentsComplete=simulation['summary']['commitmentsComplete']),
                   sourceChecks=list(dict.fromkeys(simulation['blockers'] + [c for line in lines for c in line['sourceChecks']])))
        conn.execute('INSERT INTO supplier_purchase_orders VALUES(?,?,?,?,?,?,?,?)', (doc['id'],number,context_key,doc['seasonId'],doc['scenario'],'draft',1,json.dumps(doc)))
        conn.executemany('INSERT INTO supplier_po_claims VALUES(?,?,?)', [(context_key,line['id'],doc['id']) for line in lines])
        created.append(doc['id'])
    if not created and not existing:
        raise ValueError('No positive quantities match this selection. Check the saved Budget Tracker draft.')
    return dict(created=created,existing=sorted(existing),skippedVariants=skipped,
                notice=f'{len(created)} supplier PO drafts created. {skipped} variants already have a PO and were not duplicated.')


def update(conn, ident, body):
    ensure(conn); doc = _read(conn, ident)
    if type(body.get('version')) is not int or body['version'] != doc['version']:
        raise ValueError('This PO was changed in another page. Reload before saving.')
    if doc['status'] not in ('draft','pending_validation'):
        raise ValueError('A cancelled or validated PO is read-only. Create a new draft from Budget Tracker if needed.')
    if set(body) - {'version','supplier','orderDate','deliveryDate','shipTo','notes','changeReason','edits','status'}:
        raise ValueError('Unsupported PO fields.')
    previous = json.dumps(doc)
    for field,limit in [('supplier',200),('shipTo',1000),('notes',4000),('changeReason',1000)]:
        if field in body:
            if not isinstance(body[field],str) or len(body[field]) > limit:
                raise ValueError(f'Enter a valid {field} (maximum {limit} characters).')
            doc[field] = body[field].strip()
    for field in ('orderDate','deliveryDate'):
        if field in body:
            value = body[field]
            if value == '' and field == 'deliveryDate': doc[field] = ''; continue
            try: doc[field] = dt.date.fromisoformat(value).isoformat()
            except (ValueError,TypeError): raise ValueError('Enter valid PO and delivery dates.') from None
    if doc['deliveryDate'] and doc['deliveryDate'] < doc['orderDate']:
        raise ValueError('Expected delivery cannot be before the PO date.')
    edits = body.get('edits',[]); by_id = {line['id']:line for line in doc['lines']}; seen = set()
    if not isinstance(edits,list) or len(edits)>len(by_id):
        raise ValueError('Invalid PO line changes.')
    for edit in edits:
        if not isinstance(edit,dict) or set(edit)-{'id','quantity','unitCost','unitPrice','sellThrough','supplierUnitCost'} or edit.get('id') not in by_id or edit['id'] in seen:
            raise ValueError('Select unique lines belonging to this PO.')
        if 'unitCost' in edit and 'supplierUnitCost' in edit:raise ValueError('Edit either the budget unit cost or the supplier unit cost, not both at once.')
        seen.add(edit['id'])
        for field in ('quantity','unitCost','unitPrice','sellThrough','supplierUnitCost'):
            if field not in edit: continue
            value = edit[field]
            if value is None and field != 'sellThrough': by_id[edit['id']][field] = None; continue
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 0 <= value <= 1e9:
                raise ValueError('PO quantities and prices must be finite, nonnegative numbers.')
            if field == 'quantity' and value != int(value): raise ValueError('PO quantities must be whole units.')
            if field == 'sellThrough' and value > 100: raise ValueError('Sell-through must be between 0 and 100%.')
            by_id[edit['id']][field] = value
        line=by_id[edit['id']]
        if 'unitPrice' in edit:line['sellingSource']='Manual PO selling-price assumption'
        if 'supplierUnitCost' in edit:line['unitCost']=budget_unit(line['supplierUnitCost'],line.get('fx'))
        elif 'unitCost' in edit:line['supplierUnitCost']=native_unit(line['unitCost'],line.get('fx'))
    status = body.get('status','draft')
    if status not in ('draft','cancelled'): raise ValueError('Save a draft here; final validation is a separate step.')
    doc.update(version=doc['version']+1,status=status,updatedAt=now())
    conn.execute('INSERT INTO supplier_po_versions VALUES(?,?,?)', (ident,doc['version']-1,previous))
    conn.execute('UPDATE supplier_purchase_orders SET version=?,status=?,payload=? WHERE id=?', (doc['version'],status,json.dumps(doc),ident))
    if status == 'cancelled': conn.execute('DELETE FROM supplier_po_claims WHERE order_id=?', (ident,))
    return doc


def export_csv(conn, ident):
    doc = view(conn, ident)
    if doc['status'] == 'cancelled': raise ValueError('Cancelled purchase orders cannot be exported.')
    final=doc['status']=='validated'
    output = io.StringIO(); writer = csv.writer(output)
    def safe(value):
        value = '' if value is None else str(value)
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value
    writer.writerow(['Status','PO number','Version','Supplier','Currency','PO date','Expected delivery','Ship to','Article','Description','Colour','Size','Quantity','Purchase / unit','Line purchase cost','Notes'])
    for line in doc['lines']:
        if line['quantity'] == 0: continue
        writer.writerow(map(safe,['VALIDATED - NOT SENT' if final else 'DRAFT - NOT SENT',doc['number'],doc['version'],doc['supplier'],doc.get('supplierCurrency',doc['currency']),doc['orderDate'],doc['deliveryDate'],doc['shipTo'],line['reference'],line['name'],line['color'],line['size'],line['quantity'],line.get('supplierUnitCost',line['unitCost']),line['supplierPurchaseCost'],doc['notes']]))
    return dict(filename=doc['number']+('-final.csv' if final else '-draft.csv'),csv='\ufeff'+output.getvalue())


def install(app, connection):
    from fastapi import Body, HTTPException
    from po_validation import install as install_validation
    install_validation(app,connection)

    @app.get('/api/purchase-orders')
    def orders(season_id:str, scenario:str='base'):
        c = connection()
        try: return dict(orders=listing(c,season_id,scenario),suppliers=supplier_options(c))
        finally: c.close()

    @app.get('/api/purchase-orders/{ident}')
    def order(ident:str):
        c = connection()
        try: return view(c,ident)
        except ValueError as e: raise HTTPException(409,str(e)) from None
        finally: c.close()

    @app.get('/api/purchase-orders/{ident}/selling-prices')
    def current_selling_prices(ident:str):
        c = connection()
        try:return selling_price_updates(c,ident)
        except ValueError as e:raise HTTPException(409,str(e)) from None
        finally:c.close()

    @app.post('/api/purchase-orders')
    def generate(body:dict=Body(...)):
        c = connection()
        try:
            ensure(c)
            from catalogue import sync
            sync(c)
            scenario = body.get('scenario','base'); before = source_stamp(c,scenario)
            simulation = purchase_draft.view(c,budgeting.build_report(c,scenario,sync_catalogue=False))
            with c:
                c.execute('BEGIN IMMEDIATE')
                if before != source_stamp(c,scenario): raise ValueError('Budget inputs changed during PO creation. Reload and try again.')
                return create(c,simulation,body,before)
        except (ValueError,KeyError,TypeError) as e: raise HTTPException(409,str(e)) from None
        finally: c.close()

    @app.put('/api/purchase-orders/{ident}')
    def save_order(ident:str,body:dict=Body(...)):
        c = connection()
        try:
            ensure(c)
            with c:
                c.execute('BEGIN IMMEDIATE'); update(c,ident,body)
            return view(c,ident)
        except (ValueError,KeyError,TypeError) as e: raise HTTPException(409,str(e)) from None
        finally: c.close()

    @app.get('/api/purchase-orders/{ident}/export')
    def download(ident:str):
        c = connection()
        try: return export_csv(c,ident)
        except ValueError as e: raise HTTPException(409,str(e)) from None
        finally: c.close()
