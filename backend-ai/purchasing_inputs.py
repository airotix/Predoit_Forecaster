"""A paginated explanation of unresolved source inputs, not synthetic fixes."""
import buying


def view(simulation,issue='all',search='',offset=0,limit=25):
    allowed={'all','purchase','selling','stock','incoming','delivery'}
    if issue not in allowed:raise ValueError('Select a supported purchasing input filter.')
    rows=[];summary={k:0 for k in allowed if k!='all'}
    for row in simulation['rows']:
        issues={}
        for name,key in [('purchase','unitCost'),('selling','unitPrice'),('stock','stock'),('incoming','incoming')]:
            if row[key] is None:issues[name]=(row.get('inputIssues') or {}).get(name) or 'No usable source value. Missing is not zero.'
        if row.get('requiresDeliveryReview'):issues['delivery']=(row.get('inputIssues') or {}).get('delivery') or 'Customer delivery commitments need reconciliation.'
        for name in issues:summary[name]+=1
        if not issues:continue
        detail=row.get('purchasePriceDetails') or {}
        rows.append(dict(id=row['id'],reference=row['reference'],name=row['name'],color=row['color'],size=row['size'],
            quantity=row['quantity'],inactive=bool(row.get('purchasingBlocked')),issues=issues,
            reasonCode=detail.get('reasonCode'),purchaseCost=row['unitCost'],draftPurchaseCost=row['orderUnitCost'],
            priceReview=row.get('priceReview'),candidates=[q for q in row['quotes'] if q.get('requiresReview')],
            otherCurrencyCandidates=detail.get('otherCurrencyCandidates',[])))
    total_issues=len(rows)
    terms=search.strip().casefold()
    filtered=[r for r in rows if (issue=='all' or issue in r['issues']) and (not terms or terms in ' '.join([r['reference'],r['name'],r['color'],r['size']]).casefold())]
    return dict(summary=summary,affectedVariants=total_issues,budgetVariants=len(simulation['rows']),total=len(filtered),
        rows=filtered[offset:offset+limit],offset=offset,limit=limit,currency=simulation['currency'],
        source=simulation['context']['source'],fxPolicy=simulation['context'].get('fxPolicy',{}),
        supplierExceptionCount=simulation['context'].get('unallocatedSupplierLines',0),
        notice='Counts describe current Catalogue and source inputs, including inactive/zero-quantity variants. Saved Budget draft price overrides are shown separately. No missing stock, dates, quantities or prices are assumed to be zero.')
