"""Article-level baseline challengers with coherent colour/size allocation."""
from collections import defaultdict
import numpy as np
import pandas as pd


def shares(histories,keys,end):
    totals={}
    for key in keys:
        months,values=histories[key]
        recent=values[(months<=end)&(months>end-12)]
        totals[key]=float(recent.sum())
    if not sum(totals.values()):
        # Iterate this article only. Scanning the complete assortment for each
        # dormant article makes full-universe validation grow quadratically.
        totals={k:float(histories[k][1][histories[k][0]<=end].sum()) for k in keys}
    denominator=sum(totals.values())
    return {k:v/denominator if denominator else 0. for k,v in totals.items()}


def article_values(histories,keys,end):
    first=min(histories[k][0].min() for k in keys)
    months=pd.period_range(first,end,freq='M');values=np.zeros(len(months))
    for key in keys:
        m,v=histories[key];mask=m<=end
        values[(m[mask].asi8-months[0].ordinal).astype(int)]+=v[mask]
    return values


def select_challengers(histories,validation_end,horizon,selected,residuals,selection,baseline,methods):
    grouped=defaultdict(list);winners={}
    for key in histories:grouped[key[0]].append(key)
    records={tuple(str(row[k]) for k in ('Reference','Couleur','Taille')):row for row in selection}
    for reference,keys in grouped.items():
        if len(keys)<2 or any(records[k]['validation_points']!=horizon for k in keys):continue
        weight=shares(histories,keys,validation_end)
        if not sum(weight.values()):continue
        article=article_values(histories,keys,validation_end)
        actual={k:histories[k][1][histories[k][0]>validation_end] for k in keys}
        scores={method:sum(float(np.abs(actual[k]-baseline(article,horizon,method)*weight[k]).sum()) for k in keys) for method in methods}
        method=min(scores,key=scores.get)
        independent=sum(records[k]['validation_absolute_error'] for k in keys)
        # Require a meaningful holdout improvement over independently chosen sizes.
        if independent<=0 or scores[method]>=independent*.95:continue
        predicted=baseline(article,horizon,method)
        for key in keys:
            selected[key]='article_'+method;residuals[key]=actual[key]-predicted*weight[key]
            records[key].update(selected_model=selected[key],validation_absolute_error=float(np.abs(residuals[key]).sum()),
                hierarchy='article_to_colour_to_size',article_holdout_gain=1-scores[method]/independent)
        winners[reference]=dict(method=method,keys=keys)
    return winners


def predict_challengers(histories,winners,cutoff,horizon,baseline):
    result={}
    for reference,winner in winners.items():
        values=baseline(article_values(histories,winner['keys'],cutoff),horizon,winner['method'])
        for key,weight in shares(histories,winner['keys'],cutoff).items():result[key]=values*weight
    return result
