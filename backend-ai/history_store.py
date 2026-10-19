"""Persistent CSV baseline plus date-scoped, idempotent Joolan customer orders."""
import csv
import hashlib
import math
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zlib

import pandas as pd
from m1_data_preparation import EXPECTED_COLUMNS, _standardize_columns, parse_order_dates

DEFAULT_PATH = Path(__file__).resolve().parent / 'data' / 'history.db'


def connection(path=None):
    target = Path(path or DEFAULT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=60)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS history_rows(source TEXT NOT NULL,line_key TEXT NOT NULL,
            order_date TEXT NOT NULL,payload BLOB NOT NULL,PRIMARY KEY(source,line_key));
        CREATE INDEX IF NOT EXISTS history_dates ON history_rows(source,order_date);
        CREATE TABLE IF NOT EXISTS history_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS joolan_history_raw(line_key TEXT PRIMARY KEY,order_date TEXT NOT NULL,
            document_type TEXT NOT NULL,usable INTEGER NOT NULL,issues TEXT NOT NULL,payload BLOB NOT NULL);
        CREATE INDEX IF NOT EXISTS joolan_history_scope ON joolan_history_raw(document_type,order_date);
    ''')
    columns={row[1] for row in conn.execute('PRAGMA table_info(history_rows)')}
    if 'usable' not in columns:
        conn.execute('ALTER TABLE history_rows ADD COLUMN usable INTEGER NOT NULL DEFAULT 1')
    if 'issues' not in columns:
        conn.execute("ALTER TABLE history_rows ADD COLUMN issues TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
    return conn


def metadata(conn):
    return {k: json.loads(v) for k, v in conn.execute('SELECT key,value FROM history_metadata')}


def put_metadata(conn, key, value):
    conn.execute('INSERT OR REPLACE INTO history_metadata VALUES(?,?)', (key, json.dumps(value)))


def pack(row):
    return zlib.compress(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode(), 1)


def quantity_issues(row):
    issues=[]
    for column in ('CDE_qte','LIV_qte','RELIQUAT_qte','ANN_qte'):
        value=row.get(column)
        if value is None or str(value).strip()=='':
            continue
        try:
            parsed=float(value)
            if not math.isfinite(parsed) or parsed<0:
                issues.append('Invalid or negative '+column)
        except (TypeError,ValueError):
            issues.append('Invalid or negative '+column)
    return issues


def validate_stored_baseline(conn):
    if metadata(conn).get('quantityValidationVersion')==1:
        return
    with conn:
        updates=[]
        for key,payload in conn.execute("SELECT line_key,payload FROM history_rows WHERE source='legacy'"):
            issues=quantity_issues(json.loads(zlib.decompress(payload)))
            updates.append((int(not issues),json.dumps(issues),key))
            if len(updates)==2000:
                conn.executemany("UPDATE history_rows SET usable=?,issues=? WHERE source='legacy' AND line_key=?",updates)
                updates=[]
        conn.executemany("UPDATE history_rows SET usable=?,issues=? WHERE source='legacy' AND line_key=?",updates)
        put_metadata(conn,'quantityValidationVersion',1)


def build_baseline(conn, csv_path):
    path = Path(csv_path)
    stat = path.stat()
    signature = [str(path.resolve()), stat.st_size, stat.st_mtime_ns]
    if metadata(conn).get('csvSignature') == signature:
        validate_stored_baseline(conn)
        return
    for encoding in ('utf-8', 'cp1252', 'latin-1'):
        try:
            header = pd.read_csv(path, nrows=0, encoding=encoding)
            normalized = _standardize_columns(header.copy())
            mapping = dict(zip(header.columns, normalized.columns))
            rows = 0
            cutoff = None
            with conn:
                conn.execute("DELETE FROM history_rows WHERE source='legacy'")
                with pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding, chunksize=25000) as chunks:
                    for chunk in chunks:
                        chunk = chunk.rename(columns=mapping)
                        dates = parse_order_dates(chunk['Date_Commande'])
                        if dates.isna().any():
                            raise ValueError('Historical CSV has invalid dates; the previous history was preserved.')
                        chunk['Date_Commande'] = dates.dt.strftime('%Y-%m-%d')
                        cutoff = max(cutoff or '', chunk.Date_Commande.max())
                        records = []
                        for row in chunk.to_dict('records'):
                            rows += 1
                            key = f'csv:{rows}'
                            row.update(Data_Source='legacy', Source_Line_Key=key)
                            issues=quantity_issues(row)
                            records.append(('legacy', key, row['Date_Commande'], pack(row),int(not issues),json.dumps(issues)))
                        conn.executemany('INSERT INTO history_rows VALUES(?,?,?,?,?,?)', records)
                if not rows:
                    raise ValueError('Historical CSV is empty.')
                current = path.stat()
                if [str(path.resolve()), current.st_size, current.st_mtime_ns] != signature:
                    raise ValueError('The CSV changed during import; retry with a stable file.')
                put_metadata(conn, 'csvSignature', signature)
                put_metadata(conn, 'csvCutoff', cutoff)
                put_metadata(conn, 'csvColumns', list(normalized.columns))
                put_metadata(conn, 'baseImportedAt', dt.datetime.now(dt.timezone.utc).isoformat())
                put_metadata(conn, 'quantityValidationVersion', 1)
            return
        except UnicodeDecodeError:
            continue
    raise ValueError('Cannot decode the historical CSV.')


def joolan_record(row, key):
    record = {column: '' for column in EXPECTED_COLUMNS}
    for column in EXPECTED_COLUMNS:
        if column.endswith(('_qte', '_ht')) or column in ('Prix', 'STOCK'):
            record[column] = 0
    record.update(Client=row['Customer'], Nom=row['Customer'], Reference=row['Product'],
                  Reference_CDE=row['Order_Number'], Piece=row['Order_Number'],
                  Date_Commande=row['Order_Date'], Couleur=row['Colour'], Taille=row['Size'],
                  Magasin=row['Store'], CDE_qte=row['Ordered_Quantity'], LIV_qte=row['Delivered_Quantity'],
                  ANN_qte=row.get('Cancelled_Quantity') or 0,
                  RELIQUAT_qte=row['Ordered_Quantity']-row['Delivered_Quantity']-(row.get('Cancelled_Quantity') or 0),
                  Critere='Joolan('+row['Order_Date'][:4]+')', Data_Source='joolan',
                  Cancellations_Known=row.get('Cancelled_Quantity') is not None,
                  Source_Line_Key='joolan:'+key, STOCK=None, CDE_four_qte=None, Prix=None)
    return record


def scope_end(snapshot):
    explicit = snapshot.get('scope', {}).get('endDate')
    if explicit:
        return explicit
    if snapshot.get('origin') == 'query-api' and snapshot.get('importedAt'):
        return dt.datetime.fromisoformat(snapshot['importedAt']).date().isoformat()
    return '9999-12-31'


def merge_snapshot(conn, source):
    state = dict(source.execute('SELECT key,value FROM joolan_state'))
    order_type = state.get('customer_order_type', '')
    snapshot = json.loads(state.get('snapshot', '{}'))
    preserve_raw_snapshot(conn, source, snapshot)
    if not order_type:
        return False
    scope = snapshot.get('scope', {})
    if scope.get('documentType') and scope['documentType'] != order_type:
        raise ValueError('Sync the confirmed customer-order type before combining history.')
    meta = metadata(conn)
    if meta.get('orderType') not in (None, order_type):
        raise ValueError('The confirmed order type changed. Reconcile the existing combined history before replacing its scope.')
    if meta.get('enseigne') and scope.get('enseigne') and meta['enseigne'] != scope['enseigne']:
        raise ValueError('Cannot combine two Joolan enseignes in one company history.')
    cutoff = meta['csvCutoff']
    if meta.get('snapshotImportedAt') == snapshot.get('importedAt') and meta.get('forecastCsvCutoff') == cutoff:
        return True
    start = max(scope.get('startDate') or '', (dt.date.fromisoformat(cutoff)+dt.timedelta(days=1)).isoformat())
    end = scope_end(snapshot)
    if end < start:
        return True
    with conn:
        conn.execute("DELETE FROM history_rows WHERE source='joolan' AND order_date BETWEEN ? AND ?", (start, end))
        buffer = []
        last = ''
        query = """SELECT row_key,payload FROM joolan_order_lines WHERE usable=1
            AND json_extract(payload,'$.Document_Type')=?
            AND json_extract(payload,'$.Order_Date') BETWEEN ? AND ? ORDER BY position"""
        for key, payload in source.execute(query, (order_type, start, end)):
            row = joolan_record(json.loads(payload), key)
            last = max(last, row['Date_Commande'])
            buffer.append(('joolan', key, row['Date_Commande'], pack(row),1,'[]'))
            if len(buffer) == 2000:
                conn.executemany('INSERT OR REPLACE INTO history_rows VALUES(?,?,?,?,?,?)', buffer)
                buffer = []
        conn.executemany('INSERT OR REPLACE INTO history_rows VALUES(?,?,?,?,?,?)', buffer)
        put_metadata(conn, 'orderType', order_type)
        if scope.get('enseigne'):
            put_metadata(conn, 'enseigne', scope['enseigne'])
        put_metadata(conn, 'snapshotImportedAt', snapshot.get('importedAt'))
        put_metadata(conn, 'forecastCsvCutoff', cutoff)
        coverage = meta.get('coverage', [])
        covered_end = end if end != '9999-12-31' else last
        if covered_end and covered_end >= start:
            coverage.append([start, covered_end])
        coverage = [list(pair) for pair in sorted(set(tuple(pair) for pair in coverage))]
        put_metadata(conn, 'coverage', coverage)
        put_metadata(conn, 'updatedAt', dt.datetime.now(dt.timezone.utc).isoformat())
    return True


def preserve_raw_snapshot(conn, source, snapshot):
    if not snapshot:
        return
    meta = metadata(conn)
    if meta.get('rawSnapshotImportedAt') == snapshot.get('importedAt') and meta.get('rawCsvCutoff') == meta['csvCutoff']:
        return
    scope = snapshot.get('scope', {})
    if meta.get('enseigne') and scope.get('enseigne') and meta['enseigne'] != scope['enseigne']:
        raise ValueError('Cannot combine two Joolan enseignes in one company history.')
    start = max(scope.get('startDate') or '', (dt.date.fromisoformat(meta['csvCutoff'])+dt.timedelta(days=1)).isoformat())
    end = scope_end(snapshot)
    kind = scope.get('documentType', '')
    with conn:
        delete = 'DELETE FROM joolan_history_raw WHERE order_date BETWEEN ? AND ?'
        params = (start, end)
        if kind:
            delete += ' AND document_type=?'
            params += (kind,)
        conn.execute(delete, params)
        query = """SELECT row_key,payload,usable,issues FROM joolan_order_lines
            WHERE json_extract(payload,'$.Order_Date') BETWEEN ? AND ?"""
        if kind:
            query += " AND json_extract(payload,'$.Document_Type')=?"
        buffer = []
        for key, payload, usable, issues in source.execute(query, params):
            row = json.loads(payload)
            buffer.append((key, row['Order_Date'], row['Document_Type'], usable, issues, pack(row)))
            if len(buffer) == 2000:
                conn.executemany('INSERT OR REPLACE INTO joolan_history_raw VALUES(?,?,?,?,?,?)', buffer)
                buffer = []
        conn.executemany('INSERT OR REPLACE INTO joolan_history_raw VALUES(?,?,?,?,?,?)', buffer)
        put_metadata(conn, 'rawSnapshotImportedAt', snapshot.get('importedAt'))
        put_metadata(conn, 'rawCsvCutoff', meta['csvCutoff'])
        if scope.get('enseigne'):
            put_metadata(conn, 'enseigne', scope['enseigne'])


def summary(conn):
    meta = metadata(conn)
    cutoff = meta.get('csvCutoff', '')
    counts = dict(conn.execute("SELECT source,COUNT(*) FROM history_rows WHERE source='legacy' OR order_date>? GROUP BY source", (cutoff,)))
    dates = conn.execute("SELECT MIN(order_date),MAX(order_date) FROM history_rows WHERE source='legacy' OR order_date>?", (cutoff,)).fetchone()
    raw_rows = conn.execute('SELECT COUNT(*),SUM(usable=0) FROM joolan_history_raw WHERE order_date>?', (cutoff,)).fetchone()
    legacy_bad=conn.execute("SELECT COUNT(*) FROM history_rows WHERE source='legacy' AND usable=0").fetchone()[0]
    covered = cutoff
    gaps = []
    for start, end in sorted(meta.get('coverage', [])):
        next_day = (dt.date.fromisoformat(covered)+dt.timedelta(days=1)).isoformat() if covered else start
        if start > next_day:
            gaps.append(dict(start=next_day, end=(dt.date.fromisoformat(start)-dt.timedelta(days=1)).isoformat()))
        covered = max(covered, end)
    return dict(legacyRows=counts.get('legacy', 0), joolanRows=counts.get('joolan', 0),
                totalRows=sum(counts.values()), csvCutoff=cutoff, firstDate=dates[0], lastDate=dates[1],
                coveredThrough=covered, gaps=gaps, needsOrderType=not meta.get('orderType'),
                snapshotImportedAt=meta.get('snapshotImportedAt'), orderType=meta.get('orderType'), historyRevision=revision(conn),
                rawJoolanRows=raw_rows[0],rawQuarantinedRows=raw_rows[1] or 0,storedRows=counts.get('legacy',0)+raw_rows[0],
                legacyQuarantinedRows=legacy_bad,forecastLegacyRows=counts.get('legacy',0)-legacy_bad,
                notice='CSV remains authoritative through its cutoff. Only later Joolan orders enter combined history; older order revisions require separate reconciliation. Current stock is not inferred from historical rows.')


def revision(conn):
    meta = metadata(conn)
    values = {k: meta.get(k) for k in ('csvSignature', 'snapshotImportedAt', 'orderType', 'coverage','quantityValidationVersion')}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def build(source=None, csv_path=None, db_path=None):
    if csv_path is None:
        from config import DATA_FILE_PATH
        csv_path = DATA_FILE_PATH
    conn = connection(db_path)
    try:
        build_baseline(conn, csv_path)
        if source is not None:
            owns_read = not source.in_transaction
            if owns_read:
                source.execute('BEGIN')
            try:
                merge_snapshot(conn, source)
            finally:
                if owns_read:
                    source.rollback()
        return summary(conn)
    finally:
        conn.close()


def export_pipeline(destination, source, db_path=None):
    result = build(source=source, db_path=db_path)
    if result['gaps']:
        raise ValueError('Combined history has date gaps. Import the missing periods before forecasting.')
    conn = connection(db_path)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        columns = list(dict.fromkeys(EXPECTED_COLUMNS + metadata(conn).get('csvColumns', []) +
                                    ['Data_Source', 'Source_Line_Key', 'Cancellations_Known']))
        with tempfile.NamedTemporaryFile('w', newline='', encoding='utf-8', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            for (payload,) in conn.execute("SELECT payload FROM history_rows WHERE usable=1 AND (source='legacy' OR order_date>?) ORDER BY order_date,source,line_key", (result['csvCutoff'],)):
                row = json.loads(zlib.decompress(payload))
                # Historical stock/prices are not a current operational snapshot.
                row.update(STOCK=None, CDE_four_qte=None, Prix=None, Selling_Price=None, Purchase_Cost=None)
                writer.writerow(row)
        os.replace(temporary, target)
        return str(target)
    finally:
        conn.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
