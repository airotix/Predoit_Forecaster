"""Server-side order simulation and local financial review snapshots. No ERP writes."""
import datetime as dt
import hashlib
import json
import math
import uuid
import budgeting as b

def identity(row):
    return json.dumps([row['reference'],row['color'],row['size']],separators=(',',':'))


def supplier_quotes(report):
    """Historical price evidence is not limited to this season's commitments."""
    quotes={}
    currency=report['summary']['currency']
    def add(k,quote):
        quote['id']='supplier:'+hashlib.sha256(json.dumps([k,quote],sort_keys=True).encode()).hexdigest()[:24]
        existing=next((p for p in quotes.setdefault(k,[]) if p['id']==quote['id']),None)
        if existing:return existing
        quotes[k].append(quote)
        return quote
    for row in report['rows']:
        detail=row.get('purchasePriceDetails') or {}
        for evidence in [detail,*detail.get('alternatives',[])]:
            if (evidence.get('supplier') and evidence.get('currency')==currency and evidence.get('orderId') and
                evidence.get('orderDate') and b.numeric(evidence.get('price')) is not None):
                add(identity(row),dict(supplier=evidence['supplier'],order=evidence.get('orderNumber') or evidence['orderId'],
                    orderId=evidence['orderId'],unitCost=b.numeric(evidence['price']),date=evidence['orderDate'],currency=currency,
                    source='Alternative supplier order; confirmation required' if evidence.get('requiresReview') else 'Latest saved Joolan supplier order',
                    matchLevel=evidence.get('matchLevel','Exact colour and size'),requiresReview=bool(evidence.get('requiresReview')),fx=evidence.get('fx')))
    for i,p in enumerate(report['purchaseOrders']):
        unit=p.get('budgetUnitCost',p['unitCost'] if p['currency']==currency else None)
        if b.numeric(unit) is None or not p.get('supplier'):continue
        quote=add(identity(p),dict(supplier=p['supplier'],order=p['orderNumber'] or p['orderId'],orderId=p['orderId'],
            unitCost=unit,date=p['receiptDate'],currency=currency,source='Season supplier order; planned receipt date',matchLevel='Exact colour and size',fx=p.get('fx')))
        # Older drafts used positional IDs. Read them, but save content-based IDs.
        quote.setdefault('legacyIds',[]).append(str(i))
    return quotes


def quote_matches(quote,ident):
    return bool(ident and (ident==quote['id'] or ident in quote.get('legacyIds',[])))

def covered_data(rows,report):
    """A financial subset, not proof that the whole buying plan is complete."""
    fields=('quantity','stock','incoming','orderUnitCost','orderUnitPrice','orderCost','orderTurnover','orderGrossMargin','orderMarginRate')
    def resolved(r):
        return all(isinstance(r.get(k),(int,float)) and not isinstance(r.get(k),bool) and math.isfinite(r[k]) for k in fields)
    included=[r for r in rows if resolved(r) and r['quantity']>0 and not r.get('orderingRules',{}).get('blocked') and 'Price assumptions are simulation only' not in r['blockers']]
    suppliers=[r for r in report['purchaseOrders'] if all(isinstance(r.get(k),(int,float)) and not isinstance(r.get(k),bool) and math.isfinite(r[k]) and r[k]>=0 for k in ('value','unitCost','ordered','delivered')) and (r['currency']==report['summary']['currency'] or r.get('fx') and r.get('budgetCurrency')==report['summary']['currency'])]
    included_ids={r['id'] for r in included}
    purchase=round(sum(r['orderCost'] for r in included),2)
    turnover=round(sum(r['orderTurnover'] for r in included),2)
    margin=round(sum(r['orderGrossMargin'] for r in included),2)
    commitments=round(sum(r['value'] for r in suppliers),2)
    return dict(rowIds=[r['id'] for r in included],supplierOrders=suppliers,
        recommendationCount=len(included),excludedRecommendations=sum(r['quantity'] is None or r['quantity']>0 for r in rows)-len(included),
        supplierLines=len(suppliers),excludedSupplierLines=len(report['purchaseOrders'])-len(suppliers)+report.get('unallocatedSupplierLines',0),
        purchaseCost=purchase,turnover=turnover,grossMargin=margin,marginRate=margin/turnover*100 if turnover else None,
        commitments=commitments,balanceAfterCovered=round(report['summary']['seasonBudget']-commitments-purchase,2),
        fullPlanComplete=report['summary']['commitmentsComplete'] and all(r['quantity']==0 or r['id'] in included_ids for r in rows))

