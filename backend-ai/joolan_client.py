"""Read-only Joolan Query API client and safe trade-line join, shared with the validated exporter."""
import json
import re
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from functools import lru_cache
DOCS = 'https://go.joolan.com/api/v2/swagger-ui.html'
class ExportError(Exception):
    def __init__(self, message, http_status=400):
        super().__init__(message)
        self.http_status = http_status

class SourceChangedError(ExportError):
    """A bounded read became incomplete; the whole download can be retried."""

class RateLimitError(ExportError):
    """Stop immediately; more queries cannot resolve an exhausted remote quota."""


def sql_value(value):
    if isinstance(value, str):
        # Hex avoids dependence on MySQL backslash/string escape settings.
        return "CONVERT(0x" + value.encode('utf-8').hex() + " USING utf8mb4)" if value else "''"
    if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        if isinstance(value, Decimal) and not value.is_finite():
            raise ExportError('Invalid primary-key value returned by Joolan.')
        return str(value)
    if isinstance(value, (datetime, date)):
        return sql_value(value.isoformat(sep=' ') if isinstance(value, datetime) else value.isoformat())
    raise ExportError('Unsupported primary-key type; request a stable key from Joolan.')


def key_comparison(keys, values, operator):
    columns = ', '.join(map(identifier, keys))
    literals = ', '.join(sql_value(value) for value in values)
    return f'({columns}) {operator} ({literals})' if len(keys) > 1 else f'{columns} {operator} {literals}'

def identifier(name):
    return '`' + str(name).replace('`', '``') + '`'

def validate_select(sql):
    sql = sql.strip().rstrip(';').strip()
    if not re.match(r'^SELECT\b', sql, re.I) or ';' in sql or re.search(r'\b(INTO|OUTFILE|DUMPFILE|FOR\s+UPDATE|FOR\s+SHARE|LOCK\s+IN\s+SHARE|SLEEP|BENCHMARK)\b', sql, re.I):
        raise ExportError('Use one SELECT query only; file output and locking are disabled.')
    return sql

def spool_value(value):
    """Preserve MySQL types during the temporary JSONL roundtrip."""
    if isinstance(value, Decimal):
        return {'__joolan_type__': 'decimal', 'value': str(value)}
    if isinstance(value, (datetime, date, time)):
        return {'__joolan_type__': type(value).__name__, 'value': value.isoformat()}
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return 'hex:' + bytes(value).hex()
    raise TypeError('Unsupported database value type: ' + type(value).__name__)

def unspool_value(value):
    if set(value) == {'__joolan_type__', 'value'}:
        kind, text = value['__joolan_type__'], value['value']
        if kind == 'decimal':
            return Decimal(text)
        if kind == 'datetime':
            return datetime.fromisoformat(text)
        if kind == 'date':
            return date.fromisoformat(text)
        if kind == 'time':
            return time.fromisoformat(text)
    return value

