"""Cheap readiness checks before starting the expensive forecast job."""
import pandas as pd
from planning import active_plan


def readiness(conn):
    state = dict(conn.execute('SELECT key,value FROM joolan_state'))
    source = state.get('forecast_source', 'legacy')
    plan = active_plan(conn)
    blockers = []
    warnings = []
    cutoff = None
    if source == 'fresh' or state.get('source_policy')=='fresh_only':
        import json
        source='fresh'
        report=json.loads(state.get('fresh_report','{}'))
        if not state.get('fresh_run') or not report.get('readyForForecast'):
            blockers.append('Complete and activate a new Joolan API export in Setup. Previous data is excluded.')
        if report.get('exportedThrough'):
            date=pd.Timestamp(report['exportedThrough'])
            cutoff=date.to_period('M') if date.date()==date.to_period('M').end_time.date() else date.to_period('M')-1
        warnings.extend(report.get('warnings',[]))
        from operating_scope import read,primary
        operating=read(conn)
        if operating:
            if not set(primary(operating))<=set(report.get('warehouses',[])):blockers.append('Export the primary warehouses selected in Business Scope.')
            if not set(operating['brands'])<=set(report.get('brands',[])):blockers.append('Export all brand codes selected in Business Scope before forecasting.')
            warnings.append('Business scope applies selected brands and primary supply only. Classified clearance, faulty and consignment orders are excluded from wholesale training. Consignment sell-through remains unmapped.')
            unknown=[w for w,r in operating['warehouseRoles'].items() if r=='unclassified']
            if unknown:warnings.append(f'{len(unknown)} warehouse/channel codes remain unclassified. Their stock is excluded from normal supply; review their customer-order meaning.')
    elif source == 'combined':
        from history_store import connection, summary
        history_conn = connection()
        try:
            history = summary(history_conn)
        finally:
            history_conn.close()
        if not state.get('customer_order_type') or history['needsOrderType']:
            blockers.append('Confirm the customer-order document type and build the combined database.')
        if history['gaps']:
            blockers.append('Import the missing date ranges shown in combined history.')
        if history['totalRows'] == 0:
            blockers.append('Build the CSV + Joolan database first.')
        if history['legacyQuarantinedRows']:
            warnings.append(f"{history['legacyQuarantinedRows']} invalid CSV rows are retained for review and excluded from training.")
        if history['coveredThrough']:
            date = pd.Timestamp(history['coveredThrough'])
            cutoff = date.to_period('M') if date.date() == date.to_period('M').end_time.date() else date.to_period('M')-1
    elif source == 'legacy':
        from discovery import historical_profile
        try:
            profile = historical_profile()
            cutoff = pd.Period(profile['lastOrderDate'], freq='M')
            warnings.append('CSV-only source selected. Choose CSV + confirmed Joolan orders to include newer history.')
            from history_store import connection, summary
            history_conn = connection()
            try:
                quality = summary(history_conn)
            finally:
                history_conn.close()
            if quality['legacyQuarantinedRows']:
                blockers.append(f"The CSV has {quality['legacyQuarantinedRows']} invalid quantity rows. Use the combined database's validated view, or correct the CSV before training directly from it.")
        except (ValueError, OSError) as error:
            blockers.append(str(error))
    elif source == 'joolan':
        kind = state.get('customer_order_type', '')
        if not kind:
            blockers.append('Confirm the customer-order document type.')
        row = conn.execute("SELECT MAX(json_extract(payload,'$.Order_Date')) FROM joolan_order_lines WHERE usable=1 AND json_extract(payload,'$.Document_Type')=?", (kind,)).fetchone()
        if row and row[0]:
            cutoff = pd.Period(row[0], freq='M')
        else:
            blockers.append('Import usable Joolan customer-order lines.')
        warnings.append('Joolan snapshot only selected; the historical CSV is excluded.')
    else:
        blockers.append('Select a supported forecast source.')
    if not plan:
        blockers.append('Save a planning season before refreshing forecasts.')
    elif cutoff is not None:
        start = pd.Period(plan['startDate'], freq='M')
        end = pd.Period(plan['endDate'], freq='M')
        horizon = end.ordinal-start.ordinal+1
        if start <= cutoff:
            blockers.append(f'Season must start after the training month {cutoff}.')
        if not 1 <= horizon <= 24:
            blockers.append('Season must cover between 1 and 24 months.')
        if end.ordinal-cutoff.ordinal > 36:
            blockers.append('Season ends more than 36 months beyond available training history.')
    warnings.append('Demand forecasts can run without stock/costs. Purchase quantities and approval require actual matched inputs; unknown cancellations also block approval.')
    return dict(ready=not blockers,source=source,season=plan,trainingCutoff=str(cutoff) if cutoff is not None else None,
                earliestForecastMonth=str(cutoff+1) if cutoff is not None else None,blockers=blockers,warnings=warnings)