def article_plan(rows, report):
    """Whole-article, deterministic margin-return ranking; not an optimal solver."""
    grouped={}
    for row in rows:grouped.setdefault(row['reference'],[]).append(row)
    articles=[]
    for reference,variants in grouped.items():
        active=[r for r in variants if r['quantity'] is None or r['quantity']>0]
        complete=bool(active) and all(r['orderCost'] is not None and r['orderTurnover'] is not None and r['orderMarginRate'] is not None for r in active)
        cost=round(sum(r['orderCost'] or 0 for r in active),2) if complete else None
        turnover=round(sum(r['orderTurnover'] or 0 for r in active),2) if complete else None
        margin=round(sum(r['orderGrossMargin'] or 0 for r in active),2) if complete else None
        rate=margin/turnover*100 if turnover else None
        articles.append(dict(reference=reference,activity=variants[0].get('activity'),rowIds=[r['id'] for r in variants],forecast=sum(r['forecast'] for r in variants),
            quantity=sum(r['quantity'] or 0 for r in active),purchaseCost=cost,turnover=turnover,grossMargin=margin,marginRate=rate,
            quantityUnresolved=any(r['quantity'] is None for r in variants),
            inactiveConflict=any(r.get('purchasingBlocked') and (r['quantity'] is None or r['quantity']>0) for r in variants),
            inactiveOnly=all(r.get('purchasingBlocked') for r in variants),status='waiting',reason='',rank=None,shortfall=None))
    s=report['summary'];capacity=round(s['seasonBudget']-s['knownCommittedCost'],2);remaining=capacity
    ranked=sorted(articles,key=lambda a:(-(a['grossMargin']/a['purchaseCost'] if a['purchaseCost'] and a['grossMargin'] is not None else -1),-a['forecast'],a['reference']))
    for rank,a in enumerate(ranked,1):
        a['rank']=rank
        if a['inactiveConflict'] or a['inactiveOnly']:
            a.update(status='inactive',reason='Inactive catalogue article/SKU: new purchasing is blocked. Set inactive variant quantities to zero or change their status in Catalogue. Demand history remains visible.')
        elif a['quantityUnresolved']:
            a.update(status='waiting',reason='Order quantity is unresolved. Enter whole-unit quantities before allocating this article.')
        elif not a['quantity']:
            a.update(status='zero',reason='No positive order quantity in this draft.')
        elif a['purchaseCost'] is None:
            a.update(status='waiting',reason='Enter purchase and selling prices for every ordered size to calculate this whole article. Missing values are excluded from budget allocation.')
        elif not s['budgetConfigured']:
            a.update(status='waiting',reason='Save a buying budget before allocating articles.')
        elif a['marginRate']<s['targetMargin']:
            a.update(status='margin',reason=f"Expected margin {a['marginRate']:.1f}% is below the {s['targetMargin']:.1f}% target. Adjust prices or assumptions.")
        elif a['purchaseCost']>remaining:
            a.update(status='budget',shortfall=round(a['purchaseCost']-remaining,2),reason=f"Whole-article cost {a['purchaseCost']:.2f} exceeds the remaining draft allowance {remaining:.2f}. Higher margin-return articles were considered first; reduce quantities or increase the budget.")
        else:
            remaining=round(remaining-a['purchaseCost'],2)
            a.update(status='included',reason=f"Expected margin {a['marginRate']:.1f}% meets the {s['targetMargin']:.1f}% target and all ordered sizes fit the draft allowance. Priority {rank} by gross margin per purchase cost, then forecast demand.")
    articles.sort(key=lambda a:bool((a.get('activity') or {}).get('dormant')))
    included=[a for a in articles if a['status']=='included']
    return dict(articles=articles,capacity=capacity,remaining=remaining,purchaseCost=round(sum(a['purchaseCost'] for a in included),2),
        turnover=round(sum(a['turnover'] for a in included),2),grossMargin=round(sum(a['grossMargin'] for a in included),2),
        provisional=not s['commitmentsComplete'],method='Whole articles ranked by gross margin per purchase cost, then forecast demand; no partial size allocation.')

