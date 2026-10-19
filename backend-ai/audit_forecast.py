"""Read-only audit of published results and nested, full-universe backtests."""
import datetime as dt
import json
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd
from forecasting import forecast, baseline, calendar_series, metrics, KEYS

BASE = Path(__file__).resolve().parent
OUT = BASE / 'output' / 'accuracy-audit'

def score(frame):
    result = metrics(frame.actual, frame.forecast_base)
    result['forecastUnits'] = float(frame.forecast_base.sum())
    return result

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    from database import DB_FILE
    conn = sqlite3.connect(Path(DB_FILE).resolve().as_uri() + '?mode=ro', uri=True)
    lineage = json.loads(conn.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()[0])
    monthly = pd.read_sql_query('SELECT reference AS Reference,couleur AS Couleur,taille AS Taille,year_month,true_demand FROM historical_demand', conn)
    published = pd.read_sql_query('SELECT reference AS Reference,couleur AS Couleur,taille AS Taille,forecast_month,forecast_base,forecast_conservative,forecast_optimistic,model_type FROM forecast_monthly', conn)
    missing = conn.execute('SELECT COUNT(*),SUM(unit_selling_price IS NULL),SUM(unit_purchase_cost IS NULL),SUM(current_stock IS NULL),SUM(pipeline_stock IS NULL) FROM recommendations').fetchone()
    conn.close()
    monthly['year_month'] = pd.PeriodIndex(monthly.year_month, freq='M')
    cutoff = pd.Period(lineage['cutoff'], freq='M')
    monthly = monthly[monthly.year_month <= cutoff].copy()
    for k in KEYS:
        monthly[k] = monthly[k].astype(str)
        published[k] = published[k].astype(str)
    published.forecast_month = pd.PeriodIndex(published.forecast_month, freq='M')
    selection = pd.read_csv(Path(lineage['outputDirectory'])/'model_selection.csv', dtype={k:str for k in KEYS})
    eligible = selection[selection.validation_points > 0]
    val_actual = monthly[monthly.year_month > cutoff-6].merge(eligible[KEYS], on=KEYS).true_demand.sum()
    totals = published.groupby('forecast_month').forecast_base.sum()
    history_totals = monthly.groupby('year_month').true_demand.sum()
    variants = published.groupby(KEYS).forecast_base.sum()
    report = dict(createdAt=dt.datetime.now(dt.timezone.utc).isoformat(),runId=lineage['runId'],lineage=lineage,
        limitations=['Retrospective test on the current revised order snapshot, not archived as-of snapshots.',
            'CSV demand is delivered plus remaining; newer Joolan demand is ordered minus known cancellations. Unknown cancellations and stockouts remain.',
            'Actual October 2026â€“March 2027 outcomes are not yet available. Historical results do not guarantee future accuracy.'],
        published=dict(variants=len(variants),baseUnits=float(variants.sum()),zeroForecastVariants=int((variants==0).sum()),
            modelCounts=selection.selected_model.value_counts().to_dict(),unvalidatedVariants=int((selection.validation_points==0).sum()),
            missingInputs=dict(zip(['rows','price','cost','stock','incoming'],missing)),
            monthly=[dict(month=str(m),units=float(v)) for m,v in totals.items()],
            apparentSelectionWape=float(eligible.validation_absolute_error.sum()/val_actual*100),
            apparentSelectionNote='Optimistic selection-period score: this same period chose the winning model, so it is not independent test accuracy.'),
        historyMonthly=[dict(month=str(m),units=float(v)) for m,v in history_totals.items()],folds=[])
    target=OUT/'report.json'
    def save(): target.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    save()
    print(json.dumps(report['published']),flush=True)
    for end in (cutoff-18,cutoff-12,cutoff-6):
        label=str(end+1)+'_to_'+str(end+6)
        print('BACKTEST '+label+' training full known universe, 250 iterations',flush=True)
        train=monthly[monthly.year_month<=end].copy()
        pred,chosen=forecast(train,horizon=6,cutoff=end,iterations=250)
        histories,_=calendar_series(train,end)
        naive=[]
        for key,g in pred.groupby(KEYS,sort=False):
            values=histories[tuple(key)][1]
            naive.extend(dict(zip(KEYS,key),forecast_month=m,seasonal_naive=float(p),recent_mean=float(r))
                for m,p,r in zip(g.forecast_month,baseline(values,6,'seasonal_naive'),baseline(values,6,'recent_mean')))
        pred=pred.merge(pd.DataFrame(naive),on=KEYS+['forecast_month'])
        actual=monthly[(monthly.year_month>end)&(monthly.year_month<=end+6)].rename(columns={'year_month':'forecast_month','true_demand':'actual'})
        frame=pred.merge(actual[KEYS+['forecast_month','actual']],on=KEYS+['forecast_month'],how='outer',indicator=True)
        unknown=frame['_merge'].eq('right_only')
        new_units=float(frame.loc[unknown,'actual'].sum())
        frame['new_at_origin']=unknown
        for k in ('actual','forecast_base','forecast_conservative','forecast_optimistic','seasonal_naive','recent_mean'):
            frame[k]=frame[k].fillna(0.)
        known=frame[~unknown]
        positive=frame[frame.actual>0]
        aggregate=frame.groupby('forecast_month')[['actual','forecast_base','seasonal_naive','recent_mean']].sum().reset_index()
        ref=frame.groupby(['Reference','forecast_month'])[['actual','forecast_base']].sum().reset_index()
        season=frame.groupby(KEYS)[['actual','forecast_base']].sum().reset_index()
        active_keys=train[train.year_month>end-12][KEYS].drop_duplicates()
        active=frame.merge(active_keys,on=KEYS)
        volume=train[train.year_month>end-12].groupby(KEYS).true_demand.sum().sort_values(ascending=False)
        top=volume[volume.cumsum().shift(fill_value=0)<volume.sum()*.8].reset_index()[KEYS]
        top_frame=frame.merge(top,on=KEYS)
        result=dict(trainEnd=str(end),testStart=str(end+1),testEnd=str(end+6),knownSeries=len(chosen),
            allVariantMonths=score(frame),knownVariantMonths=score(known),positiveActualMonths=score(positive),
            activePrior12Months=score(active),topPriorVolume80Percent=score(top_frame),referenceMonths=score(ref),
            sixMonthVariantTotals=score(season),brandMonths=score(aggregate),
            seasonalNaive=metrics(frame.actual,frame.seasonal_naive),recentMean=metrics(frame.actual,frame.recent_mean),
            missingNewProductUnits=new_units,missingNewProductShare=float(new_units/frame.actual.sum()*100),
            bandCoverage=float(((known.actual>=known.forecast_conservative)&(known.actual<=known.forecast_optimistic)).mean()*100),
            positiveActualBandCoverage=float(((positive.actual>=positive.forecast_conservative)&(positive.actual<=positive.forecast_optimistic)).mean()*100),
            zeroActualMonthShare=float((frame.actual==0).mean()*100),models=chosen.selected_model.value_counts().to_dict(),
            monthly=[dict(month=str(r.forecast_month),actual=float(r.actual),forecast=float(r.forecast_base),seasonalNaive=float(r.seasonal_naive)) for r in aggregate.itertuples()])
        frame.assign(forecast_month=frame.forecast_month.astype(str)).drop(columns='_merge').to_csv(OUT/(label+'.csv'),index=False)
        report['folds'].append(result);save()
        print(json.dumps(result),flush=True)
    print('SAVED '+str(target),flush=True)

if __name__=='__main__':main()
