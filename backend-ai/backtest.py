"""Read-only, run-identified rolling evaluation of the complete eligible universe."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
import pandas as pd
from forecasting import rolling_backtest,KEYS


def main():
    from database import DB_FILE
    parser=argparse.ArgumentParser()
    source=parser.add_mutually_exclusive_group()
    source.add_argument('--monthly');source.add_argument('--db',default=str(DB_FILE))
    parser.add_argument('--output',required=True)
    parser.add_argument('--series',type=int,default=0,help='0 evaluates the full observed universe; positive values are explicitly sampled diagnostics')
    parser.add_argument('--horizons',nargs='+',type=int,default=[1,3,6])
    parser.add_argument('--folds',type=int,default=3)
    parser.add_argument('--iterations',type=int,default=150)
    parser.add_argument('--no-catboost',action='store_true')
    args=parser.parse_args()
    lineage={}
    if args.monthly:data=pd.read_csv(args.monthly,dtype={k:str for k in KEYS})
    else:
        path=Path(args.db).resolve()
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
            conn.execute('BEGIN') # Keep lineage, history and attached facts in one read snapshot.
            row=conn.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()
            if not row:raise ValueError('The selected database has no published forecast lineage.')
            lineage=json.loads(row[0])
            data=pd.read_sql_query('SELECT reference AS Reference,couleur AS Couleur,taille AS Taille,year_month,true_demand FROM historical_demand',conn)
            facts=pd.read_sql_query('SELECT reference AS Reference,couleur AS Couleur,taille AS Taille,famille AS category,matiere AS material FROM recommendations',conn)
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_skus'").fetchone():
                brands=pd.read_sql_query("SELECT reference AS Reference,color AS Couleur,size AS Taille,MAX(brand) AS brand,MAX(json_extract(details,'$.product.Collection')) AS collection FROM catalogue_skus WHERE current=1 GROUP BY reference,color,size HAVING COUNT(*)=1",conn)
                facts=facts.merge(brands,on=KEYS,how='left')
            data=data.merge(facts,on=KEYS,how='left')
    data['year_month']=pd.PeriodIndex(data.year_month,freq='M')
    for k in KEYS:data[k]=data[k].astype(str)
    if lineage.get('cutoff'):data=data[data.year_month<=pd.Period(lineage['cutoff'])]
    keys=data[KEYS].drop_duplicates()
    if args.series>0:
        keys=keys.sample(min(args.series,len(keys)),random_state=42);data=data.merge(keys,on=KEYS)
    if any(h not in (1,3,6,12) for h in args.horizons) or args.folds<1:raise ValueError('Choose horizons 1, 3, 6 or 12 and a positive fold count.')
    result=dict(sourceRun=lineage.get('runId'),freshRun=lineage.get('freshRun'),trainingCutoff=lineage.get('cutoff'),
        evaluatedSeries=len(keys),sampled=args.series>0,catboostEnabled=not args.no_catboost,iterations=args.iterations,
        engineHash=hashlib.sha256(Path(__file__).with_name('forecasting.py').read_bytes()).hexdigest(),
        engineFiles={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('forecasting.py','article_forecast.py','forecast_calibration.py','backtest.py')},
        limitations=['Revised historical snapshot with attached static product attributes, not an archive of ERP values known at each cutoff.','Missing launch predictions are scored as zero and reported separately.','These are model forecasts; operational booking floors and launch analogues require as-of order/assortment snapshots for independent evaluation.'],horizons={})
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    for horizon in args.horizons:
        result['horizons'][str(horizon)]=rolling_backtest(data,horizon,args.folds,not args.no_catboost,args.iterations)
        output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        print('Evaluated horizon',horizon,'months; report',output,flush=True)
    return result

if __name__=='__main__':main()