def simulate(report, edits=None, quantity_basis='net', saved_inputs=None, price_reviews=None):
    if quantity_basis not in ('net','forecast'):raise ValueError('Unknown quantity basis.')
    edits=edits or []
    if not isinstance(edits,list) or len(edits)>100000:raise ValueError('Invalid simulation rows.')
    available={identity(r):r for r in report['rows']};overrides={}
    for edit in edits:
        if not isinstance(edit,dict) or edit.get('id') not in available:raise ValueError('A simulation variant is outside the saved scope.')
        if edit['id'] in overrides:raise ValueError('Duplicate simulation variant.')
        if set(edit)-{'id','quantity','unitCost','unitPrice','sellThrough','quoteId','supplier','reason','assortmentReviewed'}:raise ValueError('Unsupported simulation assumption.')
        if any(not isinstance(edit.get(k,''),str) for k in ('quoteId','supplier')):raise ValueError('Select a valid supplier price.')
        if 'assortmentReviewed' in edit and type(edit['assortmentReviewed']) is not bool:raise ValueError('Assortment review must be true or false.')
        for field in ('quantity','unitCost','unitPrice','sellThrough'):
            if field in edit:
                if edit[field] is None and field in ('quantity','unitCost','unitPrice'):continue
                v=b.numeric(edit[field])
                if v is None or v>1e9:raise ValueError('Simulation values must be finite and nonnegative.')
                if field=='quantity' and v!=int(v):raise ValueError('Order quantities must be whole units.')
                if field=='sellThrough' and v>100:raise ValueError('Sell-through must be between 0 and 100%.')
                edit=dict(edit);edit[field]=v
        if not isinstance(edit.get('reason',''),str) or len(edit.get('reason',''))>1000:raise ValueError('Enter a shorter assumption reason.')
        overrides[edit['id']]=edit
    quotes=supplier_quotes(report)
    revision=hashlib.sha256(json.dumps(dict(pricePolicy='supplier-price-review-v1',quantityBasis=quantity_basis,source=report['source']['revision'],scenario=report['scenario'],season=report['season'],settings=report['settings'],rows=report['rows'],orders=report['purchaseOrders']),sort_keys=True).encode()).hexdigest()
    suppliers=set(report.get('supplierOptions',[]))|{r.get('catalogueSupplier','') for r in report['rows']}|{q['supplier'] for offered in quotes.values() for q in offered}
    rows=[]
    for k,r in available.items():
        edit=overrides.get(k,{})
        snapshot=(saved_inputs or {}).get(k,{})
        offered=quotes.get(k,[])
        quote=next((p for p in offered if quote_matches(p,edit.get('quoteId'))),None)
        if edit.get('quoteId') and quote is None:raise ValueError('Supplier price changed. Reload the simulation.')
        supplier=quote['supplier'] if quote else edit.get('supplier','')
        if supplier and supplier not in suppliers:raise ValueError('Select a supplier from the saved Joolan data.')
        default_quantity=snapshot.get('quantity',r['forecast'] if quantity_basis=='forecast' else r['purchaseQuantity'])
        from order_constraints import propose,violations
        rules=r.get('orderingRules',{})
        qty=edit.get('quantity',default_quantity if 'quantity' in snapshot else propose(default_quantity,rules))
        fallback=offered[0]['unitCost'] if not r.get('catalogueCostAvailable') and offered and len({p['unitCost'] for p in offered})==1 else None
        same_quote=bool(quote and quote_matches(quote,snapshot.get('quoteId')))
        cost=edit.get('unitCost',quote['unitCost'] if quote and not same_quote else snapshot.get('cost',quote['unitCost'] if quote else r['unitCost'] if r['unitCost'] is not None else fallback))
        price=edit.get('unitPrice',snapshot.get('price',r['unitPrice']));sell=edit.get('sellThrough',snapshot.get('sellThrough',100))
        purchase=b.amount(qty,cost);sold=None if qty is None else qty*sell/100
        turnover=b.amount(sold,price);cogs=b.amount(sold,cost)
        margin=round(turnover-cogs,2) if turnover is not None and cogs is not None else None
        rate=margin/turnover*100 if margin is not None and turnover else None
        blockers=[]
        blockers.extend(violations(qty,rules))
        expected_receipt=None
        if qty and rules.get('leadTimeDays') is not None:
            expected_receipt=(dt.datetime.now(dt.timezone.utc).date()+dt.timedelta(days=rules['leadTimeDays'])).isoformat()
            if r.get('needBy') and expected_receipt>r['needBy']:blockers.append('Supplier lead time misses the next recorded customer delivery')
        if qty and r.get('requiresAssortmentReview') and not edit.get('assortmentReviewed'):blockers.append('Launch/assortment estimate requires planner review')
        if qty and r.get('requiresDeliveryReview'):blockers.append('Customer delivery commitments need reconciliation')
        if qty is None:blockers.append('Purchase quantity unresolved')
        if qty and (r['stock'] is None or r['incoming'] is None):blockers.append('Stock or incoming supply unresolved')
        if qty and cost is None:blockers.append('Purchase cost missing')
        if qty and price is None:blockers.append('Selling price missing')
        reviewed_values=dict(id=k,supplier=supplier,quoteId=quote['id'] if quote else '',orderUnitCost=cost,orderUnitPrice=price)
        from price_review import fingerprint
        price_fingerprint=fingerprint(revision,report['summary']['currency'],reviewed_values)
        price_review=(price_reviews or {}).get(price_fingerprint)
        assumptions=bool(any(n in edit for n in ('unitCost','unitPrice')) or price!=r['unitPrice'] or not quote or
            (quote and (cost!=quote['unitCost'] or quote.get('requiresReview'))) or r.get('catalogueSellingManual'))
        if qty and not supplier:blockers.append('Select a Joolan supplier price')
        if qty and assumptions and (supplier or any(n in edit for n in ('unitCost','unitPrice')) or r.get('catalogueSellingManual')) and not price_review:blockers.append('Price assumptions are simulation only')
        if qty and rate is None:blockers.append('Margin rate unavailable')
        if qty and rate is not None and rate<report['summary']['targetMargin']:blockers.append('Below margin target')
        changed=bool(edit)
        if changed and not edit.get('reason','').strip() and (not price_review or any(n in edit for n in ('quantity','sellThrough','assortmentReviewed'))):blockers.append('Explain the adjustment')
        rows.append(dict(**r,id=k,quantity=qty,orderUnitCost=cost,orderUnitPrice=price,sellThrough=sell,expectedSold=sold,
            earliestReceiptDate=expected_receipt,
            assortmentReviewed=bool(edit.get('assortmentReviewed')),
            supplier=supplier,priceReviewRequired=assumptions,priceReview=price_review,priceReviewFingerprint=price_fingerprint,
            orderCost=purchase,orderTurnover=turnover,orderGrossMargin=margin,orderMarginRate=rate,
            quotes=offered,quoteId=quote['id'] if quote else '',costBasis='Edited simulation price' if 'unitCost' in edit else 'Saved budget snapshot' if 'cost' in snapshot else 'Supplier order price' if quote else r.get('unitCostSource','SKU purchase-price estimate') if r['unitCost'] is not None else 'Recorded supplier price estimate' if fallback is not None else 'Purchase price required',priceBasis='Saved budget snapshot' if 'price' in snapshot and 'unitPrice' not in edit else r.get('unitPriceSource','Customer order price unavailable'),
            reason=edit.get('reason',''),adjusted=changed,blockers=list(dict.fromkeys(blockers))))
    from order_constraints import article_violations
    article_blocks=article_violations(rows)
    for row in rows:
        if row['reference'] in article_blocks:row['blockers'].append(article_blocks[row['reference']])
    active=[r for r in rows if r['quantity'] is None or r['quantity']>0]
    complete=bool(active) and all(r['orderCost'] is not None for r in active)
    revenue_complete=bool(active) and all(r['orderTurnover'] is not None and r['orderGrossMargin'] is not None for r in active)
    cost=round(sum(r['orderCost'] or 0 for r in active),2)
    turnover=round(sum(r['orderTurnover'] or 0 for r in active),2)
    margin=round(sum(r['orderGrossMargin'] or 0 for r in active),2)
    commitments=report['summary']['knownCommittedCost'];budget=report['summary']['seasonBudget']
    global_blocks=[]
    if not report['summary']['budgetConfigured']:global_blocks.append('Save a buying budget')
    if not report['summary']['commitmentsComplete']:global_blocks.append('Existing supplier commitments are incomplete')
    if not complete:global_blocks.append('Some proposed orders have unresolved purchase values')
    if not revenue_complete:global_blocks.append('Some proposed orders have unresolved turnover or margin')
    if revenue_complete and turnover and margin/turnover*100<report['summary']['targetMargin']:global_blocks.append('Plan gross margin is below target')
    if cost+commitments>budget:global_blocks.append('Buying budget exceeded')
    return dict(rows=rows,articlePlan=article_plan(rows,report),quantityBasis=quantity_basis,covered=covered_data(rows,report),context=report,revision=revision,scenario=report['scenario'],currency=report['summary']['currency'],
        summary=dict(knownOrderCost=cost,totalOrderCost=cost if complete else None,knownTurnover=turnover,turnover=turnover if revenue_complete else None,
            grossMargin=margin if revenue_complete else None,marginRate=margin/turnover*100 if revenue_complete and turnover else None,
            knownCommitments=commitments,commitmentsComplete=report['summary']['commitmentsComplete'],budget=budget,targetMargin=report['summary']['targetMargin'],
            provisionalBalance=round(budget-commitments-cost,2),balance=round(budget-commitments-cost,2) if complete and report['summary']['commitmentsComplete'] else None,
            overBudget=cost+commitments>budget,ready=sum(not r['blockers'] for r in active),orders=len(active)),blockers=global_blocks)

