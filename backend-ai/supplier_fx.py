"""Verified Joolan order-rate conversion for planning, never a market FX feed."""
import datetime as dt
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def convert(unit_cost, currency, target, rate, policy):
    """Return a traceable budget unit price only for a verified currency pair."""
    if not isinstance(currency,str) or not isinstance(target,str):return None
    pair=(policy or {}).get('pairs',{}).get(currency+'>'+target)
    if not pair or pair.get('method')!='divide' or not pair.get('verified'):
        return None
    try:
        if isinstance(unit_cost,bool) or isinstance(rate,bool):return None
        value,fx=Decimal(str(unit_cost)),Decimal(str(rate))
        if not value.is_finite() or not fx.is_finite() or value<=0 or fx<=0:return None
        converted=float((value/fx).quantize(Decimal('.000001'),rounding=ROUND_HALF_UP))
    except (InvalidOperation,ValueError,TypeError,OverflowError):return None
    if converted<=0:return None
    return dict(unitCost=converted,currency=target,nativeUnitCost=float(value),nativeCurrency=currency,
                exchangeRate=float(fx),method='native / recorded order rate',rateSource='commandes.Taux_Devise',
                verificationId=pair['verificationId'],notice='Historical recorded order FX for planning; not a current settlement rate.')


def policy(conn,export):
    row=conn.execute("SELECT value FROM planning_state WHERE key='supplier_fx_policy'").fetchone()
    saved=json.loads(row[0]) if row else {}
    return saved if saved.get('enseigne')==export.get('enseigne') else {}


def verify(conn,rows,currencies,enseigne):
    """Validate division against actual saved receipt native/base price pairs.

    Only the EUR base used by this integration is supported. Unknown currencies,
    ambiguous direction, non-receipts and inconsistent samples do not enable FX.
    Called explicitly after a read-only Joolan verification export, never on GET.
    """
    import budgeting as b
    import fresh_joolan as f
    grouped={};base_witness=[]
    for row in rows:
        currency=currencies.get(b.text(f.field(row,'Devise')))
        if not currency or b.text(f.field(row,'Nature')).casefold()!='réception':continue
        native=b.numeric(f.field(row,'Prix_Achat_Devise'));base=b.numeric(f.field(row,'Prix_Achat'));rate=b.numeric(f.field(row,'Taux_Devise'))
        if any(v is None or v<=0 for v in (native,base,rate)):continue
        if currency=='EUR':
            if rate==1 and abs(native-base)<=.02:base_witness.append(dict(movement=b.text(f.field(row,'Mouvement')),basePrice=base,currency='EUR'))
            continue
        grouped.setdefault(currency,[]).append(dict(movement=b.text(f.field(row,'Mouvement')),date=b.text(f.field(row,'Date')),
            nativePrice=native,basePrice=base,rate=rate,divideMatches=abs(native/rate-base)<=.02,multiplyMatches=abs(native*rate-base)<=.02))
    if not base_witness:raise ValueError('The receipt export did not corroborate an EUR base. No FX policy was changed.')
    pairs={}
    for currency,samples in grouped.items():
        if (len({s['movement'] for s in samples if s['movement']})<2 or
            not all(s['divideMatches'] for s in samples) or not any(not s['multiplyMatches'] for s in samples)):
            continue
        ident=hashlib.sha256(json.dumps([enseigne,currency,'EUR',samples,base_witness],sort_keys=True).encode()).hexdigest()
        pairs[currency+'>EUR']=dict(verified=True,method='divide',verificationId=ident,
            sampleCount=len(samples),samples=samples,source='Joolan mouvements_lignes: native Prix_Achat_Devise / Taux_Devise reconciles to base Prix_Achat',
            verifiedAt=dt.datetime.now(dt.timezone.utc).isoformat())
    if not pairs:raise ValueError('Receipt evidence did not establish an unambiguous order-rate conversion. No FX policy was changed.')
    previous=policy(conn,dict(enseigne=enseigne))
    record=dict(version='recorded-order-fx-v1',enseigne=enseigne,baseCurrency='EUR',baseEvidence=base_witness,pairs={**previous.get('pairs',{}),**pairs})
    conn.execute("INSERT OR REPLACE INTO planning_state VALUES('supplier_fx_policy',?)",(json.dumps(record),))
    return record
