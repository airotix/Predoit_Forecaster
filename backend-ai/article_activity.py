"""Display-only article recency from the published, normalized customer ledger.

Never filters model training, changes forecasts, or overrides lifecycle flags.
"""
import calendar
import datetime as dt
import json
import math
import threading

_cache = {}
_lock = threading.RLock()
CANCELLED = ('0','2','cancelled','canceled','annule','annulé','draft','unconfirmed')


def iso(value):
    try:
        return dt.date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def context(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='pipeline_metadata'").fetchone():
        return {}, None
    metadata = dict(conn.execute('SELECT key,value FROM pipeline_metadata'))
    try:
        lineage = json.loads(metadata.get('lineage', '{}'))
    except (ValueError, TypeError):
        lineage = {}
    through = iso((lineage.get('freshReport') or {}).get('exportedThrough'))
    # A month-only training cutoff ends on the final day of that month.
    if not through:
        cutoff = str(lineage.get('cutoff') or '')
        through = iso(cutoff)
        if not through and len(cutoff) == 7:
            try:
                year, month = map(int, cutoff.split('-'))
                through = dt.date(year, month, calendar.monthrange(year, month)[1]).isoformat()
            except (ValueError, TypeError):
                pass
    return metadata, through


def classify(last, through):
    if not through:
        return dict(lastCustomerOrder=last, asOf=None, dormant=False, status='unknown', label='Order activity unavailable')
    date = dt.date.fromisoformat(through)
    boundary = date.replace(year=date.year - 2, day=min(date.day, calendar.monthrange(date.year - 2, date.month)[1]))
    dormant = last is not None and last <= boundary.isoformat()
    return dict(lastCustomerOrder=last, asOf=through, dormant=dormant,
                status='dormant' if dormant else 'recent' if last else 'no_history',
                label='No orders in 2+ years — review discontinuation' if dormant else 'No order history' if not last else 'Ordered within 2 years')


def observe(dates, row, through):
    """Collect during the existing publication pass, avoiding a second ledger scan."""
    try:
        quantity = float(row.get('true_demand') or 0)
    except (ValueError, TypeError):
        return
    reference = str(row.get('Reference') or '').strip()
    date = iso(row.get('Date_Commande'))
    status = str(row.get('Order_Status') or '').lower()
    if reference and through and date and date <= through and math.isfinite(quantity) and quantity > 0 and status not in CANCELLED:
        dates[reference] = max(dates.get(reference, ''), date)


def publish_cache(conn, dates):
    metadata, through = context(conn)
    from planning import order_ledger_revision
    revision = order_ledger_revision(conn)
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    if path and revision is not None:
        from derived_cache import store
        signature = json.dumps(['article-activity-v1', metadata, revision, through], sort_keys=True)
        store(path, 'article-activity', signature, dates)
        with _lock:
            _cache.clear()
            _cache[(path,signature)] = dates


def activity(conn):
    metadata, through = context(conn)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='order_lines'").fetchone():
        return {}, through
    from planning import order_ledger_revision
    path = conn.execute('PRAGMA database_list').fetchone()[2]
    revision = order_ledger_revision(conn)
    signature = json.dumps(['article-activity-v1', metadata, revision, through], sort_keys=True)
    cache_key = (path, signature)
    with _lock:
        if path and revision is not None and cache_key in _cache:
            return _cache[cache_key], through
        from derived_cache import load, store
        result = load(path, 'article-activity', signature) if path and revision is not None else None
        if not isinstance(result, dict):
            conn.create_function('activity_iso', 1, iso, deterministic=True)
            result = dict(conn.execute('''SELECT CAST(json_extract(payload,'$.Reference') AS TEXT),
                MAX(activity_iso(json_extract(payload,'$.Date_Commande')))
                FROM order_lines
                WHERE CAST(json_extract(payload,'$.true_demand') AS REAL)>0
                  AND lower(coalesce(CAST(json_extract(payload,'$.Order_Status') AS TEXT),''))
                      NOT IN ('0','2','cancelled','canceled','annule','annulé','draft','unconfirmed')
                  AND activity_iso(json_extract(payload,'$.Date_Commande'))<=?
                GROUP BY CAST(json_extract(payload,'$.Reference') AS TEXT)''', (through or '',)))
            result.pop(None, None)
            if path and revision is not None:
                store(path, 'article-activity', signature, result)
        if path and revision is not None:
            _cache.clear()
            _cache[cache_key] = result
        return result, through


def attach(conn, rows, reference=lambda row: row['reference'], sort=True):
    dates, through = activity(conn)
    for row in rows:
        row['activity'] = classify(dates.get(reference(row)), through)
    # Python's stable sort preserves every existing order within each group.
    if sort:
        rows.sort(key=lambda row: row['activity']['dormant'])
    return rows


def catalogue_sort(conn):
    """Small per-connection temp lookup: sorting must happen before pagination."""
    dates, through = activity(conn)
    conn.execute('CREATE TEMP TABLE IF NOT EXISTS article_activity_sort(reference TEXT PRIMARY KEY,dormant INTEGER)')
    conn.execute('DELETE FROM article_activity_sort')
    conn.executemany('INSERT INTO article_activity_sort VALUES(?,?)',
                     [(ref, int(classify(last, through)['dormant'])) for ref, last in dates.items()])
    return "coalesce((SELECT dormant FROM temp.article_activity_sort a WHERE a.reference=s.reference),0)"
