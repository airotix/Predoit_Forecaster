"""Calendar-aligned forecasts selected on past-only, multi-step validation.

Every series has explicit zero months after its first observation. Baselines
always cover sparse products; CatBoost must beat them on an unseen interval.
"""
import os
import numpy as np
import pandas as pd

KEYS=['Reference','Couleur','Taille']
BASELINES=('dormant_zero','intermittent','recent_mean','seasonal_blend','seasonal_naive')
PRODUCT_FEATURES=['brand','category','material','collection']
CATEGORICAL=KEYS+PRODUCT_FEATURES
FEATURES=['lag_1','lag_2','lag_3','lag_6','lag_12','mean_3','mean_6','mean_12','nonzero_12','month_sin','month_cos','age']+CATEGORICAL

def calendar_series(monthly,cutoff=None):
    if monthly.empty:raise ValueError('No monthly demand to forecast.')
    data=monthly.copy()
    data['year_month']=pd.PeriodIndex(data['year_month'],freq='M')
    cutoff=pd.Period(cutoff,freq='M') if cutoff is not None else data.year_month.max()
    data=data[data.year_month<=cutoff]
    histories={}
    for key,group in data.groupby(KEYS,dropna=False,sort=True):
        observed=group.groupby('year_month')['true_demand'].sum().sort_index()
        index=pd.period_range(observed.index.min(),cutoff,freq='M')
        values=observed.reindex(index,fill_value=0).to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values<0).any():raise ValueError('Demand must be finite and nonnegative.')
        histories[tuple(str(v) for v in key)]=(index,values)
    if not histories:raise ValueError('No demand before the forecast cutoff.')
    return histories,cutoff

def baseline(values,horizon,method):
    history=list(np.asarray(values,dtype=float))
    mean=float(np.mean(history[-6:])) if history else 0
    if method=='dormant_zero':return np.zeros(horizon)
    if method=='intermittent':
        # TSB updates occurrence probability even in zero months, so discontinued
        # products decay instead of retaining a perpetual historical mean.
        probability=0.;size=0.
        for value in history:
            probability=.8*probability+.2*float(value>0)
            if value>0:size=value if size==0 else .8*size+.2*value
        return np.repeat(probability*size,horizon)
    # Keep the recent level fixed; do not invent future observations.
    result=[]
    for i in range(horizon):
        seasonal=history[-12] if len(history)>=12 else mean
        value=seasonal if method=='seasonal_naive' else mean if method=='recent_mean' else .65*seasonal+.35*mean
        result.append(max(float(value),0));history.append(result[-1])
    return np.asarray(result)

def feature_row(key,history,month,metadata=None):
    h=np.asarray(history,dtype=float)
    lag=lambda n:float(h[-n]) if len(h)>=n else 0.0
    mean=lambda n:float(h[-n:].mean()) if len(h) else 0.0
    return dict(zip(FEATURES,[lag(1),lag(2),lag(3),lag(6),lag(12),mean(3),mean(6),mean(12),
                              float(np.count_nonzero(h[-12:])),np.sin(2*np.pi*month.month/12),
                              np.cos(2*np.pi*month.month/12),float(len(h)),*key,*[str((metadata or {}).get(key,{}).get(field) or 'UNKNOWN') for field in PRODUCT_FEATURES]]))

def training_frame(histories,end,max_rows=200000,metadata=None):
    frames=[]
    for key,(months,values) in histories.items():
        count=int(np.searchsorted(months,end,side='right'))
        # At most the latest four years per series; deterministic, bounded training.
        indices=np.arange(max(1,count-48),count)
        # Keep recent active history; a dormant series contributes one latest target.
        if count and not np.any(values[max(0,count-24):count]>0):indices=indices[-1:]
        for i in indices:
            row=feature_row(key,values[:i],months[i],metadata);row['target']=values[i];frames.append(row)
    if not frames:return pd.DataFrame()
    frame=pd.DataFrame(frames)
    if len(frame)>max_rows:
        latest=frame.groupby(KEYS,sort=False).tail(1)
        if len(latest)>max_rows:raise ValueError('Training row cap is smaller than the known variant universe.')
        others=frame.drop(latest.index).sample(max_rows-len(latest),random_state=42)
        frame=pd.concat([latest,others]).sort_index()
    return frame