class Client:
    snapshot_note = 'Tables are read separately. Concurrent edits can affect results even when counts match.'
    table_verification = 'Count verified; not a transactional snapshot'
    documentation = DOCS
    def __init__(self, domain, enseigne, key, cancelled=None):
        parsed = urllib.parse.urlsplit(domain if '://' in domain else 'https://' + domain)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ExportError('Enter an HTTPS Joolan domain, without credentials or query parameters.')
        self.url = 'https://' + parsed.netloc + '/api/v2/query.do'
        self.enseigne, self.key = enseigne.strip(), key.strip()
        self.cancelled = cancelled or threading.Event()
        if not self.enseigne or not self.key:
            raise ExportError('Enter both enseigne and API key.')

    def query(self, sql):
        if self.cancelled.is_set():
            raise ExportError('Cancelled. No final workbook was published.')
        sql = validate_select(sql)
        params = urllib.parse.urlencode({'enseigne': self.enseigne, 'api-key': self.key})
        request = urllib.request.Request(self.url + '?' + params, data=sql.encode('utf-8'),
                                         headers={'Content-Type': 'text/plain; charset=utf-8', 'Accept': 'application/json'}, method='POST')
        # Prevent redirects from forwarding credentials to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise RateLimitError('Joolan query quota reached. Wait for Joolan to reset its quota, then retry sync; completed download pages will resume when available.', 429) from None
            raise ExportError(f'Joolan returned HTTP {error.code}. Check domain, key, Queries permission, expiry and IP restrictions.') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ExportError('Connection failed or timed out. Check internet access and the Joolan domain.') from None
        except (ValueError, UnicodeError):
            raise ExportError('Joolan did not return valid JSON. Check the domain and account configuration.') from None
        if not isinstance(payload, dict) or payload.get('result') != 'ok':
            reason = str(payload.get('error_message', 'Unexpected response')) if isinstance(payload, dict) else 'Unexpected response'
            reason = reason.replace(self.key, '[hidden]')
            if re.search(r'hourly limit|rate.?limit|quota|too many requests', reason, re.I):
                raise RateLimitError('Joolan hourly query limit reached. Wait for Joolan to reset its quota, then retry sync; completed download pages will resume when available.', 429)
            raise ExportError('Joolan rejected the query: ' + reason[:500])
        rows = payload.get('data')
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ExportError('Expected data to be an array of records; no workbook was published.')
        return rows

    def close(self):
        pass

    def count(self, table, where=''):
        rows = self.query(f'SELECT COUNT(*) AS export_count FROM {identifier(table)}' + (f' WHERE {where}' if where else ''))
        if len(rows) != 1 or 'export_count' not in rows[0]:
            raise ExportError('Could not verify the table row count.')
        return int(rows[0]['export_count'])

    def table_snapshot(self, table, log, document_type='', start_date='', end_date='', extra_where=''):
        scope = f'{identifier("Nature")} = {sql_value(document_type)}' if document_type else ''
        date_parts = []
        if start_date:
            date_parts.append(f'`Date` >= {sql_value(date.fromisoformat(start_date).isoformat())}')
        if end_date:
            end = date.fromisoformat(end_date) + timedelta(days=1)
            date_parts.append(f'`Date` < {sql_value(end.isoformat())}')
        if date_parts:
            dated = ' AND '.join(date_parts)
            if table == 'negoce_lignes':
                # Lines have no order date. Filter by their compatible header,
                # matching the same identity rules used by the local join.
                dated = re.sub(r'`Date`', 'h.`Date`', dated)
                header_scope = f' AND h.`Nature` = {sql_value(document_type)}' if document_type else ''
                dated = (f'EXISTS (SELECT 1 FROM `negoce_entetes` h WHERE h.`Entete` = `negoce_lignes`.`Entete` '
                         'AND (h.`Magasin` = `negoce_lignes`.`Magasin` OR h.`Magasin` IS NULL OR `negoce_lignes`.`Magasin` IS NULL) '
                         'AND (h.`Client` = `negoce_lignes`.`Client` OR h.`Client` IS NULL OR `negoce_lignes`.`Client` IS NULL) '
                         f'AND {dated}{header_scope})')
            scope = f'({scope}) AND ({dated})' if scope else dated
        if extra_where:scope=f'({scope}) AND ({extra_where})' if scope else extra_where
        predicate = f' WHERE {scope}' if scope else ''
        probe = self.query(f'SELECT * FROM {identifier(table)}{predicate} LIMIT 1')
        columns = list(probe[0]) if probe else []
        # Prefer the actual primary key, never assume the provided SKU join is unique.
        try:
            keys = self.query("SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                              f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = {sql_value(table)} "
                              "AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION")
            order = [field(r, 'COLUMN_NAME') for r in keys]
        except RateLimitError:
            raise
        except ExportError:
            order = []
        primary = order if order and all(key in columns for key in order) else []
        if primary:
            descending = ', '.join(identifier(key) + ' DESC' for key in primary)
            upper = self.query(f'SELECT * FROM {identifier(table)}{predicate} ORDER BY {descending} LIMIT 1')
            if not upper:
                raise SourceChangedError(f'{table}: rows disappeared while capturing the export boundary.')
            bound = [upper[0][key] for key in primary]
            where = key_comparison(primary, bound, '<=')
            if scope:
                where = f'({scope}) AND {where}'
            return dict(expected=self.count(table, where), columns=columns, order=primary,
                        primary=primary, upper=bound, where=where, paging='keyset')
        if not order:
            order = columns
            log(f'{table}: primary key unavailable; ordering by all returned columns.')
        dates = [column for column in columns if column.lower() in ('date', 'date_commande', 'date_reception', 'date_creation')]
        order = dates + [column for column in order if column not in dates]
        expected = self.count(table, scope)
        if expected and not columns:
            raise ExportError(f'{table}: count is nonzero but no records were returned.')
        return dict(expected=expected, columns=columns, order=order, primary=[], where=scope, paging='offset')

    def table_rows(self, table, batch, log, metadata, checkpoint=None):
        if not metadata:
            metadata.update(self.table_snapshot(table, log))
        expected = metadata['expected']
        order = metadata['order']
        primary = metadata['primary']
        last = metadata.get('cursor')
        offset = metadata.get('exported', 0)
        ordering = ' ORDER BY ' + ', '.join(map(identifier, order)) if order else ''
        while offset < expected:
            where = metadata['where']
            if last is not None:
                where += ' AND ' + key_comparison(primary, last, '>')
            predicate = f' WHERE {where}' if where else ''
            paging = '' if primary else f' OFFSET {offset}'
            projection=', '.join(map(identifier,metadata['projection'])) if metadata.get('projection') else '*'
            rows = self.query(f'SELECT {projection} FROM {identifier(table)}{predicate}{ordering} LIMIT {min(batch, expected-offset)}{paging}')
            if not rows:
                raise SourceChangedError(f'{table}: stopped at {offset:,} of {expected:,} bounded rows. Export incomplete.')
            if len(rows) > min(batch, expected-offset):
                raise ExportError(f'{table}: server ignored the requested LIMIT.')
            offset += len(rows)
            if primary:
                cursor = [rows[-1].get(key) for key in primary]
                if any(value is None for value in cursor) or cursor == last:
                    raise ExportError(f'{table}: server did not return an advancing primary-key cursor.')
                last = cursor
            log(f'{table}: fetched {offset:,} / {expected:,} rows')
            yield from rows
            metadata['exported'] = offset
            metadata['cursor'] = last
            if checkpoint:
                checkpoint()
        after = self.count(table, metadata['where'])
        if after != expected:
            raise SourceChangedError(f'{table}: bounded row count changed during export ({expected:,} to {after:,}).')
        if primary and expected and last != metadata['upper']:
            raise SourceChangedError(f'{table}: export did not reach the captured primary-key boundary.')
        metadata['exported'] = offset

