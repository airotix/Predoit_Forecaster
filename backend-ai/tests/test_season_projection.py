import unittest
import pandas as pd
from season_projection import reconcile_bookings,period_context,purchase_requirements

class SeasonProjectionTests(unittest.TestCase):
 def frames(self):
  key=dict(Reference='P',Couleur='BLACK',Taille='M')
  model=pd.DataFrame([dict(**key,forecast_month=pd.Period(m),forecast_conservative=5.,forecast_base=10.,forecast_optimistic=15.) for m in ('2026-10','2026-11')])
  raw=pd.DataFrame([dict(**key,Date_Commande=d,true_demand=q,LIV_qte=delivered) for d,q,delivered in [('2020-01-01',100,100),('2026-10-08',12,2),('2026-11-08',50,0)]])
  return model,raw
 def test_booked_floor_preserves_model_and_does_not_double_count(self):
  model,raw=self.frames();result=reconcile_bookings(model,raw,as_of='2026-10-15')
  self.assertEqual(result.forecast_base.tolist(),[12,10])
  self.assertEqual(result.model_forecast_base.tolist(),[10,10])
  self.assertEqual(result.forecast_conservative.tolist(),[12,5])
  self.assertEqual(result.forecast_optimistic.tolist(),[15,15])
 def test_period_deliveries_do_not_include_historical_deliveries(self):
  model,raw=self.frames();result=period_context(raw,'2026-10-01','2026-10-31').iloc[0]
  self.assertEqual(result.season_booked,12);self.assertEqual(result.season_delivered,2)
 def test_delivery_requirements_use_planned_dates_and_terminal_status(self):
  model,raw=self.frames()
  raw['RELIQUAT_qte']=[10,10,50];raw['Order_Status']=[3,1,1]
  raw['Planned_Delivery_Date']=['2026-10-15','2027-02-15',None]
  result=period_context(raw,'2026-10-01','2027-03-31').iloc[0]
  self.assertEqual(result.delivery_open,10);self.assertEqual(result.delivery_unknown,1)
  self.assertEqual(result.next_delivery_date,'2027-02-15')
 def test_monthly_assembly_retains_model_booking_and_interval_evidence(self):
  from m7_recommendations import combine_forecasts
  model,raw=self.frames();model['model_type']='RECENT_MEAN';model['interval_method']='UNCALIBRATED'
  reconciled=reconcile_bookings(model,raw,as_of='2026-10-15')
  monthly,_=combine_forecasts(pd.DataFrame(),reconciled)
  self.assertEqual(monthly.model_forecast_base.tolist(),[10,10]);self.assertEqual(monthly.season_booked.tolist(),[12,0])
  self.assertEqual(monthly.interval_method.tolist(),['UNCALIBRATED']*2)
 def test_purchase_need_adds_older_open_deliveries_without_double_counting_season_bookings(self):
  rows=pd.DataFrame([dict(forecast_base=30,season_booked=10,season_delivered=2,delivery_open=18,delivery_unknown=0),
                     dict(forecast_base=30,season_booked=10,season_delivered=2,delivery_open=8,delivery_unknown=1)])
  required=purchase_requirements(rows,'base')
  self.assertEqual(required.iloc[0],38) # 20 additional + 8 season + 10 older open units.
  self.assertTrue(pd.isna(required.iloc[1]))

if __name__=='__main__':unittest.main()