def fit_catboost(histories,end,iterations=250,metadata=None):
    if os.environ.get('FORECASTER_DISABLE_CATBOOST')=='1':return None
    try:
        from catboost import CatBoostRegressor
    except ImportError:return None
    frame=training_frame(histories,end,metadata=metadata)
    if len(frame)<30:return None
    model=CatBoostRegressor(iterations=iterations,depth=6,learning_rate=.06,
        loss_function='MAE',cat_features=CATEGORICAL,random_seed=42,verbose=False,
        thread_count=max(1,min(4,os.cpu_count() or 1)),allow_writing_files=False)
    model.fit(frame[FEATURES],frame.target)
    return model

def recursive_predictions(model,histories,start,horizon,metadata=None):
    working={k:list(v[1]) for k,v in histories.items()}
    predictions={k:[] for k in working}
    keys=list(working)
    for month in pd.period_range(start,periods=horizon,freq='M'):
        matrix=pd.DataFrame([feature_row(k,working[k],month,metadata) for k in keys])[FEATURES]
        values=np.maximum(model.predict(matrix),0)
        for key,value in zip(keys,values):
            predictions[key].append(float(value));working[key].append(float(value))
    return {k:np.asarray(v) for k,v in predictions.items()}

def metrics(actual,predicted):
    actual=np.asarray(actual,dtype=float);predicted=np.asarray(predicted,dtype=float)
    error=predicted-actual
    denominator=float(np.abs(actual).sum())
    return dict(mae=float(np.abs(error).mean()),wape=float(np.abs(error).sum()/denominator*100) if denominator else None,
                bias=float(error.sum()/denominator*100) if denominator else None,n=len(actual),actualUnits=float(actual.sum()))

