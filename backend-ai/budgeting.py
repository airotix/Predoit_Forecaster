"""Draft purchase budget from a published forecast and versioned Joolan records.

Unknown values are distinct from zero. No exchange rates or tariff currencies
are inferred, and this module never approves or writes purchase orders.
"""
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
import hashlib
import json
import math
import threading
import unicodedata

import fresh_joolan as fresh
from planning import active_plan, final_rows

SUPPORTED_CURRENCIES=('EUR','USD','GBP','CHF','CAD','AUD','PKR')
DEFAULTS=dict(brands=['DAYTONA73'],warehouses=['CENTRAL'],sellingTariff='Negoce',
    costField='Prix_Achat',costCurrency='EUR',tariffCurrency='EUR',
    costBasisVerified=False,tariffVerified=False,poCostsVerified=False,budgetConfigured=False,packRulesVerified=False,orderingRules={})
_source_lock=threading.Lock()

def numeric(value,negative=False):
    if value is None or isinstance(value,bool) or str(value).strip()=='':return None
    try:
        n=float(value)
        return n if math.isfinite(n) and (negative or n>=0) else None
    except (ValueError,TypeError):return None

def amount(quantity,price):
    if quantity is None or price is None:return None
    try:
        n=Decimal(str(quantity))*Decimal(str(price))
        value=float(n.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
        return value if math.isfinite(value) else None
    except (InvalidOperation,ValueError,OverflowError):return None

def net_price(price,*discounts):
    price=numeric(price)
    if price is None or price<=0:return None # Joolan zero placeholders are not confirmed free goods.
    result=Decimal(str(price))
    for discount in discounts:
        discount=numeric(discount)
        if discount is None or discount>100:return None
        result*=1-Decimal(str(discount))/100
    return float(result) if result.is_finite() else None

def text(value):return str(value or '').strip()
def key(r):return (text(fresh.field(r,'Produit')),text(fresh.field(r,'Couleur')) or 'UNKNOWN',text(fresh.field(r,'Taille')) or 'UNKNOWN')
def status(value):
    normalized=''.join(ch for ch in unicodedata.normalize('NFKD',text(value)).casefold() if not unicodedata.combining(ch))
    return {'validee':'open','soldee':'closed','annulee':'cancelled','en saisie':'draft'}.get(normalized,'unknown')

def settings(conn):
    plan=active_plan(conn)
    if not plan:raise ValueError('Save a planning season in Setup first.')
    row=conn.execute('SELECT value FROM planning_state WHERE key=?',('budget_settings:'+plan['id'],)).fetchone()
    saved=json.loads(row[0]) if row else {}
    result={**DEFAULTS,**saved,'budgetConfigured':saved.get('budgetConfigured',float(plan['budget'])>0)}
    from operating_scope import read,primary
    operating=read(conn)
    if operating:result.update(brands=operating['brands'],warehouses=primary(operating))
    return result,plan

def save_settings(conn,data):
    current,plan=settings(conn)
    unknown=set(data)-set(DEFAULTS)
    if unknown:raise ValueError('Unsupported budget settings: '+', '.join(sorted(unknown)))
    current.update(data)
    from operating_scope import read,primary
    operating=read(conn)
    if operating and (set(current['brands'])!=set(operating['brands']) or set(current['warehouses'])!=set(primary(operating))):raise ValueError('Change brands and warehouse roles in Business Scope; normal supply uses primary warehouses only.')
    for name in ('brands','warehouses'):
        values=current[name]
        if not isinstance(values,list) or not values or len(values)>100 or any(not isinstance(v,str) or not v.strip() for v in values):raise ValueError('Select at least one '+name+' value.')
        current[name]=sorted(set(v.strip() for v in values))
    for name in ('costCurrency','tariffCurrency'):
        if current[name] not in SUPPORTED_CURRENCIES:raise ValueError('Select a supported '+name+'.')
    if current['costField'] not in ('Prix_Achat','Prix_Achat_Moyen'):raise ValueError('Unsupported cost field.')
    if not isinstance(current['sellingTariff'],str):raise ValueError('Select a selling tariff.')
    from order_constraints import validate_rules
    validate_rules(current['orderingRules'])
    for name in ('costBasisVerified','tariffVerified','poCostsVerified','budgetConfigured','packRulesVerified'):
        if type(current[name]) is not bool:raise ValueError(name+' must be a boolean.')
    with conn:conn.execute('INSERT OR REPLACE INTO planning_state VALUES(?,?)',('budget_settings:'+plan['id'],json.dumps(current)))
    return current

def source_identity(conn,path=None):
    state=dict(conn.execute('SELECT key,value FROM joolan_state'))
    rid=state.get('fresh_run')
    if not rid:raise ValueError('Activate a validated fresh Joolan export first.')
    source=fresh.connect(path)
    try:
        run=source.execute('SELECT status,config FROM runs WHERE id=?',(rid,)).fetchone()
        if not run or run[0]!='validated':raise ValueError('The active Joolan source is not validated.')
        metadata=dict(source.execute('SELECT dataset,metadata FROM datasets WHERE run_id=?',(rid,)))
        revision=hashlib.sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest()
        return rid,json.loads(run[1]),metadata,revision
    finally:source.close()

def compact(r,names):return {name:fresh.field(r,name) for name in names}

@lru_cache(maxsize=1)
def _load_source(path,rid,revision):
    from derived_cache import load,store
    signature=json.dumps([str(path),rid,revision,'budget-source-v2'])
    saved=load(path,'budget-source',signature)
    if isinstance(saved,dict) and all(isinstance(saved.get(k),dict) for k in ('products','headers','tariffs')) and all(isinstance(saved.get(k),list) for k in ('skus','poPrices','quantities','inventory','currencies')):
        try:
            skus={tuple(k):v for k,v in saved['skus']};prices={tuple(k):v for k,v in saved['poPrices']}
            if all(len(k)==3 and isinstance(v,dict) for k,v in skus.items()) and all(len(k)==4 and isinstance(v,dict) for k,v in prices.items()):
                return dict(saved,skus=skus,poPrices=prices)
        except (TypeError,ValueError):pass
    source=fresh.connect(path)
    try:
        products={text(fresh.field(r,'Produit')):compact(r,('Produit','Marque','Famille','Designation','Taux_TVA_Vente','Fournisseur','Conditionnement_Achat')) for r in fresh.rows(source,rid,'produits')}
        skus={};ambiguous=set()
        for r in fresh.rows(source,rid,'skus'):
            k=key(r)
            if k in skus:ambiguous.add(k)
            skus[k]=compact(r,('Produit','Couleur','Taille','Prix_Achat','Prix_Achat_Moyen','Remise_Achat'))
        for k in ambiguous:skus.pop(k,None)
        headers={text(fresh.field(r,'Commande')):compact(r,('Commande','Numero_Commande','Fournisseur','Date','Date_Livraison','Statut','Devise','Taux_Devise','Remise1','Remise2','Remise3','Remise4','Remise5')) for r in fresh.rows(source,rid,'commandes')}
        prices={}
        for r in fresh.rows(source,rid,'commandes_produits'):
            prices[(text(fresh.field(r,'Commande')),*key(r))]=compact(r,('Commande','Produit','Couleur','Taille','Prix_Achat_Devise','Remise_Achat'))
        result=dict(products=products,skus=skus,headers=headers,poPrices=prices,
            quantities=[compact(r,('Commande','Produit','Couleur','Taille','Magasin','Quantite','Quantite_Livree','Statut')) for r in fresh.rows(source,rid,'commandes_quantites')],
            inventory=[compact(r,('Magasin','Produit','Couleur','Taille','Disponible','En_Livraison')) for r in fresh.rows(source,rid,'inventory')],
            tariffs={text(fresh.field(r,'Tarif')):r for r in fresh.rows(source,rid,'tarifs')},
            currencies=[])
        if len(skus)>=1000:
            store(path,'budget-source',signature,dict(result,skus=list(skus.items()),poPrices=list(prices.items())))
        return result
    finally:source.close()

@lru_cache(maxsize=2)
def _load_tariff(path,rid,revision,tariff):
    source=fresh.connect(path)
    try:
        rows=source.execute("SELECT payload FROM records WHERE run_id=? AND dataset='tarifsproduits' AND json_extract(payload,'$.Tarif')=?",(rid,tariff))
        return {(text(fresh.field(r,'Produit')),text(fresh.field(r,'Couleur')),text(fresh.field(r,'Taille'))):compact(r,('Prix_Vente','Remise_Vente'))
            for r in (json.loads(value[0]) for value in rows)}
    finally:source.close()

@lru_cache(maxsize=2)
def _load_currencies(path,rid,revision):
    source=fresh.connect(path)
    try:return list(fresh.rows(source,rid,'devises'))
    finally:source.close()

def options(conn,path=None):
    rid,config,metadata,revision=source_identity(conn,path)
    source=fresh.connect(path)
    try:
        brands=sorted({text(fresh.field(r,'Marque')) for r in fresh.rows(source,rid,'produits')} - {''})
        tariffs=[dict(code=text(fresh.field(r,'Tarif')),name=text(fresh.field(r,'Libelle')),exTax=fresh.field(r,'HT')==1) for r in fresh.rows(source,rid,'tarifs')]
        currencies=[dict(code=text(fresh.field(r,'Devise')),iso=text(fresh.field(r,'currency_code')) or text(fresh.field(r,'Code')),name=text(fresh.field(r,'Nom'))) for r in fresh.rows(source,rid,'devises')]
        observed=sorted({text(fresh.field(r,'Devise')) for r in fresh.rows(source,rid,'commandes')} - {''})
        current,plan=settings(conn)
        from operating_scope import read
        return dict(settings=current,season=plan,brands=brands,warehouses=config['warehouses'],tariffs=tariffs,currencies=currencies,observedCurrencyCodes=observed,sourceRun=rid,operatingScope=read(conn))
    finally:source.close()

def _stock(source,warehouses):
    balances={};transit=set();invalid=set()
    for r in source['inventory']:
        raw=text(fresh.field(r,'Magasin'))
        if not any(raw.casefold()==w.casefold() for w in warehouses):continue
        k=key(r)
        try:warehouse=fresh.warehouse_code(raw,warehouses)
        except ValueError:invalid.add(k);continue
        value=numeric(fresh.field(r,'Disponible'),True)
        by_store=balances.setdefault(k,{})
        if value is None or warehouse in by_store:invalid.add(k)
        else:by_store[warehouse]=value
        shipping=numeric(fresh.field(r,'En_Livraison'))
        if shipping is None or shipping>0:transit.add(k)
    return {k:sum(v.values()) for k,v in balances.items() if k not in invalid and set(v)==set(warehouses)},transit

def _currency_map(source):
    result={code:code for code in SUPPORTED_CURRENCIES}
    for r in source['currencies']:
        code=text(fresh.field(r,'Devise'));iso=text(fresh.field(r,'currency_code')).upper()
        if iso not in SUPPORTED_CURRENCIES:iso=text(fresh.field(r,'Code')).upper()
        # Some Joolan references expose a literal ISO code only in Nom (e.g.
        # Devise=02, Nom=USD, empty Code). Never infer from arbitrary labels.
        if iso not in SUPPORTED_CURRENCIES:iso=text(fresh.field(r,'Nom')).upper()
        if code and iso in SUPPORTED_CURRENCIES:result[code]=iso
    return result

def _po_ledger(source,config,plan,products,as_of=None,fx_policy=None):
    currencies=_currency_map(source);incoming={};unknown_incoming=set();ledger=[];unallocated=[]
    headers=source['headers'];prices=source['poPrices'];start=dt.date.fromisoformat(plan['startDate']);end=dt.date.fromisoformat(plan['endDate'])
    def exception(reason,r,header=None):
        header=header or {}
        unallocated.append(dict(reason=reason,orderId=text(fresh.field(r,'Commande')),orderNumber=text(fresh.field(header,'Numero_Commande')),
            supplier=text(fresh.field(header,'Fournisseur')),reference=key(r)[0],color=key(r)[1],size=key(r)[2],warehouse=text(fresh.field(r,'Magasin')),
            receiptDate=text(fresh.field(header,'Date_Livraison')) or None))
    for r in source['quantities']:
        k=key(r)
        if k[0] not in products:continue
        raw_store=text(fresh.field(r,'Magasin'))
        if not any(raw_store.casefold()==w.casefold() for w in config['warehouses']):continue
        command=text(fresh.field(r,'Commande'));header=headers.get(command);p=prices.get((command,*k))
        if not header:unknown_incoming.add(k);exception('Unmatched supplier order',r);continue
        header_status=status(fresh.field(header,'Statut'));line_status=status(fresh.field(r,'Statut')) if text(fresh.field(r,'Statut')) else header_status
        # Cancellation/closure on the header prevents draft/open lines becoming receipts.
        role=header_status if header_status in ('cancelled','closed','draft','unknown') else line_status
        if role=='draft':continue
        ordered=numeric(fresh.field(r,'Quantite'));delivered=numeric(fresh.field(r,'Quantite_Livree'))
        if ordered is None or delivered is None:unknown_incoming.add(k);exception('Invalid supplier quantities',r,header);continue
        remaining=max(ordered-delivered,0) if role=='open' else 0.
        eta=fresh.field(header,'Date_Livraison')
        try:date=dt.date.fromisoformat(str(eta)[:10])
        except (ValueError,TypeError):date=None
        if role=='unknown':unknown_incoming.add(k);exception('Unknown supplier status',r,header);continue
        if role in ('cancelled','closed') and delivered==0:continue
        if ordered==0 and delivered==0:continue
        if date is None or (role=='open' and remaining>0 and date<dt.date.fromisoformat(as_of or plan['startDate'])):
            if role=='open':unknown_incoming.add(k)
            exception('Missing planned receipt date' if date is None else 'Overdue open supplier order',r,header)
            continue
        if date<start or date>end:continue
        if role=='open':incoming[k]=incoming.get(k,0.)+remaining
        unit=None
        if config['poCostsVerified'] and p:
            unit=net_price(fresh.field(p,'Prix_Achat_Devise'),fresh.field(p,'Remise_Achat'),*(fresh.field(header,'Remise'+str(i)) for i in range(1,6)))
        code=text(fresh.field(header,'Devise'));iso=currencies.get(code)
        committed_units=max(ordered,delivered) if role=='open' else delivered
        native=amount(committed_units,unit)
        cost=native if iso==plan['currency'] else None
        from supplier_fx import convert
        fx=convert(unit,iso,plan['currency'],fresh.field(header,'Taux_Devise'),fx_policy) if cost is None else None
        if fx:cost=amount(committed_units,fx['unitCost'])
        ledger.append(dict(orderId=command,orderNumber=text(fresh.field(header,'Numero_Commande')),supplier=text(fresh.field(header,'Fournisseur')),
            reference=k[0],color=k[1],size=k[2],warehouse=raw_store,status=role,receiptDate=date.isoformat(),ordered=ordered,delivered=delivered,outstanding=remaining,
            currency=iso or code or 'Unknown',nativeValue=native,value=cost,unitCost=unit,
            budgetCurrency=plan['currency'],budgetUnitCost=fx['unitCost'] if fx else unit if iso==plan['currency'] else None,fx=fx))
    for k in unknown_incoming:incoming[k]=None
    return ledger,incoming,unknown_incoming,unallocated

def inventory_for_forecast(conn,path=None):
    """One receipt-aware quantity contract shared by forecasts and Budget Tracker."""
    config,plan=settings(conn);rid,export,metadata,revision=source_identity(conn,path)
    source_path=str(path or fresh.SOURCE_DB)
    core=hashlib.sha256(json.dumps({k:v for k,v in metadata.items() if k!='devises'},sort_keys=True).encode()).hexdigest()
    with _source_lock:
        source={**_load_source(source_path,rid,core),'currencies':_load_currencies(source_path,rid,metadata.get('devises',''))}
    products={k:v for k,v in source['products'].items() if text(fresh.field(v,'Marque')) in config['brands']}
    stock,transit=_stock(source,config['warehouses'])
    from supplier_fx import policy
    ledger,incoming,unknown,unallocated=_po_ledger(source,config,plan,products,export['throughDate'],policy(conn,export))
    complete=all(json.loads(metadata.get(t,'{}')).get('complete') for t in ('commandes','commandes_produits','commandes_quantites'))
    return [dict(Reference=k[0],Couleur=k[1],Taille=k[2],STOCK=stock.get(k),
        CDE_four_qte=incoming.get(k,0.) if complete and k not in transit and k not in unknown else None)
        for k in source['skus'] if k[0] in products]


@lru_cache(maxsize=2)
def _supply_view(path,rid,revision,currency_revision,config_json,plan_json,as_of,fx_policy_json):
    """Source/warehouse/receipt calculations are identical across scenarios."""
    source={**_load_source(path,rid,revision),'currencies':_load_currencies(path,rid,currency_revision)}
    config,plan=json.loads(config_json),json.loads(plan_json)
    products={p:r for p,r in source['products'].items() if text(fresh.field(r,'Marque')) in config['brands']}
    stock,transit=_stock(source,config['warehouses'])
    ledger,incoming,unknown,unallocated=_po_ledger(source,config,plan,products,as_of,json.loads(fx_policy_json))
    return products,stock,transit,ledger,incoming,unknown,unallocated


def build_report(conn,scenario='base',path=None,sync_catalogue=True):
    from catalogue import sync,price_map
    if sync_catalogue:sync(conn,path)
    config,plan=settings(conn);rid,export,metadata,revision=source_identity(conn,path)
    saved_prices=price_map(conn,plan['currency'])
    if not set(config['warehouses'])<=set(export['warehouses']):raise ValueError('Selected warehouses were not included in this fresh export.')
    source_path=str(path or fresh.SOURCE_DB)
    core_revision=hashlib.sha256(json.dumps({k:v for k,v in metadata.items() if k!='devises'},sort_keys=True).encode()).hexdigest()
    with _source_lock:
        source={**_load_source(source_path,rid,core_revision),'currencies':_load_currencies(source_path,rid,metadata.get('devises',''))}
    with _source_lock:
        from supplier_fx import policy
        fx_policy=policy(conn,export)
        products,stock,transit,ledger,incoming,unknown_incoming,unallocated=_supply_view(
            source_path,rid,core_revision,metadata.get('devises',''),json.dumps(config,sort_keys=True),json.dumps(plan,sort_keys=True),export['throughDate'],json.dumps(fx_policy,sort_keys=True))
    if not products:raise ValueError('The selected brands have no products in the active export.')
    with _source_lock:tariff_prices=_load_tariff(source_path,rid,core_revision,config['sellingTariff'])
    tariff=source['tariffs'].get(config['sellingTariff'],{})
    rows=[];coverage=dict(variants=0,stockKnown=0,incomingKnown=0,costKnown=0,priceKnown=0,purchasePriced=0)
    supply_issues={}
    for exception in unallocated:
        supply_issues.setdefault((exception['reference'],exception['color'],exception['size']),set()).add(exception['reason'])
    categories={}
    for r in final_rows(conn,scenario,include_draft=False,_saved_prices=saved_prices):
        if r['reference'] not in products:continue
        forecast=numeric(r['demand_forecast']);required=numeric(r.get('future_demand',forecast));override=r.get('manual_override')
        if not forecast and not override:continue
        k=(r['reference'],r['couleur'],r['taille']);p=products[k[0]];sku=source['skus'].get(k,{})
        available=stock.get(k);supply=incoming.get(k,0.) if k not in transit else None
        if any(name not in metadata or not json.loads(metadata[name]).get('complete') for name in ('commandes','commandes_produits','commandes_quantites')):supply=None
        qty=override if override is not None else max(required-available-supply,0) if required is not None and available is not None and supply is not None else None
        if r.get('purchasing_blocked') and override is None:qty=0.
        saved=saved_prices.get(k,{})
        cost=saved.get('purchase');price=saved.get('selling')
        buy_cost=0. if qty==0 else amount(qty,cost)
        revenue=amount(forecast,price);cogs=amount(forecast,cost);margin=revenue-cogs if revenue is not None and cogs is not None else None
        gaps=[]
        for label,value in [('Available stock',available),('Scheduled supply',supply),('Purchase cost',cost),('Selling price',price)]:
            if value is None:gaps.append(label)
        row=dict(reference=k[0],color=k[1],size=k[2],name=text(fresh.field(p,'Designation')),category=text(fresh.field(p,'Famille')) or 'Other',
            forecast=forecast,futureDemand=required,stock=available,incoming=supply,purchaseQuantity=qty,manualOverride=override,unitCost=cost,unitPrice=price,
            purchaseCost=buy_cost,revenue=revenue,grossMargin=margin,marginPercent=margin/revenue*100 if margin is not None and revenue else None,missing=gaps)
        row['requiresAssortmentReview']='ASSORTMENT_REVIEW' in str(r.get('financial_note',''))
        row['requiresDeliveryReview']='DELIVERY_DATE_UNKNOWN' in str(r.get('financial_note',''))
        from order_constraints import applicable
        variant_identity=json.dumps([k[0],k[1],k[2]],separators=(',',':'))
        row['orderingRules']=applicable(config,k[0],variant_identity,numeric(fresh.field(p,'Conditionnement_Achat')))
        row['catalogueStatus']=r.get('catalogue_status',{})
        row['purchasingBlocked']=r.get('purchasing_blocked',False)
        if row['purchasingBlocked']:
            row['orderingRules'].update(blocked=True,blockedReason=r.get('status_reason','Inactive catalogue item'))
        row['recordedPurchasePack']=numeric(fresh.field(p,'Conditionnement_Achat'))
        row['needBy']=r.get('next_delivery_date')
        row['unitCostSource']='Saved manually' if saved.get('purchase_source')=='manual' else 'Supplier order price unavailable'
        row['unitPriceSource']='Saved manually' if saved.get('selling_source')=='manual' else 'Customer order price unavailable'
        for side,field,details_field,label in [('purchase','unitCostSource','purchasePriceDetails','Supplier'),('selling','unitPriceSource','sellingPriceDetails','Customer')]:
            detail=saved.get(side+'_details')
            if detail:
                row[details_field]=detail
                if saved.get(side+'_source')!='manual' and saved.get(side) is not None:
                    row[field]=label+' order '+(detail.get('orderNumber') or detail.get('orderId',''))+' · '+detail['orderDate']+' · '+detail['currency']
        row['catalogueCostAvailable']=k in saved_prices
        row['catalogueSupplier']=text(fresh.field(p,'Fournisseur'))
        row['catalogueSellingManual']=saved.get('selling_source')=='manual'
        row['inputIssues']={}
        if cost is None:row['inputIssues']['purchase']=(row.get('purchasePriceDetails') or {}).get('reason','No usable supplier-order price in the budget currency.')
        if price is None:row['inputIssues']['selling']=(row.get('sellingPriceDetails') or {}).get('reason') or 'No usable confirmed customer-order price in the budget currency.'
        if available is None:row['inputIssues']['stock']='Forecast colour/size is not mapped to a unique current Joolan SKU.' if k not in source['skus'] else 'No complete, valid stock record for the selected primary warehouse. Missing is not zero.'
        if supply is None:row['inputIssues']['incoming']='; '.join(sorted(supply_issues.get(k,set()))) or ('Inventory reports goods in delivery; reconcile them against supplier receipts to avoid double counting.' if k in transit else 'Supplier quantity or source coverage is incomplete.')
        if row['requiresDeliveryReview']:row['inputIssues']['delivery']='Customer delivery dates or open balances require reconciliation in Joolan.'
        rows.append(row);coverage['variants']+=1
        for name,value in [('stockKnown',available),('incomingKnown',supply),('costKnown',cost),('priceKnown',price),('purchasePriced',buy_cost)]:coverage[name]+=value is not None
        categories.setdefault(row['category'],[]).append(row)
    known_new=round(sum(r['purchaseCost'] or 0 for r in rows),2);known_po=round(sum(r['value'] or 0 for r in ledger),2)
    po_complete=not unallocated and all(r['value'] is not None for r in ledger) and all(json.loads(metadata.get(t,'{}')).get('complete') for t in ('commandes','commandes_produits','commandes_quantites'))
    purchase_complete=bool(rows) and coverage['purchasePriced']==len(rows)
    complete=po_complete and purchase_complete
    total=round(known_new+known_po,2);budget=float(plan['budget']);remaining=round(budget-total,2) if complete else None
    revenue_known=round(sum(r['revenue'] or 0 for r in rows),2)
    margin_rows=[r for r in rows if r['grossMargin'] is not None]
    known_margin=round(sum(r['grossMargin'] for r in margin_rows),2)
    price_complete=bool(rows) and coverage['priceKnown']==len(rows)
    margin_complete=bool(rows) and len(margin_rows)==len(rows)
    currency_totals={}
    for r in ledger:
        if r['nativeValue'] is not None and r['currency']!=plan['currency']:currency_totals[r['currency']]=round(currency_totals.get(r['currency'],0)+r['nativeValue'],2)
    warnings=[]
    if not config['budgetConfigured']:warnings.append('Set and save your seasonal purchasing budget.')
    if not config['poCostsVerified']:warnings.append('Confirm supplier prices are before VAT and discounts are sequential percentages before valuing purchase commitments.')
    if unallocated:warnings.append(f'{len(unallocated)} supplier lines need a receipt date, status or quantity reconciliation before the total budget can be certified.')
    if unknown_incoming or transit:warnings.append('Overdue, unresolved or in-transit supply is not assumed available. Receipt reconciliation is required for affected variants.')
    if currency_totals:warnings.append('Original supplier-currency amounts remain visible. Only verified recorded order rates convert values into the buying currency; unconverted values stay unknown.')
    warnings.append('Draft season totals use planned supplier receipt dates. They are not paid invoices, a cash-flow statement or a time-phased replenishment plan. Purchase approval remains blocked.')
    warnings.append('Revenue and margin are forecast estimates using booked-order demand and the selected unit-cost basis. Unknown partial cancellations, purchase pack sizes and minimum orders are not resolved by this budget view.')
    warnings.append('Only configured ordering limits and verified purchase-pack values are enforced. Missing MOQ, supplier lead times, transport and duty inputs remain unspecified; displayed margin excludes unmapped landed charges.')
    category_report=[]
    for name,items in sorted(categories.items()):
        subtotal=round(sum(r['purchaseCost'] or 0 for r in items),2);m=[r for r in items if r['grossMargin'] is not None]
        category_report.append(dict(category=name,knownPurchaseCost=subtotal,complete=all(r['purchaseCost'] is not None for r in items),variants=len(items),unpriced=sum(r['purchaseCost'] is None for r in items),
            marginPercent=sum(r['grossMargin'] for r in m)/sum(r['revenue'] for r in m)*100 if len(m)==len(items) and sum(r['revenue'] for r in m)>0 else None))
    summary=dict(seasonBudget=budget,budgetConfigured=config['budgetConfigured'],knownPurchaseCost=known_new,totalPurchaseCost=known_new if purchase_complete else None,
        knownCommittedCost=known_po,committedCost=known_po if po_complete else None,knownBudgetUsage=total,budgetUsage=total/budget*100 if complete and budget>0 else None,
        remainingBudget=remaining,remainingAfterKnown=round(budget-total,2),purchaseComplete=purchase_complete,commitmentsComplete=po_complete,budgetComplete=complete,
        knownTurnover=revenue_known,expectedTurnover=revenue_known if price_complete else None,knownGrossMargin=known_margin,grossMargin=known_margin if margin_complete else None,
        grossMarginPercent=known_margin/revenue_known*100 if margin_complete and revenue_known>0 else None,marginComplete=margin_complete,
        targetMargin=float(plan['targetMargin']),currency=plan['currency'],overBudget=bool(config['budgetConfigured'] and total>budget))
    return dict(summary=summary,settings=config,season=plan,coverage=coverage,categories=category_report,rows=rows,purchaseOrders=ledger,
        supplierOptions=sorted({text(fresh.field(p,'Fournisseur')) for p in source['products'].values()}-{''}),
        fxPolicy=dict(baseCurrency=fx_policy.get('baseCurrency'),pairs={k:{field:v for field,v in p.items() if field!='samples'} for k,p in fx_policy.get('pairs',{}).items()}),
        unallocatedSupplierLines=len(unallocated),supplierExceptions=unallocated,otherCurrencyCommitments=currency_totals,warnings=warnings,financialComplete=complete and margin_complete,
        source=dict(runId=rid,historyThrough=export['throughDate'],inventoryAsOf=json.loads(metadata.get('inventory','{}')).get('fetchedAt'),
            currencyAsOf=json.loads(metadata.get('devises','{}')).get('fetchedAt'),revision=revision),scenario=scenario)