def validate(conn,report,edits,selected,revision,quantity_basis='net',commit=True,saved_inputs=None,price_reviews=None):
    result=simulate(report,edits,quantity_basis,saved_inputs,price_reviews)
    if revision!=result['revision']:raise ValueError('Source, settings or forecast changed. Recalculate before validating.')
    if not isinstance(selected,list) or not selected or len(set(selected))!=len(selected):raise ValueError('Select orders to validate.')
    rows={r['id']:r for r in result['rows']}
    if any(k not in rows or not rows[k]['quantity'] for k in selected):raise ValueError('Select valid positive-quantity orders.')
    from order_constraints import article_violations
    selected_article_blocks=article_violations([rows[k] for k in selected])
    if selected_article_blocks:raise ValueError('; '.join(selected_article_blocks.values()))
    blocked=result['blockers']+[f"{rows[k]['reference']} / {rows[k]['size']}: {', '.join(rows[k]['blockers'])}" for k in selected if rows[k]['blockers']]
    if blocked:raise ValueError('Validation blocked: '+'; '.join(blocked[:8]))
    record=dict(id=uuid.uuid4().hex,createdAt=dt.datetime.now(dt.timezone.utc).isoformat(),seasonId=report['season']['id'],
        sourceRun=report['source']['runId'],revision=revision,scenario=result['scenario'],status='financially_reviewed',currency=result['currency'],
        summary=result['summary'],orders=[rows[k] for k in selected],notice='Local financial review only. No purchase order was sent to Joolan.')
    from contextlib import nullcontext
    with conn if commit else nullcontext():conn.execute('INSERT INTO planning_state VALUES(?,?)',('buying_review:'+record['id'],json.dumps(record)))
    return record
