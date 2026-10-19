"""Read-only live checks for projection scenarios and the shared purchase draft."""
import json,time,urllib.request

def get(path):
    start=time.monotonic()
    with urllib.request.urlopen('http://127.0.0.1:4000/api/'+path,timeout=300) as response:
        result=json.load(response)
    print(path,round(time.monotonic()-start,2),'seconds',flush=True)
    return result

if __name__=='__main__':
    projections=get('projections')
    chosen=next(p for p in projections if p['scenarios']['base']['total']>0)
    reference=chosen['skuId'].removeprefix('SKU-')
    for scenario in ('conservative','base','optimistic'):
        detail=get('projections/'+reference+'/detail?scenario='+scenario)
        total=sum(v for row in detail['colorVariants'] for v in row['recommendedQty'].values() if v is not None)
        assert abs(total-chosen['scenarios'][scenario]['total'])<.01
        print('Projection',reference,scenario,round(total,4),'stock',detail['stockSummary']['stockReel'],'incoming',detail['stockSummary']['fournisseur'],flush=True)
    result=get('budget/draft?scenario=base')
    assert set(result['context']['settings']['brands'])=={'DAYTONA73','D73','IRON AND RESIN','IRON&RESIN'}
    assert result['context']['settings']['warehouses']==['CENTRAL']
    print('Draft',dict(version=result['draft']['version'],forecastRun=result['draft']['forecastRun'],
        articles=len(result['articlePlan']['articles']),variants=len(result['rows']),selected=len(result['draft']['selected']),
        stockKnown=sum(r['stock'] is not None for r in result['rows']),sellingKnown=sum(r['orderUnitPrice'] is not None for r in result['rows']),
        blockers=result['blockers']),flush=True)
    recommendations=get('recommendations?scenario=base')
    assert all(r.get('draftVersion')==result['draft']['version'] for r in recommendations)
    if result['draft']['version']:
        lookup={r['skuId']:r for r in recommendations}
        for row in result['rows']:
            rec=lookup[row['reference']+'|'+row['color']]
            size=next(s for s in rec['sizeBreakdown'] if s['size']==row['size'])
            assert size['finalQty']==row['quantity']
    print('Shared version verified across',len(recommendations),'article / colour groups. No draft edits were saved.',flush=True)
