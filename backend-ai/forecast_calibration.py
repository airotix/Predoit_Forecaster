"""Ranges from earlier held-out predictions, never selection-window residuals."""
from collections import defaultdict
import numpy as np
from article_forecast import predict_challengers


def calibration(histories,cutoff,horizon,selected,winners,baseline,fit,predict,metadata,iterations):
    errors=defaultdict(list);pools=defaultdict(list)
    for fold in (2,3):
        end=cutoff-fold*horizon
        past={k:(m[m<=end],v[m<=end]) for k,(m,v) in histories.items() if (m<=end).sum()>=3}
        if not past:continue
        model=fit(past,end,iterations,metadata) if any(selected[k]=='catboost' for k in past) else None
        cb=predict(model,past,end+1,horizon,metadata) if model is not None else {}
        eligible={ref:w for ref,w in winners.items() if all(k in past for k in w['keys'])}
        hierarchy=predict_challengers(past,eligible,end,horizon,baseline)
        for key,(months,values) in past.items():
            full_m,full_v=histories[key]
            actual=full_v[(full_m>end)&(full_m<=end+horizon)]
            if len(actual)!=horizon:continue
            method=selected[key]
            if method.startswith('article_') and key not in hierarchy:continue
            if method=='catboost' and key not in cb:continue
            prediction=hierarchy[key] if key in hierarchy else cb[key] if method=='catboost' else baseline(values,horizon,method)
            scale=max(1.,float(np.mean(values[-12:])))
            for h,(a,p) in enumerate(zip(actual,prediction),1):
                error=float(a-p);errors[key].append((float(a),float(p),error))
                pools[(method,h)].append(error/scale)
    return errors,pools


def quality(records):
    if not records:return dict(calibration_points=0,calibration_wape=None,calibration_bias=None,confidence='LOW',confidence_reason='No independent calibration predictions.')
    a=np.array([r[0] for r in records]);p=np.array([r[1] for r in records]);denominator=float(a.sum())
    wape=float(np.abs(a-p).sum()/denominator*100) if denominator else None
    bias=float((p-a).sum()/denominator*100) if denominator else None
    supported=len(records)>=6 and wape is not None and wape<=50 and abs(bias)<=25
    return dict(calibration_points=len(records),calibration_wape=wape,calibration_bias=bias,confidence='MEDIUM' if supported else 'LOW',
        confidence_reason='Earlier held-out WAPE <= 50%, absolute bias <= 25%, at least six points; this is an evidence policy, not a probability.' if supported else 'Insufficient positive-demand evidence or earlier held-out errors exceed the evidence policy.')


def summarize_pools(pools):
    return {key:(float(q[0]),float(q[1]),len(values)) for key,values in pools.items() if len(values)>=30 for q in [np.quantile(values,[.1,.9])]}


def bounds(method,h,value,scale,pools,calibration_horizon,summaries=None):
    pool=pools.get((method,h),[]) if h<=calibration_horizon else []
    if len(pool)<30:return 0.,max(value*2,value+1),'UNCALIBRATED',len(pool)
    low,high,_=summaries[(method,h)] if summaries is not None else (*np.quantile(pool,[.1,.9]),len(pool))
    return max(0.,min(value,value+low*scale)),max(value,value+high*scale),'EARLIER_HOLDOUT_RESIDUALS',len(pool)
