"""Explicit local buyer confirmation of exact saved price assumptions.

Reviewer names are user-entered labels, not authenticated identities. This
module does not grant roles, approve financial exceptions or send orders.
"""
import datetime as dt
import hashlib
import json
import uuid


def fingerprint(revision, currency, row):
    values = {k: row[k] for k in ('id', 'supplier', 'quoteId', 'orderUnitCost', 'orderUnitPrice')}
    return hashlib.sha256(json.dumps([revision, currency, values], sort_keys=True).encode()).hexdigest()


def context_key(context):
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def approvals(conn, context):
    prefix = 'price_review:' + context_key(context) + ':'
    result = {}
    for value, in conn.execute('SELECT value FROM planning_state WHERE key LIKE ? ORDER BY rowid', (prefix + '%',)):
        record = json.loads(value)
        for row in record['prices']:
            result[row['fingerprint']] = {k: record[k] for k in ('id', 'createdAt', 'reviewer', 'reason', 'draftVersion')}
    return result


def record(conn, context, simulation, body):
    draft = simulation['draft']
    if (not draft['version'] or draft['stale'] or type(body.get('version')) is not int or
        body['version'] != draft['version'] or body.get('forecastRun') != draft['forecastRun'] or
        body.get('revision') != simulation['revision']):
        raise ValueError('Draft changed. Save and reload its latest version before confirming prices.')
    reviewer, reason = body.get('reviewer'), body.get('reason')
    if not isinstance(reviewer, str) or not 1 <= len(reviewer.strip()) <= 120:
        raise ValueError('Enter the reviewer name (up to 120 characters).')
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError('Record why these prices and this supplier are accepted (up to 1000 characters).')
    selected = body.get('selected')
    if (not isinstance(selected, list) or not selected or len(selected) > 10000 or
        any(not isinstance(k, str) for k in selected) or len(set(selected)) != len(selected)):
        raise ValueError('Select the saved draft lines whose prices you reviewed.')
    rows = {r['id']: r for r in simulation['rows']}
    prices = []
    for ident in selected:
        row = rows.get(ident)
        if not row or not row['quantity'] or not row['supplier'] or row['orderUnitCost'] is None or row['orderUnitPrice'] is None:
            raise ValueError('Each reviewed line needs a positive quantity, a selected supplier, purchase cost and selling price.')
        prices.append(dict(fingerprint=row['priceReviewFingerprint'],
                           **{k: row[k] for k in ('id', 'supplier', 'quoteId', 'orderUnitCost', 'orderUnitPrice', 'costBasis', 'priceBasis')}))
    saved = dict(id=uuid.uuid4().hex, createdAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                 reviewer=reviewer.strip(), reason=reason.strip(), identityBasis='User-entered local reviewer label; not verified sign-in',
                 draftVersion=draft['version'], revision=simulation['revision'], currency=simulation['currency'],
                 context=context, prices=prices)
    conn.execute('INSERT INTO planning_state VALUES(?,?)',
                 ('price_review:' + context_key(context) + ':' + saved['id'], json.dumps(saved)))
    return saved
