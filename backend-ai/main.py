"""Build versioned forecasts and publish serving data atomically."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import uuid
import pandas as pd
from config import DATA_FILE_PATH,FORECAST_HORIZON_MONTHS

def run_phase1(data_path=None):
    """Deployment entry point: only a newly activated API export may be used."""
    from database import get_connection,_create_persistent_tables
    from joolan import ensure_joolan_schema
    if data_path:raise ValueError('External data files are disabled. Activate a fresh Joolan export in Setup.')
    conn=get_connection()
    try:
        _create_persistent_tables(conn);ensure_joolan_schema(conn)
        with conn:
            conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('source_policy','fresh_only')")
            conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('forecast_source','fresh')")
    finally:conn.close()
    return _run_phase1()

def _run_phase1(data_path=None):
    """Pipeline implementation; legacy fixtures remain available for regression tests."""
    from database import get_connection,populate_database,_create_persistent_tables
    from joolan import selected_pipeline_path,snapshot_summary
    from planning import active_plan,input_rows,inputs_fingerprint
    from ingestion import merge_config_csv_with_append
    base=Path(__file__).resolve().parent
    conn=get_connection()
    try:
        _create_persistent_tables(conn)
        from operating_scope import read as read_scope
        operating_scope=read_scope(conn)
        from catalogue import sync
        plan=active_plan(conn);selected=snapshot_summary(conn)
        filepath=data_path or selected_pipeline_path(conn,base/'data/raw/.joolan_pipeline.csv')
        state=dict(conn.execute('SELECT key,value FROM joolan_state'))
        if state.get('fresh_run'):sync(conn)
        inputs=input_rows(conn)
        if state.get('source_policy')=='fresh_only' and (not filepath or Path(filepath).name!='.fresh_joolan_pipeline.csv'):
            raise ValueError('Only freshly exported Joolan data may train this deployment.')
        source='fresh' if filepath and Path(filepath).name=='.fresh_joolan_pipeline.csv' else 'combined' if filepath and Path(filepath).name=='.combined_pipeline.csv' else 'joolan' if filepath and Path(filepath).name=='.joolan_pipeline.csv' else 'explicit' if data_path else 'legacy'
    finally:conn.close()
    filepath=filepath or merge_config_csv_with_append() or DATA_FILE_PATH
    digest=hashlib.sha256()
    with open(filepath,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    from m1_data_preparation import run_module1
    from m2_model_assignment import run_module2
    from m3_kpis import run_module3
    from forecasting import forecast
    from m7_recommendations import run_module7
    data=run_module1(filepath);raw=data['raw']
    training_monthly = data['monthly_sku_color_size']
    combined_summary = None
    if source=='fresh':
        coverage=pd.Timestamp(json.loads(state['fresh_report'])['exportedThrough'])
        last_complete=coverage.to_period('M') if coverage.date()==coverage.to_period('M').end_time.date() else coverage.to_period('M')-1
        training_monthly=training_monthly[training_monthly.year_month<=last_complete]
        if training_monthly.empty:raise ValueError('No complete training month in the fresh export.')
    if source == 'combined':
        from history_store import connection as history_connection, summary as history_summary
        history_conn = history_connection()
        try:
            combined_summary = history_summary(history_conn)
        finally:
            history_conn.close()
        coverage = pd.Timestamp(combined_summary['coveredThrough'])
        last_complete = coverage.to_period('M') if coverage.date() == coverage.to_period('M').end_time.date() else coverage.to_period('M') - 1
        training_monthly = training_monthly[training_monthly.year_month <= last_complete]
        if training_monthly.empty:
            raise ValueError('No complete historical month is available for forecasting.')
    if inputs:
        from planning import apply_input_rows
        apply_input_rows(raw,inputs)
        latest=raw.sort_values('Date_Commande').drop_duplicates(['Reference','Couleur','Taille'],keep='last')
        data['stock_info']=latest[['Reference','Couleur','Taille','STOCK','CDE_four_qte']].copy()
    latest=raw.sort_values('Date_Commande').drop_duplicates(['Reference','Couleur','Taille'],keep='last')
    data['stock_info']=latest[['Reference','Couleur','Taille','STOCK','CDE_four_qte']].copy()
    profiles=run_module2(data['monthly_sku_color'])
    kpis=run_module3(raw,data['monthly_sku_color'],profiles)
    start=None;horizon=FORECAST_HORIZON_MONTHS
    if plan:
        start=pd.Period(plan['startDate'],freq='M')
        horizon=pd.Period(plan['endDate'],freq='M').ordinal-start.ordinal+1
    effective_cutoff=last_complete if source in ('fresh','combined') else None
    run_id=uuid.uuid4().hex;output=base/'output/runs'/run_id;output.mkdir(parents=True)
    feature_rows=raw[raw.year_month<=effective_cutoff] if effective_cutoff is not None else raw
    feature_rows=feature_rows.sort_values('Date_Commande').drop_duplicates(['Reference','Couleur','Taille'],keep='last')
    feature_names=dict(brand='Catalog_Brand',category='Famille',material='Matiere',collection='Catalog_Collection')
    product_features={tuple(str(row[k]) for k in ('Reference','Couleur','Taille')):{name:str(row.get(column) or 'UNKNOWN') for name,column in feature_names.items()} for _,row in feature_rows.iterrows()}
    monthly,selection=forecast(training_monthly,horizon=horizon,start=start,cutoff=effective_cutoff,metadata=product_features,artifact_dir=output)
    from launch_forecast import extend_launches
    monthly,selection,assortment_report=extend_launches(monthly,selection,raw,effective_cutoff or training_monthly.year_month.max(),as_of=json.loads(state['fresh_report'])['exportedThrough'] if source=='fresh' else None)
    from season_projection import reconcile_bookings,period_context,purchase_requirements
    monthly=reconcile_bookings(monthly,raw,as_of=json.loads(state['fresh_report'])['exportedThrough'] if source=='fresh' else None)
    if source=='fresh' and plan:
        from budgeting import inventory_for_forecast
        operational=get_connection()
        try:data['stock_info']=pd.DataFrame(inventory_for_forecast(operational))
        finally:operational.close()
    reco=run_module7(pd.DataFrame(),monthly,raw,data['stock_info'],kpis['sku_kpis'],kpis['size_kpis'],data['critere_map'],validated=True)
    period=period_context(raw,monthly.forecast_month.min().start_time,monthly.forecast_month.max().end_time.date())
    reco['recommendations']=reco['recommendations'].merge(period,on=['Reference','Couleur','Taille'],how='left')
    reco['recommendations'][['season_booked','season_delivered']]=reco['recommendations'][['season_booked','season_delivered']].fillna(0.)
    model_totals=monthly.groupby(['Reference','Couleur','Taille'],as_index=False)[['model_forecast_'+s for s in ('conservative','base','optimistic')]].sum()
    reco['recommendations']=reco['recommendations'].merge(model_totals,on=['Reference','Couleur','Taille'],how='left')
    r_context=reco['recommendations']
    r_context['all_open_orders']=r_context.confirmed_orders
    r_context['historical_delivered']=r_context.confirmed_delivered
    r_context['confirmed_orders']=r_context.delivery_open.where(r_context.delivery_unknown.eq(0))
    r_context['confirmed_delivered']=r_context.season_delivered
    for scenario in ('conservative','base','optimistic'):
        future=purchase_requirements(r_context,scenario)
        r_context['required_future_'+scenario]=future
        r_context['net_to_order_'+scenario]=(future-r_context.available_inventory).clip(lower=0)
    r_context['probable_additional_base']=(r_context.forecast_base-r_context.season_booked).clip(lower=0)
    latest=raw.sort_values('Date_Commande').drop_duplicates(['Reference','Couleur','Taille'],keep='last')
    details=latest[['Reference','Couleur','Taille']].copy()
    is_joolan='Data_Source' in raw and raw.Data_Source.eq('joolan').all()
    for target,column in [('unit_selling_price','Selling_Price'),('unit_purchase_cost','Purchase_Cost')]:
        details[target]=latest[column].to_numpy() if column in latest else None
    if not is_joolan and details.unit_selling_price.isna().all():details['unit_selling_price']=latest['Prix'].to_numpy()
    r=reco['recommendations'].merge(details,on=['Reference','Couleur','Taille'],how='left')
    for idx,row in r.iterrows():
        missing=[]
        if pd.isna(row.unit_selling_price):missing.append('PRICE_UNKNOWN')
        if pd.isna(row.unit_purchase_cost):missing.append('COST_UNKNOWN')
        if pd.isna(row.current_stock) or pd.isna(row.pipeline_stock):missing.append('INVENTORY_UNKNOWN')
        if row.delivery_unknown:missing.append('DELIVERY_DATE_UNKNOWN')
        r.at[idx,'financial_note']=';'.join(missing) if missing else 'Actual SKU costs and inventory supplied.'
        for scenario in ('conservative','base','optimistic'):
            r.at[idx,'expected_revenue_'+scenario]=row['forecast_'+scenario]*row.unit_selling_price if pd.notna(row.unit_selling_price) else None
            r.at[idx,'estimated_cost_'+scenario]=row['net_to_order_'+scenario]*row.unit_purchase_cost if pd.notna(row.unit_purchase_cost) else None
        r.at[idx,'estimated_margin_base']=row.forecast_base*(row.unit_selling_price-row.unit_purchase_cost) if pd.notna(row.unit_selling_price) and pd.notna(row.unit_purchase_cost) else None
        r.at[idx,'margin_rate_base']=(row.unit_selling_price-row.unit_purchase_cost)/row.unit_selling_price if pd.notna(row.unit_selling_price) and pd.notna(row.unit_purchase_cost) and row.unit_selling_price>0 else None
    r['avg_price']=r['unit_selling_price']
    r=r.merge(selection.rename(columns={'confidence':'model_confidence'}),on=['Reference','Couleur','Taille'],how='left')
    r['confidence']=r.model_confidence.fillna('LOW')
    if 'needs_assortment_review' in r:
        mask=r.needs_assortment_review.fillna(False).astype(bool)
        r.loc[mask,'financial_note']=r.loc[mask,'financial_note']+';ASSORTMENT_REVIEW'
    if plan:r['Saison']=plan['name']
    reco['recommendations']=r
    r.to_csv(output/'recommendations.csv',index=False)
    monthly.to_csv(output/'forecast_monthly_detail.csv',index=False)
    selection.to_csv(output/'model_selection.csv',index=False)
    lineage=dict(runId=run_id,source=source,sourceHash=digest.hexdigest(),sourceImportedAt=selected.get('importedAt') if source in ('joolan','combined') else None,
        seasonId=plan['id'] if plan else None,plan=plan,cutoff=str(effective_cutoff or training_monthly.year_month.max()),
        forecastStart=str(monthly.forecast_month.min()),forecastEnd=str(monthly.forecast_month.max()),
        engine='calendar-validation-v2',inputsHash=inputs_fingerprint(inputs),outputDirectory=str(output),createdAt=dt.datetime.now(dt.timezone.utc).isoformat())
    lineage['projectionDefinition']='Operational monthly booking projection = max(statistical prediction, eligible booked units). Model predictions are retained separately; booking dates are not delivery dates.'
    lineage['orderBalanceDefinition']='Validated open balances with terminal statuses excluded; historical deliveries are distinct from delivered units against season bookings.'
    lineage['purchaseRequirementDefinition']='Open customer deliveries due within the period plus max(operational booking projection - season booked units, 0). This assumes additional unbooked demand needs supply within the planning period. Unknown or overdue delivery commitments require reconciliation.'
    import importlib.metadata
    lineage['runtimeVersions']={name:importlib.metadata.version(name) for name in ('pandas','numpy','scikit-learn')}
    try:lineage['runtimeVersions']['catboost']=importlib.metadata.version('catboost')
    except importlib.metadata.PackageNotFoundError:lineage['runtimeVersions']['catboost']=None
    code_base=Path(__import__('forecasting').__file__).resolve().parent
    lineage['codeHash']=hashlib.sha256(b''.join((code_base/name).read_bytes() for name in ('forecasting.py','article_forecast.py','forecast_calibration.py','season_projection.py','launch_forecast.py','main.py','m7_recommendations.py','budgeting.py','purchase_prices.py','order_constraints.py','planning.py','purchase_draft.py','buying.py'))).hexdigest()
    lineage['uncertaintyDefinition']='Monthly ranges use earlier held-out residual pools when at least 30 comparable errors exist; otherwise uncalibrated. Season sums have no coverage guarantee. Confidence is an error-based evidence policy, not a probability.'
    lineage['assortment']=assortment_report
    lineage['qualitySummary']=dict(calibratedVariants=int(r.calibration_points.fillna(0).gt(0).sum()),uncalibratedVariants=int(r.calibration_points.fillna(0).eq(0).sum()),
        monthlyRangeMethods=monthly.interval_method.value_counts().to_dict(),confidencePolicy='MEDIUM requires >=6 earlier held-out points, WAPE <=50% and absolute bias <=25%. Otherwise LOW; no confidence percentage is claimed.')
    joolan_rows = raw[raw.Data_Source.eq('joolan')] if 'Data_Source' in raw else raw.iloc[:0]
    lineage['cancellationsComplete']=bool(joolan_rows.empty or ('Cancellations_Known' in joolan_rows and joolan_rows.Cancellations_Known.astype(str).str.lower().eq('true').all()))
    if source == 'combined':
        lineage['combinedHistory'] = combined_summary
    if source=='fresh':
        lineage.update(freshRun=state['fresh_run'],freshReport=json.loads(state['fresh_report']))
        if operating_scope:
            lineage.update(operatingScope=operating_scope,operatingScopeRevision=operating_scope['revision'])
            lineage['scopeNotice']='Wholesale booked-order forecast for selected brands; clearance, faulty and classified consignment COMMANDE records excluded. Unclassified channels require review; consignment sell-through is not modelled.'
    lineage['demandDefinition']='Net ordered units' if is_joolan and lineage['cancellationsComplete'] else 'Gross ordered units; cancellations unknown' if is_joolan else 'Delivered plus remaining units'
    if source == 'combined':
        lineage['demandDefinition']='CSV delivered plus remaining units through baseline cutoff; later Joolan ordered units minus known cancellations.'
    if source=='fresh':lineage['demandDefinition']=json.loads(state['fresh_report'])['demandDefinition']
    (output/'lineage.json').write_text(json.dumps(lineage,indent=2),encoding='utf-8')
    results=dict(data=data,profiles=profiles,kpis=kpis,recommendations=reco,lineage=lineage)
    populate_database(results)
    # Build this derived view during the forecast job, rather than making the
    # first Product KPIs visitor scan the entire newly published order ledger.
    try:
        from product_kpis import ledger_reorders
        conn=get_connection()
        try:ledger_reorders(conn,dict(conn.execute('SELECT key,value FROM pipeline_metadata')))
        finally:conn.close()
    except Exception as error:
        print('[READ CACHE] KPI precomputation deferred:',type(error).__name__)
    return results

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--data')
    run_phase1(parser.parse_args().data)
