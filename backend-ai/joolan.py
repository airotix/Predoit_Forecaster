"""Joolan line-level snapshots. Import does not overwrite legacy facts or train models."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import io
import json
import math
import os
import tempfile
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from joolan_client import Client, ExportError, SourceChangedError, order_date, spool_value, trade_document_spool, unspool_value

FIELDS = ['Order_Number', 'Customer', 'Order_Date', 'Product', 'Ordered_Quantity', 'Delivered_Quantity']
EXTRA = ['Store', 'Colour', 'Size', 'Document_Type', 'Link_Status', 'Date_Status', 'Cancelled_Quantity', 'Line_Number']
NOTICE = 'Quantity-only source: prices, inventory, cancellations and product seasons are not supplied. Financial and buying recommendations need those inputs.'


def ensure_joolan_schema(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS joolan_order_lines (
            row_key TEXT PRIMARY KEY, position INTEGER NOT NULL, payload TEXT NOT NULL,
            usable INTEGER NOT NULL, issues TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS joolan_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')


def _text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _quantity(value):
    if value is None or isinstance(value, bool) or _text(value) == '':
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_trade_row(source):
    row = {name: source.get(name) for name in FIELDS + EXTRA}
    issues = []
    for name in ['Order_Number', 'Customer', 'Product', 'Store', 'Colour', 'Size', 'Document_Type', 'Link_Status','Line_Number']:
        row[name] = _text(row[name])
    for name in ['Order_Number', 'Customer', 'Product']:
        if not row[name]:
            issues.append('Missing '+name)
    date_value, status, _ = order_date(row['Order_Date'])
    row['Order_Date'] = date_value.date().isoformat() if isinstance(date_value, dt.datetime) else date_value.isoformat() if isinstance(date_value, dt.date) else _text(date_value)
    row['Date_Status'] = status
    if status != 'Date available':
        issues.append(status)
    for name in ['Ordered_Quantity', 'Delivered_Quantity']:
        original = row[name]
        quantity = _quantity(original)
        row[name] = quantity if quantity is not None else _text(original) or None
        if quantity is None:
            issues.append('Missing or invalid '+name)
    if isinstance(row['Ordered_Quantity'], float) and isinstance(row['Delivered_Quantity'], float):
        if row['Delivered_Quantity'] > row['Ordered_Quantity']:
            issues.append('Delivered quantity exceeds ordered quantity')
    cancelled=row.get('Cancelled_Quantity')
    if cancelled is not None and _text(cancelled)!='':
        row['Cancelled_Quantity']=_quantity(cancelled)
        if row['Cancelled_Quantity'] is None:issues.append('Invalid cancellation quantity')
        elif isinstance(row['Ordered_Quantity'],float) and isinstance(row['Delivered_Quantity'],float) and row['Delivered_Quantity']+row['Cancelled_Quantity']>row['Ordered_Quantity']:
            issues.append('Delivered plus cancelled quantity exceeds ordered quantity')
    else:row['Cancelled_Quantity']=None
    if row['Link_Status'] and row['Link_Status'].casefold() not in ('linked item', 'item linked'):
        issues.append(row['Link_Status'])
    return row, issues


def is_trade_workbook(raw):
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        return 'Trade documents' in wb.sheetnames
    finally:
        wb.close()


def read_trade_workbook(raw):
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        if 'Export details' in wb.sheetnames:
            detail_columns = {}
            for values in wb['Export details'].iter_rows(values_only=True):
                labels = {str(value).strip().lower(): index for index, value in enumerate(values) if value is not None}
                if 'dataset' in labels and 'status' in labels:
                    detail_columns = labels
                    continue
                if any(str(v).upper() in ('INCOMPLETE', 'INCOMPLETE SOURCES') for v in values if v is not None):
                    source = str(values[detail_columns.get('dataset', 0)] or 'source')
                    counts = ''
                    if 'exported rows' in detail_columns and 'expected rows' in detail_columns:
                        exported = values[detail_columns['exported rows']]
                        expected = values[detail_columns['expected rows']]
                        if isinstance(exported, (int, float)) and isinstance(expected, (int, float)):
                            counts = f' ({int(exported):,} of {int(expected):,} rows)'
                    raise ValueError(f'This export has incomplete sources: {source}{counts}. The previous snapshot was preserved. Complete the Joolan download before importing; saving the workbook in the data folder does not restore missing rows.')
        names = [n for n in wb.sheetnames if n == 'Trade documents' or (n.startswith('Trade documents_') and n[len('Trade documents_'):].isdigit())]
        names.sort(key=lambda n: 1 if n == 'Trade documents' else int(n.rsplit('_',1)[1]))
        if not names:
            raise ValueError('Workbook must contain the Trade documents sheet from the Joolan exporter.')
        for name in names:
            iterator = wb[name].iter_rows(values_only=True)
            headers = [str(v).strip() if v is not None else '' for v in next(iterator, [])]
            missing = set(FIELDS) - set(headers)
            if missing:
                raise ValueError('Missing trade columns: '+', '.join(sorted(missing)))
            for values in iterator:
                if any(v is not None for v in values):
                    yield dict(zip(headers, values))
    finally:
        wb.close()


def replace_snapshot(conn, sources, origin, scope=None):
    ensure_joolan_schema(conn)
    conn.execute('DROP TABLE IF EXISTS temp.joolan_snapshot_stage')
    conn.execute('CREATE TEMP TABLE joolan_snapshot_stage(row_key TEXT PRIMARY KEY,position INTEGER,payload TEXT,usable INTEGER,issues TEXT)')
    occurrences=collections.Counter();batch=[]
    added=updated=skipped=usable=total=0
    try:
        for position,source in enumerate(sources):
            row,issues=normalize_trade_row(source)
            identity=tuple(row[k] for k in ('Order_Number','Customer','Store','Product','Colour','Size','Document_Type','Line_Number'))
            occurrences[identity]+=1
            key=hashlib.sha256(json.dumps((identity,occurrences[identity]),ensure_ascii=False).encode()).hexdigest()
            payload=json.dumps(row,ensure_ascii=False,sort_keys=True)
            existing=conn.execute('SELECT payload FROM joolan_order_lines WHERE row_key=?',(key,)).fetchone()
            added+=int(existing is None);updated+=int(existing is not None and existing[0]!=payload)
            skipped+=int(existing is not None and existing[0]==payload);usable+=int(not issues);total+=1
            batch.append((key,position,payload,int(not issues),json.dumps(issues)))
            if len(batch)>=1000:
                conn.executemany('INSERT INTO joolan_snapshot_stage VALUES(?,?,?,?,?)',batch);batch=[]
        if batch:conn.executemany('INSERT INTO joolan_snapshot_stage VALUES(?,?,?,?,?)',batch)
        if not total or not usable:raise ValueError('No usable dated order lines found. The previous Joolan snapshot was preserved.')
        removed=conn.execute('SELECT COUNT(*) FROM joolan_order_lines old WHERE NOT EXISTS(SELECT 1 FROM joolan_snapshot_stage new WHERE new.row_key=old.row_key)').fetchone()[0]
        summary=dict(totalRows=total,usableRows=usable,quarantinedRows=total-usable,rowsAdded=added,rowsUpdated=updated,rowsSkipped=skipped,rowsRemoved=removed,
            importedAt=dt.datetime.now(dt.timezone.utc).isoformat(),origin=origin,notice=NOTICE)
        if scope:
            summary['scope'] = scope
        with conn:
            conn.execute('DELETE FROM joolan_order_lines')
            conn.execute('INSERT INTO joolan_order_lines SELECT * FROM joolan_snapshot_stage')
            conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('snapshot',?)",(json.dumps(summary),))
        return snapshot_summary(conn)
    except Exception:
        conn.rollback();raise
    finally:conn.execute('DROP TABLE IF EXISTS temp.joolan_snapshot_stage')


def snapshot_summary(conn):
    ensure_joolan_schema(conn)
    state=dict(conn.execute('SELECT key,value FROM joolan_state'))
    result=json.loads(state.get('snapshot','{}'))
    result.setdefault('totalRows',0)
    result.setdefault('usableRows',0)
    result.setdefault('quarantinedRows',0)
    result['forecastSource']=state.get('forecast_source','legacy')
    result['customerOrderType']=state.get('customer_order_type','')
    result['notice']=NOTICE
    result['documentTypes']=[{'type':r[0] or '(blank)', 'rows':r[1]} for r in conn.execute("SELECT json_extract(payload,'$.Document_Type'),COUNT(*) FROM joolan_order_lines GROUP BY json_extract(payload,'$.Document_Type')")]
    return result


def snapshot_rows(conn,offset=0,limit=25):
    ensure_joolan_schema(conn)
    result=[]
    for payload,usable,issues in conn.execute('SELECT payload,usable,issues FROM joolan_order_lines ORDER BY position LIMIT ? OFFSET ?',(limit,offset)):
        row=json.loads(payload);row['Usable']=bool(usable);row['Issues']=json.loads(issues);result.append(row)
    return result


def select_forecast_source(conn,source):
    if dict(conn.execute('SELECT key,value FROM joolan_state')).get('source_policy')=='fresh_only':
        raise ValueError('Only a validated fresh Joolan API run can be activated in Setup.')
    if source not in ('legacy','joolan','combined'):
        raise ValueError('Source must be legacy, joolan or combined.')
    if source == 'combined':
        from history_store import build
        history = build(source=conn)
        if history['needsOrderType']:
            raise ValueError('Confirm the customer-order document type before using combined history.')
        if history['gaps']:
            raise ValueError('Import the missing date ranges before using combined history.')
    if source=='joolan' and not snapshot_summary(conn)['usableRows']:
        raise ValueError('Import usable Joolan order lines first.')
    if source=='joolan' and not snapshot_summary(conn)['customerOrderType']:
        raise ValueError('Select and confirm the customer-order document type first.')
    ensure_joolan_schema(conn)
    with conn:
        conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('forecast_source',?)",(source,))
    return snapshot_summary(conn)


def pipeline_dataframe(conn):
    from m1_data_preparation import EXPECTED_COLUMNS
    ensure_joolan_schema(conn)
    rows=[]
    order_type=snapshot_summary(conn)['customerOrderType']
    if not order_type:raise ValueError('Confirm the customer-order document type before forecasting.')
    for (text,) in conn.execute("SELECT payload FROM joolan_order_lines WHERE usable=1 AND json_extract(payload,'$.Document_Type')=? ORDER BY position",(order_type,)):
        record=json.loads(text)
        row={name:'' for name in EXPECTED_COLUMNS}
        for name in EXPECTED_COLUMNS:
            if name.endswith(('_qte','_ht')) or name in ('Prix','STOCK'):
                row[name]=0
        row.update(Client=record['Customer'],Nom=record['Customer'],Reference=record['Product'],
                   Reference_CDE=record['Order_Number'],Piece=record['Order_Number'],
                   Date_Commande=record['Order_Date'],Couleur=record['Colour'],Taille=record['Size'],
                   Magasin=record['Store'],CDE_qte=record['Ordered_Quantity'],LIV_qte=record['Delivered_Quantity'],
                   RELIQUAT_qte=record['Ordered_Quantity']-record['Delivered_Quantity']-(record.get('Cancelled_Quantity') or 0),
                   Critere='Joolan('+record['Order_Date'][:4]+')',Data_Source='joolan')
        row.update(STOCK=None,CDE_four_qte=None,Prix=None)
        row.update(ANN_qte=record.get('Cancelled_Quantity') or 0,Cancellations_Known=record.get('Cancelled_Quantity') is not None)
        rows.append(row)
    if not rows:
        raise ValueError('Selected Joolan source has no usable order lines; refusing to fall back to legacy data.')
    return pd.DataFrame(rows)

def confirm_order_type(conn,order_type):
    order_type=str(order_type).strip()
    if not order_type:raise ValueError('Select the document type Joolan uses for customer orders.')
    count=conn.execute("SELECT COUNT(*) FROM joolan_order_lines WHERE usable=1 AND json_extract(payload,'$.Document_Type')=?",(order_type,)).fetchone()[0]
    if not count:raise ValueError('No usable imported lines have that document type.')
    with conn:conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('customer_order_type',?)",(order_type,))
    return snapshot_summary(conn)


def selected_pipeline_path(conn,destination):
    state=dict(conn.execute('SELECT key,value FROM joolan_state'))
    if state.get('source_policy')=='fresh_only' or state.get('forecast_source')=='fresh':
        from fresh_joolan import export_pipeline
        return export_pipeline(conn,destination)
    selected = snapshot_summary(conn)['forecastSource']
    if selected == 'combined':
        from history_store import export_pipeline
        return export_pipeline(Path(destination).with_name('.combined_pipeline.csv'), conn)
    if selected!='joolan':
        return None
    df=pipeline_dataframe(conn)
    target=Path(destination);target.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='joolan-pipeline-',suffix='.csv',dir=target.parent)
    os.close(fd)
    try:
        df.to_csv(temp,index=False,encoding='utf-8')
        os.replace(temp,target)
    finally:
        Path(temp).unlink(missing_ok=True)
    return str(target)


def fetch_trade_rows(key,enseigne='legend73',document_type='',batch=10000,checkpoint_dir=None,start_date='',end_date=''):
    from joolan_download import download_pair, reset_download
    document_type = document_type.strip().upper()
    client=Client('https://go.joolan.com',enseigne,key)
    if checkpoint_dir is not None:
        scope_parts = [enseigne, document_type]
        if start_date or end_date:
            scope_parts.extend([start_date, end_date])
        scope = hashlib.sha256(json.dumps(scope_parts).encode()).hexdigest()
        context = nullcontext(str(Path(checkpoint_dir) / scope))
    else:
        context = tempfile.TemporaryDirectory(prefix='joolan-sync-')
    try:
        with context as scratch:
            # Capture both bounds before downloading either table. New keys above
            # those bounds belong to the next sync instead of shifting pagination.
            for attempt in range(3):
                try:
                    spools = download_pair(client, scratch, batch, document_type, start_date, end_date)
                    break
                except SourceChangedError:
                    reset_download(scratch)
                    if attempt == 2:
                        raise ExportError('Joolan records kept changing during three download attempts. The previous snapshot was preserved. Retry during a quieter period or request a consistent export from Joolan.') from None
            # Join scratch databases are disposable; durable files contain only
            # download pages/checkpoints and must be reusable on the next sync.
            with tempfile.TemporaryDirectory(prefix='join-', dir=scratch) as join_dir:
                report,_,_=trade_document_spool(spools,join_dir,client.cancelled,lambda message:None,document_type)
                with report.open(encoding='utf-8') as stream:
                    for text in stream:
                        yield json.loads(text,object_hook=unspool_value)
            reset_download(scratch)
    except ExportError as error:
        raise ValueError(str(error).replace(key,'[hidden]')) from None
    finally:
        client.close()
