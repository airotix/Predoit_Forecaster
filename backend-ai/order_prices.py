"""Latest usable Joolan order prices, independent of demand and stock quantities.

Prices are native-currency net unit amounts, excluding VAT. Automatic values
never overwrite manual catalogue edits. Missing/ambiguous evidence stays null.
"""
import datetime as dt
import hashlib
import json
import threading
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

import budgeting as b
import fresh_joolan as f

VERSION = 'latest-orders-v2-reconciled'
_lock = threading.RLock()


def ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS catalogue_order_prices(
        sku TEXT,currency TEXT,side TEXT,price REAL,payload TEXT,
        PRIMARY KEY(sku,currency,side))''')


def date(value):
    try:
        return dt.date.fromisoformat(b.text(value)[:10]).isoformat()
    except ValueError:
        return None


def select_latest(options):
    """Do not infer transaction sequence from arbitrary numeric document IDs."""
    if not options:
        return None, 'No valid matching order price'
    newest = max(p['orderDate'] for p in options)
    latest = [p for p in options if p['orderDate'] == newest]
    if len({(round(p['price'], 8), p.get('supplier', '')) for p in latest}) != 1:
        return None, 'Conflicting prices on latest order date'
    chosen = dict(sorted(latest, key=lambda p: (p['orderId'], p.get('lineId', '')))[-1])
    chosen.update(matchLevel='Exact colour and size', method='Latest valid dated order; net of recorded discounts, excluding VAT. Historical transaction price, not a new quote.')
    return chosen, None


def add_latest(groups, key, evidence):
    current = groups.get(key)
    if not current or evidence['orderDate'] > current[0]['orderDate']:
        groups[key] = [evidence]
    elif evidence['orderDate'] == current[0]['orderDate']:
        current.append(evidence)


def resolve(groups, variants, currencies):
    exact = {key: select_latest(options) for key, options in groups.items()}
    colours = defaultdict(list)
    articles = defaultdict(list)
    for (variant, currency), (price, reason) in exact.items():
        colours[(variant[:2], currency)].append((price, reason))
        articles[(variant[0], currency)].append((price, reason))
    result = {}
    for variant in variants:
        for currency in currencies:
            selected, reason = exact.get((variant, currency), (None, 'No valid matching order price'))
            # A conflicting exact price must never be hidden by a broader match.
            if (variant, currency) not in exact:
                for level, options in [('Same article and colour', colours.get((variant[:2], currency), [])),
                                       ('Same article', articles.get((variant[0], currency), []))]:
                    if not options or any(p is None for p, _ in options):
                        continue
                    prices = [p for p, _ in options]
                    if len({(round(p['price'], 8), p.get('supplier', '')) for p in prices}) != 1:
                        continue
                    selected = dict(max(prices, key=lambda p: (p['orderDate'], p['orderId'])), matchLevel=level + ' · matching prices agree')
                    reason = None
                    break
            result[(variant, currency)] = (selected, reason)
    return result


def collect(source, rid, variants, config, cutoff, complete, fx_policy=None, target_currency=None, diagnostics=None):
    currencies = b._currency_map({'currencies': list(f.rows(source, rid, 'devises'))})
    iso_codes = sorted(set(currencies.values()) & set(b.SUPPORTED_CURRENCIES))
    products = {b.text(f.field(p, 'Produit')): p for p in f.rows(source, rid, 'produits')}
    supplier_groups = defaultdict(list)
    customer_groups = defaultdict(list)
    excluded = Counter()
    diagnostics=diagnostics if diagnostics is not None else {}
    diagnostics.update(reasons=defaultdict(Counter),alternatives={},seen=Counter(),references=Counter())
    diagnostics['sourceState']='ready' if complete('commandes','commandes_produits','devises') and config['poCostsVerified'] else 'UNVERIFIED_COST_BASIS' if not config['poCostsVerified'] else 'INCOMPLETE_SOURCE'
    if complete('commandes', 'commandes_produits', 'devises') and config['poCostsVerified']:
        headers = {b.text(f.field(h, 'Commande')): h for h in f.rows(source, rid, 'commandes')}
        for line in f.rows(source, rid, 'commandes_produits'):
            variant = b.key(line)
            if variant[0] not in variants:
                continue
            diagnostics['seen'][variant]+=1;diagnostics['references'][variant[0]]+=1
            order = b.text(f.field(line, 'Commande'))
            header = headers.get(order, {})
            order_date = date(f.field(header, 'Date'))
            supplier = b.text(f.field(header, 'Fournisseur'))
            preferred = b.text(f.field(products.get(variant[0], {}), 'Fournisseur'))
            currency = currencies.get(b.text(f.field(header, 'Devise')))
            if b.status(f.field(header, 'Statut')) not in ('open', 'closed') or (b.text(f.field(line, 'Statut')) and b.status(f.field(line, 'Statut')) not in ('open', 'closed')):
                diagnostics['reasons'][variant]['UNCONFIRMED_OR_CANCELLED']+=1
                excluded['supplier_status'] += 1; continue
            if not order_date or order_date > cutoff:
                diagnostics['reasons'][variant]['INVALID_OR_FUTURE_DATE']+=1
                excluded['supplier_date'] += 1; continue
            if not supplier:
                diagnostics['reasons'][variant]['SUPPLIER_MISSING']+=1
                excluded['supplier_mismatch'] += 1; continue
            if currency not in iso_codes:
                diagnostics['reasons'][variant]['CURRENCY_UNMAPPED']+=1
                excluded['supplier_currency'] += 1; continue
            price = b.net_price(f.field(line, 'Prix_Achat_Devise'), f.field(line, 'Remise_Achat'), *(f.field(header, 'Remise' + str(i)) for i in range(1, 6)))
            if price is None or price <= 0:
                diagnostics['reasons'][variant]['ZERO_OR_INVALID_PRICE']+=1
                excluded['supplier_invalid_price'] += 1; continue
            evidence=dict(price=price, unitCost=price, currency=currency, supplier=supplier,
                orderId=order, orderNumber=b.text(f.field(header, 'Numero_Commande')), orderDate=order_date,
                lineId=b.text(f.field(line, 'Ligne')), source='Joolan supplier order', matchedVariant=list(variant),
                recordedRate=b.numeric(f.field(header,'Taux_Devise')),nativeCurrencyCode=b.text(f.field(header,'Devise')))
            add_latest(diagnostics['alternatives'],(variant,currency,supplier),evidence)
            from supplier_fx import convert
            fx=convert(price,currency,target_currency,f.field(header,'Taux_Devise'),fx_policy) if target_currency and currency!=target_currency else None
            if preferred and supplier!=preferred:
                diagnostics['reasons'][variant]['SUPPLIER_CHANGED']+=1
                excluded['supplier_mismatch']+=1;continue
            add_latest(supplier_groups,(variant,currency),evidence)
            if fx:
                add_latest(supplier_groups,(variant,target_currency),dict(evidence,price=fx['unitCost'],unitCost=fx['unitCost'],currency=target_currency,fx=fx))
            elif target_currency and currency!=target_currency:
                diagnostics['reasons'][variant]['FX_UNAVAILABLE']+=1
    else:
        excluded['supplier_sources_incomplete_or_unverified'] += 1
    if complete('negoce_entetes', 'negoce_lignes', 'devises'):
        headers = defaultdict(list)
        for header in f.rows(source, rid, 'negoce_entetes'):
            headers[b.text(f.field(header, 'Entete'))].append(header)
        header_cache = {}
        allowed = {w.casefold() for w in config['warehouses']}
        for line in f.rows(source, rid, 'negoce_lignes'):
            variant = b.key(line)
            if variant[0] not in variants:
                continue
            order = b.text(f.field(line, 'Entete'))
            join_key = (order, b.text(f.field(line, 'Magasin')), b.text(f.field(line, 'Client')))
            if join_key not in header_cache:
                candidates = headers.get(order, [])
                for field_name, value in zip(('Magasin', 'Client'), join_key[1:]):
                    if value:
                        candidates = [h for h in candidates if b.text(f.field(h, field_name)) == value]
                header_cache[join_key] = candidates[0] if len(candidates) == 1 else None
            header = header_cache[join_key]
            if header is None:
                excluded['customer_ambiguous_or_missing_header'] += 1; continue
            order_date = date(f.field(header, 'Date'))
            if not order_date or order_date > cutoff:
                excluded['customer_date'] += 1; continue
            if f.field(header, 'Nature') != 'COMMANDE' or f.field(line, 'Nature') != 'COMMANDE':
                excluded['not_customer_order'] += 1; continue
            if b.text(f.field(header, 'Magasin')).casefold() not in allowed or (b.text(f.field(line, 'Magasin')) and b.text(f.field(line, 'Magasin')).casefold() not in allowed):
                excluded['customer_other_warehouse'] += 1; continue
            if any(b.text(f.field(r, 'Statut')) not in ('1', '3') for r in (header, line)) or f.field(header, 'non_facturable') not in (0, False, '0'):
                excluded['customer_cancelled_unconfirmed_or_nonbillable'] += 1; continue
            currency = currencies.get(b.text(f.field(line, 'Devise')))
            if currency not in iso_codes or currencies.get(b.text(f.field(header, 'Devise'))) != currency:
                excluded['customer_currency'] += 1; continue
            qty, unit, discount, value = (b.numeric(f.field(line, name)) for name in ('Quantite', 'Prix_HT_Devise', 'Remise', 'Total_HT_Devise'))
            if any(v is None for v in (qty, unit, discount, value)) or min(qty, unit, value) <= 0 or discount > 100:
                excluded['customer_invalid_price'] += 1; continue
            if abs(value - qty * unit * (1 - discount / 100)) > .02:
                excluded['customer_total_mismatch'] += 1; continue
            price = float((Decimal(str(value)) / Decimal(str(qty))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
            if price <= 0:
                excluded['customer_invalid_price'] += 1; continue
            add_latest(customer_groups, (variant, currency), dict(price=price, currency=currency, orderId=order,
                orderNumber=b.text(f.field(header, 'Numero')), orderDate=order_date, lineId=b.text(f.field(line, 'Ligne')),
                customer=b.text(f.field(header, 'Client')), source='Joolan customer order', matchedVariant=list(variant)))
    else:
        excluded['customer_sources_incomplete'] += 1
    return supplier_groups, customer_groups, iso_codes, dict(excluded)


def purchase_diagnostic(variant,currency,reason,diagnostics,fx_policy):
    """Native prices and different vendors remain evidence, not invented defaults."""
    from supplier_fx import convert
    candidates=[];foreign=[]
    for (key,native,supplier),options in diagnostics.get('alternatives',{}).get(variant,[]):
        chosen,_=select_latest(options)
        if not chosen:continue
        if native!=currency:
            fx=convert(chosen['price'],native,currency,chosen.get('recordedRate'),fx_policy)
            if not fx:
                foreign.append(chosen);continue
            chosen=dict(chosen,price=fx['unitCost'],unitCost=fx['unitCost'],currency=currency,fx=fx)
        candidates.append(dict(chosen,requiresReview=True,reviewReason='Historical supplier differs from the current article supplier. Confirm supplier and prices before financial review.'))
    candidates.sort(key=lambda r:(r['orderDate'],r['orderId']),reverse=True)
    reasons=dict(diagnostics.get('reasons',{}).get(variant,{}))
    if diagnostics.get('sourceState')!='ready':code=diagnostics.get('sourceState','INCOMPLETE_SOURCE')
    elif reason and 'Conflicting' in reason:code='CONFLICTING_LATEST_PRICE'
    elif candidates:code='SUPPLIER_CHANGED'
    elif foreign:code='FX_UNAVAILABLE'
    elif reasons:code=max(reasons,key=reasons.get)
    elif diagnostics.get('references',{}).get(variant[0]):code='OTHER_VARIANTS_NOT_UNIFORM'
    else:code='NO_SUPPLIER_ORDERS'
    messages={
        'INCOMPLETE_SOURCE':'Supplier-order or currency datasets are incomplete. A latest source price cannot be certified.',
        'UNVERIFIED_COST_BASIS':'Confirm supplier price and discount semantics in Budget settings before importing order costs.',
        'CONFLICTING_LATEST_PRICE':'The latest order date has conflicting prices. No older price was substituted.',
        'SUPPLIER_CHANGED':'Usable historical prices exist for a different supplier. Confirm the supplier before using a candidate.',
        'FX_UNAVAILABLE':'A native-currency price exists, but no verified conversion and usable order rate are available for this budget currency.',
        'ZERO_OR_INVALID_PRICE':'Supplier order lines have zero/missing prices or invalid discounts. Zero is not treated as free stock.',
        'CURRENCY_UNMAPPED':'The saved currency reference does not identify this supplier currency.',
        'UNCONFIRMED_OR_CANCELLED':'Only unconfirmed, cancelled or unknown-status supplier evidence was found.',
        'INVALID_OR_FUTURE_DATE':'Supplier order dates are missing, invalid or later than the source cutoff.',
        'SUPPLIER_MISSING':'Supplier identity is missing from the order.',
        'OTHER_VARIANTS_NOT_UNIFORM':'Other sizes or colours have order history, but their prices do not establish a uniform safe default for this variant.',
        'NO_SUPPLIER_ORDERS':'No supplier order was exported for this article.'}
    return dict(reasonCode=code,reason=messages[code],rejectionCounts=reasons,
                alternatives=candidates[:5],otherCurrencyCandidates=sorted(foreign,key=lambda r:r['orderDate'],reverse=True)[:5])


def sync(conn, path=None, force=False, through_date=None):
    """Read one immutable export; publish prices atomically after identity checks."""
    ensure(conn)
    from planning import active_plan
    if not active_plan(conn):
        return dict(skipped='Select a planning season before resolving order prices.')
    config, plan = b.settings(conn)
    rid, export, metadata, revision = b.source_identity(conn, path)
    requested = through_date or dt.datetime.now(dt.timezone.utc).date().isoformat()
    if not date(requested) or not date(export['throughDate']):
        raise ValueError('Invalid order-price cutoff date.')
    cutoff = min(export['throughDate'], requested)
    relevant = dict(warehouses=config['warehouses'], poCostsVerified=config['poCostsVerified'], currency=plan['currency'])
    from supplier_fx import policy
    fx_policy=policy(conn,export)
    relevant['fxPolicy']=fx_policy
    fingerprint = hashlib.sha256(json.dumps([VERSION, rid, revision, relevant, cutoff], sort_keys=True).encode()).hexdigest()
    with _lock:
        previous = conn.execute("SELECT value FROM planning_state WHERE key='order_price_import'").fetchone()
        # Upgrade the initial v1 marker without rescanning unchanged evidence.
        legacy = hashlib.sha256(json.dumps([VERSION, rid, revision, config, cutoff], sort_keys=True).encode()).hexdigest()
        if not force and previous and json.loads(previous[0]).get('fingerprint') == legacy:
            report = dict(json.loads(previous[0]), fingerprint=fingerprint)
            with conn:
                conn.execute("UPDATE planning_state SET value=? WHERE key='order_price_import'", (json.dumps(report),))
            return report
        if not force and previous and json.loads(previous[0]).get('fingerprint') == fingerprint:
            return json.loads(previous[0])
        skus = conn.execute('SELECT sku,reference,color,size FROM catalogue_skus WHERE current=1').fetchall()
        variants = {tuple(r[1:]) for r in skus}
        references = {v[0] for v in variants}
        source = f.connect(path)
        try:
            complete = lambda *names: all(json.loads(metadata.get(n, '{}')).get('complete') for n in names)
            diagnostics={}
            purchase, selling, currencies, excluded = collect(source, rid, references, config, cutoff, complete,fx_policy,plan['currency'],diagnostics)
        finally:
            source.close()
        # Resolve observed transaction currencies, not every unused reference code.
        currencies = sorted({key[1] for key in purchase} | {key[1] for key in selling} | {plan['currency']} | {r[0] for r in conn.execute('SELECT DISTINCT currency FROM catalogue_prices')})
        resolved = {'purchase': resolve(purchase, variants, currencies), 'selling': resolve(selling, variants, currencies)}
        # Index candidates once; do not scan every supplier line per catalogue SKU.
        alternatives=defaultdict(list)
        for key,value in diagnostics['alternatives'].items():alternatives[key[0]].append((key,value))
        diagnostics['alternatives']=alternatives
        counts = Counter()
        now = f.now()
        with conn:
            current_identity = b.source_identity(conn, path)
            if current_identity[0] != rid or current_identity[1] != export or current_identity[3] != revision or b.settings(conn) != (config, plan) or policy(conn,current_identity[1])!=fx_policy:
                raise ValueError('Source or financial settings changed during price selection. Retry.')
            old = {(sku, currency, side): (price, json.loads(payload)) for sku, currency, side, price, payload in conn.execute('SELECT * FROM catalogue_order_prices')}
            records = []
            for sku, ref, color, size in skus:
                for currency in currencies:
                    conn.execute("INSERT OR IGNORE INTO catalogue_prices VALUES(?,?,NULL,NULL,'orders','orders',?)", (sku, currency, now))
                    for side in ('purchase', 'selling'):
                        selected, reason = resolved[side][((ref, color, size), currency)]
                        price = selected['price'] if selected else None
                        detail = dict(selected or {}, reason=reason, sourceRun=rid, cutoff=cutoff, updatedAt=now, currency=currency)
                        if side=='purchase' and not selected:
                            detail.update(purchase_diagnostic((ref,color,size),currency,reason,diagnostics,fx_policy))
                        before = old.get((sku, currency, side))
                        if before:
                            if before[0] != price:
                                detail.update(previousPrice=before[0], changedAt=now)
                            else:
                                detail.update({k: before[1][k] for k in ('previousPrice', 'changedAt') if k in before[1]})
                        records.append((sku, currency, side, price, json.dumps(detail)))
                        tag = ('supplier:' if side == 'purchase' else 'customer:') + selected['orderId'] if selected else 'orders:unmatched'
                        conn.execute(f"UPDATE catalogue_prices SET {side}=?,{side}_source=?,updated_at=? WHERE sku=? AND currency=? AND {side}_source<>'manual'", (price, tag, now, sku, currency))
                        if currency == plan['currency']:
                            counts[side + ('Matched' if selected else 'Missing')] += 1
            conn.executemany('INSERT OR REPLACE INTO catalogue_order_prices VALUES(?,?,?,?,?)', records)
            report = dict(fingerprint=fingerprint, policy=VERSION, sourceRun=rid, cutoff=cutoff, currency=plan['currency'], updatedAt=now, excluded=excluded, **counts)
            conn.execute("INSERT OR REPLACE INTO planning_state VALUES('order_price_import',?)", (json.dumps(report),))
        return report


def reset(conn, rows, currency):
    """Explicitly restore automatic evidence without changing budget/PO snapshots."""
    ensure(conn)
    if currency not in b.SUPPORTED_CURRENCIES or not isinstance(rows, list) or not 0 < len(rows) <= 1000:
        raise ValueError('Select 1 to 1000 SKU prices and a supported currency.')
    validated = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'sku', 'side'} or row['side'] not in ('purchase', 'selling'):
            raise ValueError('Select a SKU and purchase or selling price.')
        item = conn.execute('SELECT price,payload FROM catalogue_order_prices WHERE sku=? AND currency=? AND side=?', (row['sku'], currency, row['side'])).fetchone()
        if item is None:
            raise ValueError('Refresh order-price evidence before restoring this price.')
        detail = json.loads(item[1])
        tag = ('supplier:' if row['side'] == 'purchase' else 'customer:') + detail['orderId'] if item[0] is not None else 'orders:unmatched'
        validated.append((row['side'], item[0], tag, row['sku']))
    with conn:
        for side, price, tag, sku in validated:
            conn.execute(f'UPDATE catalogue_prices SET {side}=?,{side}_source=?,updated_at=? WHERE sku=? AND currency=?', (price, tag, f.now(), sku, currency))
        conn.execute("INSERT OR REPLACE INTO planning_state VALUES('catalogue_prices_updated',?)", (f.now(),))
    return dict(saved=len(validated), notice='Latest order-price defaults restored. Saved budget drafts and POs retain their snapshots.')
