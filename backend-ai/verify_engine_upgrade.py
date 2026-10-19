"""Run the real pipeline against a new SQLite snapshot without publishing live.

Example: python -B -u verify_engine_upgrade.py --target D:/Preduit-verification/run.db
The target must not exist. Raw Joolan data are read from the configured source DB.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3


def manual_prices(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_prices'").fetchone():return None
    rows=conn.execute("SELECT * FROM catalogue_prices WHERE purchase_source='manual' OR selling_source='manual' ORDER BY sku,currency").fetchall()
    # Only manually controlled values must survive catalogue synchronization.
    names=[r[1] for r in conn.execute('PRAGMA table_info(catalogue_prices)')]
    values=[]
    for row in rows:
        r=dict(zip(names,row))
        values.append((r['sku'],r['currency'],r.get('purchase') if r.get('purchase_source')=='manual' else 'automatic',r.get('selling') if r.get('selling_source')=='manual' else 'automatic'))
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--target',required=True)
    parser.add_argument('--resume-snapshot',action='store_true',help='Reuse an isolated, still-unpublished snapshot after an interrupted verification.')
    parser.add_argument('--source',default=str(Path(__file__).resolve().parent/'data/joolan_live.db'))
    parser.add_argument('--report',default='output/engine-upgrade/pipeline-verification.json')
    args=parser.parse_args();source=Path(args.source).resolve();target=Path(args.target).resolve()
    if target==source or (target.exists() and not args.resume_snapshot):raise ValueError('Use a new isolated verification database path.')
    if args.resume_snapshot and not target.is_file():raise ValueError('No isolated snapshot exists to resume.')
    if not source.is_file():raise ValueError('The serving database does not exist.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
        before=json.loads(original.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()[0])
        with sqlite3.connect(target) as isolated:
            if args.resume_snapshot:
                copied=json.loads(isolated.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()[0])
                if copied['runId']!=before['runId']:raise ValueError('Isolated snapshot has already published or no longer matches the live source run.')
            else:original.backup(isolated)
    os.environ['FORECASTER_DB_PATH']=str(target)
    import database
    from main import run_phase1
    with database.get_connection() as conn:prices_before=manual_prices(conn)
    print('Isolated snapshot ready; live publication remains',before['runId'],flush=True)
    result=run_phase1();lineage=result['lineage'];monthly=result['recommendations']['monthly_detail'];rows=result['recommendations']['recommendations']
    checks={}
    checks['v2_engine']=lineage['engine']=='calendar-validation-v2'
    checks['same_validated_source']=lineage['freshRun']==before['freshRun']
    checks['all_monthly_bookings_covered']=bool((monthly.forecast_base+1e-6>=monthly.season_booked).all())
    checks['scenario_ordering']=bool(((monthly.forecast_conservative<=monthly.forecast_base+1e-6)&(monthly.forecast_base<=monthly.forecast_optimistic+1e-6)).all())
    checks['original_predictions_retained']=bool(monthly[['model_forecast_conservative','model_forecast_base','model_forecast_optimistic']].notna().all().all())
    checks['no_negative_open_balances']=bool((rows.all_open_orders>=0).all())
    from season_projection import purchase_requirements
    expected_required=purchase_requirements(rows,'base')
    checks['delivery_and_unbooked_demands_added_once']=bool(((rows.required_future_base-expected_required).abs().fillna(0)<1e-6).all() and rows.required_future_base.isna().equals(expected_required.isna()))
    checks['season_bookings_covered']=bool((rows.forecast_base+1e-6>=rows.season_booked).all())
    checks['unknown_delivery_blocks_purchase']=bool(rows.loc[rows.delivery_unknown>0,'required_future_base'].isna().all())
    raw=result['data']['raw']
    observed=raw[raw.year_month.between(monthly.forecast_month.min(),monthly.forecast_month.max())]
    expected=set(map(tuple,observed[['Reference','Couleur','Taille']].astype(str).to_numpy()))
    actual=set(map(tuple,rows[['Reference','Couleur','Taille']].astype(str).to_numpy()))
    checks['all_booked_variants_present']=expected<=actual
    with database.get_connection() as conn:
        checks['manual_prices_preserved']=manual_prices(conn)==prices_before
        checks['database_quick_check']=conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        checks['persisted_monthly_count']=conn.execute('SELECT COUNT(*) FROM forecast_monthly').fetchone()[0]==len(monthly)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as original:
        live=json.loads(original.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()[0])
        checks['live_publication_unchanged']=live['runId']==before['runId']
    from budgeting import build_report
    with database.get_connection() as conn:
        budget=build_report(conn)
    report=dict(checks=checks,passed=all(checks.values()),liveRun=before['runId'],verificationRun=lineage['runId'],database=str(target),lineage=lineage,
        variants=len(rows),monthlyRows=len(monthly),bookedVariants=len(expected),baseUnits=float(rows.forecast_base.sum()),
        seasonBookedUnits=float(rows.season_booked.sum()),openOrders=float(rows.all_open_orders.sum()),
        unknownDeliveryVariants=int(rows.delivery_unknown.gt(0).sum()),confidence=rows.confidence.value_counts().to_dict(),
        selectedModels=rows.selected_model.value_counts().to_dict(),budgetSummary=budget['summary'],
        limitations=['This verifies pipeline invariants, not future predictive accuracy.','Unobserved future launches need an explicit assortment/availability contract.','Historical backtests use a revised snapshot, not archived point-in-time ERP exports.'])
    report_path=Path(args.report);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2,default=str,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'],checks=checks,report=str(report_path)),indent=2),flush=True)
    if not report['passed']:raise RuntimeError('An isolated pipeline verification check failed; live results were retained.')


if __name__=='__main__':main()
