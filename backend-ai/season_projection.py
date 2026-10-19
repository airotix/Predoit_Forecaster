"""Operational booking projections, distinct from the statistical predictions.

The floor is known eligible booked demand, not a new customer adoption model.
Order-booking months and delivery requirements are separate date axes.
"""
import pandas as pd

KEYS=['Reference','Couleur','Taille']
SCENARIOS=('conservative','base','optimistic')


def purchase_requirements(rows,scenario):
    """Known open deliveries plus additional, not-yet-booked planning demand.

    Booked deliveries already appear in delivery_open; adding the whole booking
    projection would count them twice. Older bookings due now are included too.
    Unbooked projected units are assumed needed in the planning period; this is
    an explicit buying assumption, not an inferred delivery date.
    """
    additional=(rows['forecast_'+scenario]-rows.season_booked).clip(lower=0)
    return (additional+rows.delivery_open).where(rows.delivery_unknown.eq(0))


def reconcile_bookings(monthly,raw,as_of=None):
    result=monthly.copy()
    for scenario in SCENARIOS:result['model_forecast_'+scenario]=result['forecast_'+scenario]
    dates=pd.to_datetime(raw.Date_Commande,errors='coerce')
    valid=dates.notna()
    if as_of is not None:valid &= dates.dt.normalize()<=pd.Timestamp(as_of).normalize()
    booked=raw.loc[valid,KEYS+['true_demand']].copy()
    booked['forecast_month']=dates.loc[valid].dt.to_period('M')
    booked=booked.groupby(KEYS+['forecast_month'],as_index=False).true_demand.sum().rename(columns={'true_demand':'season_booked'})
    result=result.merge(booked,on=KEYS+['forecast_month'],how='left')
    result['season_booked']=result.season_booked.fillna(0.)
    for scenario in SCENARIOS:
        # max(model, bookings) = bookings + max(model - bookings, 0).
        # Adding the full model to bookings would count demand twice.
        result['forecast_'+scenario]=result[['model_forecast_'+scenario,'season_booked']].max(axis=1)
    return result


def period_context(raw,start,end):
    dates=pd.to_datetime(raw.Date_Commande,errors='coerce')
    in_season=dates.between(pd.Timestamp(start),pd.Timestamp(end)+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1))
    rows=raw.loc[in_season].copy()
    result=raw[KEYS].drop_duplicates().merge(rows.groupby(KEYS,as_index=False).agg(season_booked=('true_demand','sum'),season_delivered=('LIV_qte','sum')),on=KEYS,how='left')
    result[['season_booked','season_delivered']]=result[['season_booked','season_delivered']].fillna(0.)
    if 'Planned_Delivery_Date' not in raw:
        # Legacy fixtures have no delivery contract; preserve their booking basis.
        result['delivery_open']=0.;result['delivery_unknown']=0.
        result['next_delivery_date']=None
        return result
    pending=pd.to_numeric(raw.RELIQUAT_qte,errors='coerce')
    if 'Order_Status' in raw:
        status=pd.to_numeric(raw.Order_Status,errors='coerce')
        pending=pending.where(~status.isin([0,2,3]),0.)
    eta=pd.to_datetime(raw.Planned_Delivery_Date,errors='coerce')
    dated=eta.between(pd.Timestamp(start),pd.Timestamp(end)+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1))
    values=raw[KEYS].copy();values['delivery_open']=pending.where(dated,0.)
    values['delivery_unknown']=((pending>0)&(eta.isna()|(eta<pd.Timestamp(start)))).astype(int)
    values['next_delivery_date']=eta.where(dated&(pending>0)).dt.strftime('%Y-%m-%d')
    values=values.groupby(KEYS,as_index=False).agg(delivery_open=('delivery_open','sum'),delivery_unknown=('delivery_unknown','sum'),next_delivery_date=('next_delivery_date','min'))
    return result.merge(values,on=KEYS,how='left')
