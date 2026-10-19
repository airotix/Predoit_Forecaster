"""Published demand and inventory, preserving unknowns and actual size labels."""
from collections import defaultdict
from fastapi import HTTPException
from planning import SCENARIOS


def total(values):
    values = list(values)
    return round(sum(values), 4) if values and all(v is not None for v in values) else None


def detail(conn, reference, scenario='base'):
    if scenario not in SCENARIOS:
        raise HTTPException(400, 'Unknown scenario.')
    cursor = conn.execute('SELECT * FROM recommendations WHERE reference=? ORDER BY couleur,taille', (reference,))
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, r)) for r in cursor]
    if not rows:
        raise HTTPException(404, 'Article not found in the published forecast.')
    first = rows[0]
    season_basis=any(r.get('season_booked') is not None for r in rows)
    fields = dict(totalDeProduit='season_booked' if season_basis else 'confirmed_orders', recommendedQty='forecast_'+scenario,
                  totalDeFournisseur='pipeline_stock', totalDeCitNegoce='confirmed_delivered',
                  totalDeLeStock='net_to_order_'+scenario, availableStock='current_stock')
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[row['couleur'] or 'Unknown'][str(row['taille'] or 'Unknown')].append(row)
    variants = [dict(color=color, **{
        label: {size: total(r.get(column) for r in records) for size, records in sizes.items()}
        for label, column in fields.items()}) for color, sizes in grouped.items()]
    stock = total(r.get('current_stock') for r in rows)
    incoming = total(r.get('pipeline_stock') for r in rows)
    return dict(skuId='SKU-'+reference, skuName=first.get('designation') or reference,
        projectionBasis='season_bookings' if season_basis else 'legacy_open_balances',
        category=first.get('famille') or 'Unknown', scenario=scenario,
        productInfo=dict(reference=reference, name=first.get('designation') or reference,
            matiere=first.get('matiere') or '', theme=first.get('theme') or '',
            famille=first.get('famille') or '', sousFamille=first.get('modele') or '',
            rayon=first.get('rayon') or '', saison=first.get('saison') or ''),
        stockSummary=dict(stockReel=stock, fournisseur=incoming,
            clientNegoce=total(r.get('confirmed_delivered') for r in rows),
            total=total([stock, incoming])),
        colorVariants=variants,
        confidence='low' if any(str(r.get('confidence','')).upper() not in ('HIGH','MEDIUM') for r in rows) else 'medium' if any(str(r.get('confidence','')).upper()=='MEDIUM' for r in rows) else 'high')