def forecast(monthly,horizon=6,cutoff=None,start=None,use_catboost=True,iterations=250,use_hierarchy=True,metadata=None,artifact_dir=None):
    histories,cutoff=calendar_series(monthly,cutoff)
    metadata=metadata or {}
    start=pd.Period(start,freq='M') if start is not None else cutoff+1
    if start<=cutoff:raise ValueError('The planning period must start after the last historical month.')
    if not 1<=horizon<=24:raise ValueError('Forecast horizon must be between 1 and 24 months.')
    distance=start.ordinal-cutoff.ordinal-1
    if distance+horizon>36:raise ValueError('Planning period is too far beyond available history. Import recent orders.')
    # Use a common calendar cutoff; short series are handled by baselines.
    val_horizon=6 if max(len(v[1]) for v in histories.values())>=18 else 3
    validation_end=cutoff-val_horizon
    validation_histories={k:(m[m<=validation_end],v[m<=validation_end]) for k,(m,v) in histories.items() if (m<=validation_end).sum()>=3}
    validation_model=fit_catboost(validation_histories,validation_end,iterations,metadata) if use_catboost and validation_histories else None
    validation_cb=recursive_predictions(validation_model,validation_histories,validation_end+1,val_horizon,metadata) if validation_model is not None else {}
    selected={};residuals={};selection=[]
    for key,(months,values) in histories.items():
        cut=int(np.searchsorted(months,validation_end,side='right'))
        scores={};errors={}
        if cut>=3 and len(values)-cut==val_horizon:
            actual=values[cut:]
            for method in BASELINES:
                pred=baseline(values[:cut],val_horizon,method)
                scores[method]=float(np.abs(actual-pred).sum());errors[method]=actual-pred
            if key in validation_cb:
                scores['catboost']=float(np.abs(actual-validation_cb[key]).sum());errors['catboost']=actual-validation_cb[key]
        winner=min(scores,key=scores.get) if scores else 'recent_mean'
        # Do not substitute the pooled model for a baseline unless it actually wins.
        selected[key]=winner;residuals[key]=errors.get(winner,np.asarray([]))
        selection.append(dict(zip(KEYS,key),selected_model=winner,validation_points=val_horizon if scores else 0,
                              validation_absolute_error=scores.get(winner),baseline_absolute_error=min((v for k,v in scores.items() if k!='catboost'),default=None)))
    from article_forecast import select_challengers,predict_challengers
    winners=select_challengers(histories,validation_end,val_horizon,selected,residuals,selection,baseline,BASELINES) if use_hierarchy else {}
    article_predictions=predict_challengers(histories,winners,cutoff,distance+horizon,baseline)
    final_model=fit_catboost(histories,cutoff,iterations,metadata) if 'catboost' in selected.values() else None
    cb=recursive_predictions(final_model,histories,cutoff+1,distance+horizon,metadata) if final_model is not None else {}
    from forecast_calibration import calibration,quality,bounds,summarize_pools
    calibration_errors,pools=calibration(histories,cutoff,val_horizon,selected,winners,baseline,fit_catboost,recursive_predictions,metadata,iterations)
    pool_summaries=summarize_pools(pools)
    for record in selection:
        key=tuple(str(record[k]) for k in KEYS)
        record.update(quality(calibration_errors.get(key,[])))
        record['validation_start']=str(validation_end+1);record['validation_end']=str(cutoff)
        record['interval_target']='Monthly 10th/90th residual scenarios; season sums are not calibrated intervals.'
    if artifact_dir is not None:
        from pathlib import Path
        import json
        directory=Path(artifact_dir);directory.mkdir(parents=True,exist_ok=True)
        if final_model is not None:final_model.save_model(str(directory/'catboost.cbm'))
        (directory/'feature_contract.json').write_text(json.dumps(dict(features=FEATURES,categorical=CATEGORICAL,iterations=iterations,loss='MAE',
            cutoff=str(cutoff),hierarchicalArticles=len(winners),calibrationPools=[dict(model=m,horizon=h,samples=len(v),q10=float(np.quantile(v,.1)),q90=float(np.quantile(v,.9))) for (m,h),v in pools.items()]),indent=2),encoding='utf-8')
    output=[]
    for key,(months,values) in histories.items():
        method=selected[key]
        predictions=article_predictions[key] if key in article_predictions else cb[key] if method=='catboost' and key in cb else baseline(values,distance+horizon,method if method in BASELINES else 'recent_mean')
        scale=max(1.,float(np.mean(values[-12:])))
        for step,(month,value) in enumerate(zip(pd.period_range(start,periods=horizon,freq='M'),predictions[distance:]),distance+1):
            low,high,interval_method,samples=bounds(method,step,value,scale,pools,val_horizon,pool_summaries)
            output.append(dict(zip(KEYS,key),forecast_month=month,
                forecast_conservative=round(low,4),forecast_base=round(max(value,0),4),
                forecast_optimistic=round(high,4),model_type=method.upper(),interval_method=interval_method,interval_samples=samples))
    return pd.DataFrame(output),pd.DataFrame(selection)