@lru_cache(maxsize=4096)
def _field_key(columns, name):
    # Export rows share schemas. Resolve each column once, retaining the original
    # first-match rule even when a source has two differently cased column names.
    folded = name.casefold()
    return next((key for key in columns if key.casefold() == folded), None)

def field(row, name):
    key = _field_key(tuple(row), name)
    return row[key] if key is not None else None

def order_date(value):
    if value is None or value == '':
        return None, 'Missing date', ''
    if isinstance(value, (datetime, date)):
        return value, 'Date available', value.isoformat()
    text = str(value).strip()
    try:
        result = datetime.fromisoformat(text)
        # API date strings are local dates; preserve a timezone-bearing string as text.
        if result.tzinfo is None:
            return result, 'Date available', result.isoformat()
    except ValueError:
        pass
    for pattern in ('%d/%m/%Y', '%Y%m%d'):
        try:
            result = datetime.strptime(text, pattern)
            return result, 'Date available', result.isoformat()
        except ValueError:
            pass
    return text, 'Unrecognized date format', ''

def trade_document_spool(spools, scratch, cancelled, log, nature_filter=''):
    import sqlite3
    from contextlib import closing
    columns = ['Order_Number', 'Customer', 'Order_Date', 'Product', 'Ordered_Quantity',
               'Delivered_Quantity', 'Store', 'Colour', 'Size', 'Document_Type', 'Link_Status', 'Date_Status']
    output = Path(scratch) / 'trade_documents.jsonl'
    stats = dict(rows=0, headers=0, unmatched_lines=0, missing_items=0, missing_dates=0)
    wanted = nature_filter.strip().upper()
    with closing(sqlite3.connect(str(Path(scratch) / 'trade_join.sqlite'))) as db:
        db.execute('CREATE TABLE headers(seq INTEGER PRIMARY KEY, id TEXT, store TEXT, customer TEXT, nature TEXT, date_sort TEXT, payload TEXT)')
        db.execute('CREATE TABLE items(seq INTEGER PRIMARY KEY, id TEXT, store TEXT, customer TEXT, header_seq INTEGER, payload TEXT)')
        for table in ('negoce_entetes', 'negoce_lignes'):
            with spools[table].open(encoding='utf-8') as stream:
                for text in stream:
                    if cancelled.is_set():
                        raise ExportError('Cancelled. No final workbook was published.')
                    row = json.loads(text, object_hook=unspool_value)
                    keys = tuple(str(field(row, key)) if field(row, key) is not None else None
                                 for key in ('entete', 'magasin', 'client'))
                    if table == 'negoce_entetes':
                        db.execute('INSERT INTO headers(id,store,customer,nature,date_sort,payload) VALUES(?,?,?,?,?,?)',
                                   keys + (str(field(row, 'nature') or '').strip().upper(), order_date(field(row, 'date'))[2], text))
                    else:
                        db.execute('INSERT INTO items(id,store,customer,payload) VALUES(?,?,?,?)', keys + (text,))
        db.execute('CREATE INDEX trade_header_id ON headers(id,store,customer)')
        # Require exactly one compatible header. Never multiply a line across reused IDs.
        db.execute("""UPDATE items SET header_seq=(SELECT CASE WHEN COUNT(*)=1 THEN MAX(seq) END
                      FROM headers WHERE headers.id=items.id
                      AND (items.store IS NULL OR headers.store IS NULL OR headers.store=items.store)
                      AND (items.customer IS NULL OR headers.customer IS NULL OR headers.customer=items.customer))""")
        db.execute('CREATE INDEX trade_item_header ON items(header_seq)')
        stats['transaction_types'] = db.execute('SELECT nature, COUNT(*) FROM headers GROUP BY nature ORDER BY nature').fetchall()
        stats['unmatched_lines'] = db.execute('SELECT COUNT(*) FROM items WHERE header_seq IS NULL').fetchone()[0]
        stats['headers'] = db.execute("SELECT COUNT(*) FROM headers WHERE ?='' OR nature=?", (wanted,wanted)).fetchone()[0]
        query = """SELECT headers.payload, items.payload FROM headers
                   LEFT JOIN items ON items.header_seq=headers.seq
                   WHERE ?='' OR headers.nature=?
                   ORDER BY CASE WHEN date_sort='' THEN 1 ELSE 0 END,date_sort,headers.seq,items.seq"""
        with output.open('w', encoding='utf-8') as stream:
            def emit(header, item, status):
                if cancelled.is_set():
                    raise ExportError('Cancelled. No final workbook was published.')
                date_value, date_status, _ = order_date(field(header, 'date'))
                record = dict(Order_Number=field(header,'entete') if header else field(item,'entete'),
                              Customer=field(header,'client') if header else field(item,'client'),
                              Order_Date=date_value, Product=field(item,'produit'),
                              Ordered_Quantity=field(item,'quantite'), Delivered_Quantity=field(item,'quantite_livree'),
                              Cancelled_Quantity=field(item,'quantite_annulee'),Line_Number=field(item,'ligne'),
                              Store=field(header,'magasin') if header else field(item,'magasin'),
                              Colour=field(item,'couleur'), Size=field(item,'taille'),
                              Document_Type=field(header,'nature'), Link_Status=status, Date_Status=date_status)
                stream.write(json.dumps(record, ensure_ascii=False, default=spool_value)+'\n')
                stats['rows'] += 1
                stats['missing_dates'] += int(date_status != 'Date available')
            for head, item in db.execute(query,(wanted,wanted)):
                header=json.loads(head,object_hook=unspool_value)
                line=json.loads(item,object_hook=unspool_value) if item else {}
                emit(header,line,'Linked item' if item else 'Header without linked item')
                stats['missing_items'] += int(not item)
            if not wanted:
                # Preserve orphan/ambiguous item quantities without inventing an order date/type.
                for (text,) in db.execute('SELECT payload FROM items WHERE header_seq IS NULL ORDER BY seq'):
                    emit({},json.loads(text,object_hook=unspool_value),'No unique compatible header')
    log(f"Trade documents: {stats['headers']:,} selected headers, {stats['rows']:,} report rows; quantities are individual line values.")
    return output, columns, stats
