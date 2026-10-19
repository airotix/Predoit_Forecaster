"""Joolan active flags with persistent, local article/SKU overrides.

An inactive article blocks all its variants. An active article does not cancel
an inactive variant. Missing source flags remain unknown, never invented zeros.
Demand, stock, historical orders and saved purchase documents are retained.
"""
import json
import uuid

import fresh_joolan as fresh


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_sku_status(
        sku TEXT PRIMARY KEY,reference TEXT,joolan_active INTEGER,source_run TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_article_status(
        reference TEXT PRIMARY KEY,joolan_active INTEGER,source_run TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_status_overrides(
        level TEXT,target TEXT,active INTEGER,reason TEXT,updated_at TEXT,
        PRIMARY KEY(level,target))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_status_history(
        id TEXT PRIMARY KEY,level TEXT,target TEXT,active INTEGER,previous_active INTEGER,
        reason TEXT,changed_at TEXT)''')
    conn.execute('CREATE INDEX IF NOT EXISTS catalogue_status_history_target ON catalogue_status_history(level,target,changed_at DESC)')
    conn.execute('''CREATE VIEW IF NOT EXISTS catalogue_effective_status AS
        SELECT sku,CASE WHEN article_active=0 OR sku_active=0 THEN 0
                        WHEN article_active=1 AND sku_active=1 THEN 1 ELSE NULL END AS active
        FROM (SELECT s.sku,coalesce(ao.active,a.joolan_active) AS article_active,
                     coalesce(vo.active,v.joolan_active) AS sku_active
              FROM catalogue_skus s
              LEFT JOIN catalogue_article_status a ON a.reference=s.reference
              LEFT JOIN catalogue_sku_status v ON v.sku=s.sku
              LEFT JOIN catalogue_status_overrides ao ON ao.level='article' AND ao.target=s.reference
              LEFT JOIN catalogue_status_overrides vo ON vo.level='sku' AND vo.target=s.sku
              WHERE s.current=1)''')


def _flag(expression):
    return f"CASE WHEN {expression} IN (0,1,'0','1') THEN CAST({expression} AS INTEGER) ELSE NULL END"


def sync_sources(conn):
    """Extract only the small flags in SQL; don't decode full SKU details per read."""
    ensure(conn)
    source = conn.execute("SELECT value FROM planning_state WHERE key='catalogue_source'").fetchone()
    marker = 'status-v1:' + (source[0] if source else '')
    previous = conn.execute("SELECT value FROM planning_state WHERE key='catalogue_status_source'").fetchone()
    if previous and previous[0] == marker:
        return
    sku_flag = _flag("coalesce(json_extract(details,'$.sku.Actif'),json_extract(details,'$.sku.actif'))")
    article_flag = _flag("coalesce(json_extract(details,'$.product.Actif'),json_extract(details,'$.product.actif'))")
    with conn:
        conn.execute(f'''INSERT OR REPLACE INTO catalogue_sku_status
            SELECT sku,reference,{sku_flag},source_run FROM catalogue_skus WHERE current=1''')
        # Conflicting copies of an article flag are unknown, rather than choosing
        # an arbitrary SKU's product record as authority for the entire article.
        conn.execute(f'''INSERT OR REPLACE INTO catalogue_article_status
            SELECT reference,CASE WHEN COUNT(DISTINCT coalesce(active,-1))=1 THEN MIN(active) ELSE NULL END,MAX(source_run)
            FROM (SELECT reference,{article_flag} AS active,source_run FROM catalogue_skus WHERE current=1)
            GROUP BY reference''')
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('catalogue_status_source',?)", (marker,))


def _boolean(value):
    return None if value is None else bool(value)


def lookup(conn, skus=None, references=None):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_sku_status'").fetchone():
        return {}
    where = ' WHERE s.current=1'
    params = []
    if skus is not None:
        if not skus:
            return {}
        where += ' AND s.sku IN (' + ','.join('?' for _ in skus) + ')'
        params = list(skus)
    if references is not None:
        if not references:
            return {}
        where += ' AND s.reference IN (' + ','.join('?' for _ in references) + ')'
        params.extend(references)
    result = {}
    for sku, reference, color, size, raw_article, raw_sku, article_override, sku_override, article_updated, sku_updated, source_run in conn.execute('''
        SELECT s.sku,s.reference,s.color,s.size,a.joolan_active,v.joolan_active,
               ao.active,vo.active,ao.updated_at,vo.updated_at,v.source_run
        FROM catalogue_skus s
        LEFT JOIN catalogue_article_status a ON a.reference=s.reference
        LEFT JOIN catalogue_sku_status v ON v.sku=s.sku
        LEFT JOIN catalogue_status_overrides ao ON ao.level='article' AND ao.target=s.reference
        LEFT JOIN catalogue_status_overrides vo ON vo.level='sku' AND vo.target=s.sku''' + where, params):
        article = raw_article if article_override is None else article_override
        variant = raw_sku if sku_override is None else sku_override
        effective = False if article == 0 or variant == 0 else True if article == 1 and variant == 1 else None
        reason = ('Inactive article (' + ('Catalogue override' if article_override is not None else 'Joolan') + ')') if article == 0 else (
            'Inactive SKU (' + ('Catalogue override' if sku_override is not None else 'Joolan') + ')') if variant == 0 else ''
        result[sku] = dict(reference=reference,color=color,size=size,articleJoolan=_boolean(raw_article),skuJoolan=_boolean(raw_sku),
            articleOverride=_boolean(article_override),skuOverride=_boolean(sku_override),articleActive=_boolean(article),
            skuActive=_boolean(variant),active=effective,purchasingBlocked=effective is False,reason=reason,
            articleUpdatedAt=article_updated,skuUpdatedAt=sku_updated,sourceRun=source_run)
    return result


def variant_map(conn, references=None):
    values = {}
    for value in lookup(conn,references=references).values():
        key = (value['reference'],value['color'],value['size'])
        # Inconsistent duplicate SKU identities never remove an inactive block.
        if key not in values or value['purchasingBlocked']:
            values[key] = value
    return values


def save(conn, updates):
    ensure(conn)
    if not isinstance(updates,list) or not 0 < len(updates) <= 1000:
        raise ValueError('Save between 1 and 1000 status changes.')
    validated = []; seen = set()
    with conn:
        if not conn.in_transaction:
            conn.execute('BEGIN IMMEDIATE')
        for update in updates:
            if not isinstance(update,dict) or set(update)-{'level','id','active','reason'}:
                raise ValueError('Unsupported status fields.')
            level = update.get('level'); target = update.get('id'); active = update.get('active')
            if level not in ('article','sku') or not isinstance(target,str) or not target or 'active' not in update or (active is not None and type(active) is not bool):
                raise ValueError('Select an article or SKU, and active, inactive or Joolan default.')
            identity = (level,target)
            if identity in seen:
                raise ValueError('Duplicate status change.')
            seen.add(identity)
            column = 'reference' if level == 'article' else 'sku'
            if not conn.execute(f'SELECT 1 FROM catalogue_skus WHERE current=1 AND {column}=?',(target,)).fetchone():
                raise ValueError('Article or SKU is not in the current catalogue.')
            reason = update.get('reason','').strip() if isinstance(update.get('reason',''),str) else None
            if reason is None or len(reason)>500:
                raise ValueError('Enter a status reason of up to 500 characters.')
            validated.append((level,target,active,reason))
        for level,target,active,reason in validated:
            before = conn.execute('SELECT active FROM catalogue_status_overrides WHERE level=? AND target=?',(level,target)).fetchone()
            now = fresh.now()
            if active is None:
                conn.execute('DELETE FROM catalogue_status_overrides WHERE level=? AND target=?',(level,target))
            else:
                conn.execute('INSERT OR REPLACE INTO catalogue_status_overrides VALUES(?,?,?,?,?)',(level,target,int(active),reason,now))
            conn.execute('INSERT INTO catalogue_status_history VALUES(?,?,?,?,?,?,?)',
                (uuid.uuid4().hex,level,target,None if active is None else int(active),before[0] if before else None,reason,now))
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('catalogue_status_updated',?)",(fresh.now(),))
    return dict(saved=len(validated),notice='Status saved locally. Inactive articles/SKUs are blocked for new purchasing. Existing drafts keep their quantities and must be reviewed. Joolan is unchanged.')


def history(conn, sku, reference):
    ensure(conn)
    return [dict(level=r[0],id=r[1],active=_boolean(r[2]),previousOverride=_boolean(r[3]),reason=r[4],changedAt=r[5])
        for r in conn.execute('''SELECT level,target,active,previous_active,reason,changed_at FROM catalogue_status_history
            WHERE (level='sku' AND target=?) OR (level='article' AND target=?) ORDER BY changed_at DESC LIMIT 20''',(sku,reference))]