def rolling_backtest(monthly,horizon=6,folds=3,use_catboost=True,iterations=150):
    """Independent outer folds over all known and newly observed test variants.

    Missing predictions count as zero for scoring and remain explicitly counted.
    These revised-history tests do not claim point-in-time ERP snapshot fidelity.
    """
    monthly=monthly.copy();monthly['year_month']=pd.PeriodIndex(monthly.year_month,freq='M')
    for field in KEYS:monthly[field]=monthly[field].astype(str)
    _,last=calendar_series(monthly)
    first=monthly.year_month.min();results=[]
    for fold in range(folds,0,-1):
        end=last-fold*horizon
        if end.ordinal-first.ordinal<11:continue
        train=monthly[monthly.year_month<=end].copy()
        if train.empty:continue
        features=[field for field in PRODUCT_FEATURES if field in train]
        facts=train.sort_values('year_month').drop_duplicates(KEYS,keep='last')
        metadata={tuple(str(row[k]) for k in KEYS):{f:row[f] for f in features} for _,row in facts.iterrows()} if features else None
        predictions,_=forecast(train,horizon,cutoff=end,use_catboost=use_catboost,iterations=iterations,metadata=metadata)
        actual=monthly[(monthly.year_month>end)&(monthly.year_month<=end+horizon)]
        actual=actual.groupby(KEYS+['year_month'],as_index=False).true_demand.sum().rename(columns={'year_month':'forecast_month','true_demand':'actual'})
        keys=pd.concat([predictions[KEYS],actual[KEYS]]).drop_duplicates()
        grid=keys.merge(pd.DataFrame({'forecast_month':pd.period_range(end+1,periods=horizon,freq='M')}),how='cross')
        frame=grid.merge(predictions,on=KEYS+['forecast_month'],how='left').merge(actual,on=KEYS+['forecast_month'],how='left')
        frame['missingPrediction']=frame.forecast_base.isna()
        frame['actual']=frame.actual.fillna(0.)
        histories,_=calendar_series(train,end)
        naive=[];recent=[];new=[]
        for key,group in frame.groupby(KEYS,sort=False):
            values=histories.get(tuple(key))
            unseen=values is None
            pred=np.zeros(horizon) if unseen else baseline(values[1],horizon,'seasonal_naive')
            mean=np.zeros(horizon) if unseen else baseline(values[1],horizon,'recent_mean')
            naive.extend(zip(group.index,pred));recent.extend(zip(group.index,mean));new.extend(zip(group.index,[unseen]*horizon))
        frame['seasonal_naive']=pd.Series(dict(naive));frame['recent_mean']=pd.Series(dict(recent));frame['newVariant']=pd.Series(dict(new))
        for col in ('forecast_base','forecast_conservative','forecast_optimistic'):frame[col]=frame[col].fillna(0.)
        article=frame.groupby(['Reference','forecast_month'])[['actual','forecast_base']].sum()
        variant_period=frame.groupby(KEYS)[['actual','forecast_base','seasonal_naive','recent_mean']].sum()
        article_period=frame.groupby('Reference')[['actual','forecast_base','seasonal_naive','recent_mean']].sum()
        totals=frame.groupby('forecast_month')[['actual','forecast_base']].sum()
        known=frame[~frame.newVariant];positive=frame[frame.actual>0]
        def score(f):return metrics(f.actual,f.forecast_base) if len(f) else None
        segments={}
        for field in ('brand','category'):
            if field not in monthly:continue
            facts=monthly.sort_values('year_month').drop_duplicates(KEYS,keep='last')[KEYS+[field]]
            labelled=frame.merge(facts,on=KEYS,how='left');labelled[field]=labelled[field].fillna('UNKNOWN').astype(str)
            segments[field]={label:dict(selected=score(items),seasonalNaive=metrics(items.actual,items.seasonal_naive),
                recentMean=metrics(items.actual,items.recent_mean),missingForecastUnits=float(items.loc[items.missingPrediction,'actual'].sum()),
                newVariantUnits=float(items.loc[items.newVariant,'actual'].sum())) for label,items in labelled.groupby(field)}
        results.append(dict(trainEnd=str(end),testStart=str(end+1),testEnd=str(end+horizon),
            segments=segments,
            selected=score(frame),seasonalNaive=metrics(frame.actual,frame.seasonal_naive),recentMean=metrics(frame.actual,frame.recent_mean),
            zeroDemand=metrics(frame.actual,np.zeros(len(frame))),series=len(keys),knownSeries=len(histories),
            newVariants=int(frame[frame.newVariant][KEYS].drop_duplicates().shape[0]),
            missingForecastUnits=float(frame.loc[frame.missingPrediction,'actual'].sum()),
            newVariantUnits=float(frame.loc[frame.newVariant,'actual'].sum()),
            predictionCoverage=float((~frame.missingPrediction).mean()*100),
            knownVariantMetrics=score(known),positiveDemandMetrics=score(positive),articleMetrics=score(article),totalMonthlyMetrics=score(totals),
            variantPeriodMetrics=score(variant_period),articlePeriodMetrics=score(article_period),
            articlePeriodBaselines=dict(seasonalNaive=metrics(article_period.actual,article_period.seasonal_naive),recentMean=metrics(article_period.actual,article_period.recent_mean)),
            empiricalBandCoverage=float(((frame.actual>=frame.forecast_conservative)&(frame.actual<=frame.forecast_optimistic)).mean()*100),
            positiveDemandBandCoverage=float(((positive.actual>=positive.forecast_conservative)&(positive.actual<=positive.forecast_optimistic)).mean()*100) if len(positive) else None))
    if not results:raise ValueError('Insufficient calendar history for the requested backtest horizon.')
    return results
