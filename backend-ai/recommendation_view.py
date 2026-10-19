"""Keep demand forecasts, unresolved purchase quantities and edits distinct."""
def purchase_total(rows,field='final_quantity'):
    return round(sum(r[field] for r in rows),4) if all(r[field] is not None for r in rows) else None

def size_breakdown(rows,sort_key):
    return [dict(size=r['taille'],forecast=r.get('demand_forecast',0),recommended=r['recommended_quantity'],manualOverride=r['manual_override'],
        finalQty=r['final_quantity'],minUnits=None,maxUnits=None,blocked=bool(r.get('purchasing_blocked')),statusReason=r.get('status_reason',''),rounding=None) for r in sorted(rows,key=lambda r:sort_key(r['taille']))]

def validate_edits(rows,body):
    import math
    sizes=body.get('sizeBreakdown')
    if not isinstance(sizes,list) or not sizes:raise ValueError('Enter at least one size quantity.')
    allowed={r['taille'] for r in rows};seen=set();result=[]
    for edit in sizes:
        if not isinstance(edit,dict) or edit.get('size') not in allowed:raise ValueError('Unknown product size.')
        size=edit['size']
        if size in seen:raise ValueError('Duplicate product size.')
        seen.add(size)
        value=edit.get('finalQty')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('Quantity must be finite and nonnegative.')
        result.append((size,value))
    return result
