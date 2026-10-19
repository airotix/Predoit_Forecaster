"""Persisted planning inputs and final, scenario-specific purchase decisions."""
import datetime as dt
import json
import math
import uuid
import hashlib

SCENARIOS = ('conservative', 'base', 'optimistic')

def ensure_schema(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS planning_seasons(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS planning_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS planning_inputs(reference TEXT,couleur TEXT,taille TEXT,
        selling_price REAL,purchase_cost REAL,stock REAL,incoming REAL,
        PRIMARY KEY(reference,couleur,taille));
      CREATE TABLE IF NOT EXISTS order_lines(line_key TEXT PRIMARY KEY,payload TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS order_lines_customer_date ON order_lines(
        CAST(json_extract(payload,'$.Client') AS TEXT),substr(json_extract(payload,'$.Date_Commande'),1,10) DESC);
      CREATE INDEX IF NOT EXISTS order_lines_activity ON order_lines(
        CAST(json_extract(payload,'$.Client') AS TEXT),substr(json_extract(payload,'$.Date_Commande'),1,10),
        json_extract(payload,'$.true_demand'),json_extract(payload,'$.Reference_CDE'));
      CREATE TABLE IF NOT EXISTS derived_revisions(name TEXT PRIMARY KEY,version INTEGER NOT NULL);
      INSERT OR IGNORE INTO derived_revisions VALUES('order_lines',0);
      CREATE TRIGGER IF NOT EXISTS order_lines_insert_revision AFTER INSERT ON order_lines BEGIN
        UPDATE derived_revisions SET version=version+1 WHERE name='order_lines'; END;
      CREATE TRIGGER IF NOT EXISTS order_lines_update_revision AFTER UPDATE ON order_lines BEGIN
        UPDATE derived_revisions SET version=version+1 WHERE name='order_lines'; END;
      CREATE TRIGGER IF NOT EXISTS order_lines_delete_revision AFTER DELETE ON order_lines BEGIN
        UPDATE derived_revisions SET version=version+1 WHERE name='order_lines'; END;
    ''')
    from catalogue import ensure
    ensure(conn)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='user_overrides'").fetchone():
        columns={r[1] for r in conn.execute('PRAGMA table_info(user_overrides)')}
        for name,declaration in [('scenario',"TEXT NOT NULL DEFAULT 'base'"),('plan_id',"TEXT NOT NULL DEFAULT ''")]:
            if name not in columns:conn.execute(f'ALTER TABLE user_overrides ADD COLUMN {name} {declaration}')

def seasons(conn):
    return [json.loads(r[0]) for r in conn.execute('SELECT payload FROM planning_seasons ORDER BY rowid DESC')]

def active_plan(conn):
    row=conn.execute("SELECT value FROM planning_state WHERE key='active_season'").fetchone()
    if row:
        found=conn.execute('SELECT payload FROM planning_seasons WHERE id=?',(row[0],)).fetchone()
        if found:return json.loads(found[0])
    return None

def order_ledger_revision(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='derived_revisions'").fetchone():return None
    row=conn.execute("SELECT version FROM derived_revisions WHERE name='order_lines'").fetchone()
    return row[0] if row else None

def save_season(conn, data, season_id=None):
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    start=dt.date.fromisoformat(str(data['startDate']))
    end=dt.date.fromisoformat(str(data['endDate']))
    if end<start:raise ValueError('Season end must follow its start.')
    if not str(data.get('name','')).strip():raise ValueError('Enter a season name.')
    for name in ('budget','targetMargin'):
        if not math.isfinite(float(data[name])) or float(data[name])<0:raise ValueError('Budget and margin must be finite and nonnegative.')
    if float(data['targetMargin'])>100:raise ValueError('Margin must be between 0 and 100 percent.')
    if str(data.get('currency','')).upper() not in ('EUR','USD','GBP','CHF','CAD','AUD','PKR'):
        raise ValueError('Select a supported currency.')
    existing=conn.execute('SELECT payload FROM planning_seasons WHERE id=?',(season_id,)).fetchone() if season_id else None
    if season_id and not existing:raise ValueError('Season not found.')
    record=json.loads(existing[0]) if existing else dict(id=uuid.uuid4().hex,createdAt=now,status='draft')
    record.update({k:data[k] for k in ('name','startDate','endDate','currency','budget','targetMargin')})
    record['updatedAt']=now
    with conn:
        conn.execute('INSERT OR REPLACE INTO planning_seasons VALUES(?,?)',(record['id'],json.dumps(record)))
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('active_season',?)",(record['id'],))
    return record

def input_rows(conn):
    cols=('Reference','Couleur','Taille','Selling_Price','Purchase_Cost','STOCK','CDE_four_qte')
    values={(r[0],r[1],r[2]):dict(zip(cols,r)) for r in conn.execute('SELECT * FROM planning_inputs')}
    from catalogue import price_map
    plan=active_plan(conn)
    for key,prices in price_map(conn,(plan or {}).get('currency','EUR')).items():
        row=values.setdefault(key,dict(zip(cols,(*key,None,None,None,None))))
        if prices['purchase'] is not None:row['Purchase_Cost']=prices['purchase']
        if prices['selling'] is not None:row['Selling_Price']=prices['selling']
        for field,source in [('Purchase_Cost','purchase'),('Selling_Price','selling')]:
            if prices[source] is None:
                row[field]=None
                row['Clear_'+field]=True
    return list(values.values())

def apply_input_rows(raw,inputs):
    """Overlay planning inputs, preserving deliberately cleared catalogue prices."""
    import pandas as pd
    if not inputs:return
    mapped=pd.DataFrame(inputs).set_index(['Reference','Couleur','Taille'])
    lookup=pd.MultiIndex.from_frame(raw[['Reference','Couleur','Taille']])
    for column in ('Selling_Price','Purchase_Cost','STOCK','CDE_four_qte'):
        values=pd.Series(mapped[column].reindex(lookup).to_numpy(),index=raw.index)
        raw[column]=values.combine_first(raw[column]) if column in raw else values
        marker='Clear_'+column
        if marker in mapped:
            cleared=mapped[marker].reindex(lookup).eq(True).to_numpy()
            raw.loc[cleared,column]=float('nan')

def inputs_fingerprint(rows):
    encoded=sorted(json.dumps(row,sort_keys=True,separators=(',',':')) for row in rows)
    return hashlib.sha256(json.dumps(encoded).encode()).hexdigest()

def save_inputs(conn, rows):
    records=[]
    for row in rows:
        identifiers=[str(row.get(k,'')).strip() for k in ('Reference','Couleur','Taille')]
        if not all(identifiers):raise ValueError('Each input row needs Reference, Couleur and Taille.')
        values=[]
        for k in ('Selling_Price','Purchase_Cost','STOCK','CDE_four_qte'):
            v=row.get(k)
            if v is None or str(v).strip()=='':values.append(None);continue
            v=float(v)
            if not math.isfinite(v) or v<0:raise ValueError(k+' must be finite and nonnegative.')
            values.append(v)
        records.append(tuple(identifiers+values))
    with conn:conn.executemany('INSERT OR REPLACE INTO planning_inputs VALUES(?,?,?,?,?,?,?)',records)
    return len(records)

def final_rows(conn, scenario='base', season_id=None, include_draft=True, _saved_prices=None):
    if scenario not in SCENARIOS:raise ValueError('Unknown scenario.')
    meta=dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
    lineage=json.loads(meta.get('lineage','{}'))
    from operating_scope import revision
    scope_revision=revision(conn)
    if scope_revision and lineage.get('operatingScopeRevision')!=scope_revision:
        raise ValueError('Business scope changed. Refresh forecasts before reviewing purchase decisions.')
    plan=active_plan(conn)
    if plan and lineage.get('seasonId')!=plan['id']:
        raise ValueError('Refresh forecasts for the selected season before reviewing or exporting purchase decisions.')
    if plan and lineage.get('plan') and any(plan[k]!=lineage['plan'].get(k) for k in ('startDate','endDate')):
        raise ValueError('The planning dates changed. Refresh forecasts before reviewing or exporting purchase decisions.')
    if season_id and lineage.get('seasonId')!=season_id:
        raise ValueError('Refresh forecasts for the selected season before exporting or reviewing its budget.')
    cursor=conn.execute('SELECT * FROM recommendations ORDER BY reference,couleur,taille')
    columns=[d[0] for d in cursor.description]
    rows=[dict(zip(columns,r)) for r in cursor]
    overrides={}
    override_columns={r[1] for r in conn.execute('PRAGMA table_info(user_overrides)')}
    scope="WHERE scenario=? AND plan_id=?" if 'scenario' in override_columns else ''
    params=(scenario,lineage.get('seasonId') or '') if scope else ()
    for ref,color,size,value in conn.execute('SELECT reference,couleur,taille,override_qty FROM user_overrides '+scope+' ORDER BY updated_at DESC,rowid DESC',params):
        overrides.setdefault((ref,color,size),float(value))
    result=[]
    draft=None
    if include_draft and lineage.get('runId') and plan:
        from purchase_draft import read
        saved_draft=read(conn,scenario)
        if saved_draft['version'] and saved_draft.get('currency')==plan['currency']:draft=saved_draft
    draft_edits={e['id']:e for e in draft['edits']} if draft else {}
    from catalogue import price_map
    saved_prices=price_map(conn,(plan or {}).get('currency','EUR')) if _saved_prices is None else _saved_prices
    from catalogue_status import variant_map
    statuses=variant_map(conn)
    for row in rows:
        key=(row['reference'],row['couleur'],row['taille'])
        financial=str(row.get('financial_note',''))
        forecast=float(row.get('forecast_'+scenario) or 0)
        available=row.get('available_inventory')
        missing_inventory='INVENTORY_UNKNOWN' in financial or available is None
        required=row.get('required_future_'+scenario) if lineage.get('engine')=='calendar-validation-v2' else forecast
        recommended=0.0 if required==0 else None if required is None or missing_inventory else max(float(required)-float(available),0)
        status=statuses.get(key,{})
        blocked=status.get('purchasingBlocked',False)
        if blocked:recommended=0.0
        final=overrides.get(key,recommended)
        cost=row.get('unit_purchase_cost')
        price=row.get('unit_selling_price')
        saved=saved_prices.get(key,{})
        if key in saved_prices:cost=saved['purchase'];financial=financial.replace('COST_UNKNOWN','') if cost is not None else financial+';COST_UNKNOWN';row['unit_purchase_cost']=cost
        if key in saved_prices:price=saved['selling'];financial=financial.replace('PRICE_UNKNOWN','') if price is not None else financial+';PRICE_UNKNOWN';row['unit_selling_price']=price
        row['financial_note']=financial
        cost_known=cost is not None and 'COST_UNKNOWN' not in financial
        price_known=price is not None and 'PRICE_UNKNOWN' not in financial
        row.update(scenario=scenario,demand_forecast=forecast,future_demand=required,recommended_quantity=recommended,
                   catalogue_status=status,purchasing_blocked=blocked,status_reason=status.get('reason',''),
                   final_quantity=final,manual_override=overrides.get(key),
                   purchase_cost=None if final is None or not cost_known else final*float(cost),
                   turnover=None if not price_known else forecast*float(price),
                   inventory_known=not missing_inventory,cost_known=cost_known,price_known=price_known,
                   decision_required=forecast>0 or (final is not None and final>0))
        if draft:
            from buying import identity
            edit=draft_edits.get(identity(dict(reference=key[0],color=key[1],size=key[2])),{})
            prices=draft.get('resolvedInputs',{}).get(identity(dict(reference=key[0],color=key[1],size=key[2])),{})
            quantity=edit.get('quantity',prices.get('quantity',0 if blocked else math.ceil(forecast)))
            cost=prices.get('cost',edit.get('unitCost',cost));price=prices.get('price',edit.get('unitPrice',price))
            sold=quantity*edit.get('sellThrough',100)/100 if quantity is not None else None
            from budgeting import amount
            row.update(final_quantity=quantity,manual_override=edit.get('quantity'),
                unit_purchase_cost=cost,unit_selling_price=price,expected_sold=sold,
                purchase_cost=amount(quantity,cost),turnover=amount(sold,price),cost_of_sales=amount(sold,cost),
                inventory_known=prices.get('stock') is not None and prices.get('incoming') is not None,
                cost_known=cost is not None,price_known=price is not None,
                decision_required=quantity is None or quantity>0,purchase_draft=True)
        result.append(row)
    return result

def financial_summary(conn, scenario='base', season_id=None, rows=None):
    if rows is None:rows=final_rows(conn,scenario,season_id)
    plan=active_plan(conn)
    cost=sum(r['purchase_cost'] or 0 for r in rows)
    revenue=sum(r['turnover'] or 0 for r in rows)
    complete=bool(rows) and all(not r['decision_required'] or (r['final_quantity'] is not None and r['inventory_known'] and r['cost_known'] and r['price_known'] and not (r.get('purchasing_blocked') and r['final_quantity']>0)) for r in rows)
    # Demand margin uses unit costs for all sold units, not only the newly purchased units.
    cogs=sum((r['cost_of_sales'] or 0) if 'cost_of_sales' in r else r['demand_forecast']*float(r.get('unit_purchase_cost') or 0) for r in rows)
    budget=float(plan['budget']) if plan else 0
    return dict(totalPurchaseCost=cost if complete else None,seasonBudget=budget,
                expectedTurnover=revenue if complete else None,grossMargin=revenue-cogs if complete else None,
                grossMarginPercent=(revenue-cogs)/revenue*100 if complete and revenue else None,
                financialComplete=complete,missingInputRows=sum(r['decision_required'] and not(r['inventory_known'] and r['cost_known'] and r['price_known']) for r in rows),
                budgetUsage=cost/budget*100 if complete and budget>0 else None,
                targetMargin=float(plan['targetMargin']) if plan else None,currency=plan['currency'] if plan else 'EUR')
