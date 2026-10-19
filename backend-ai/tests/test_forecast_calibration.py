import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from forecasting import baseline,training_frame
from forecast_calibration import calibration,quality,bounds,summarize_pools

class CalibrationTests(unittest.TestCase):
 def test_selection_window_cannot_change_earlier_calibration_errors(self):
  months=pd.period_range('2022-01',periods=48,freq='M');key=('P','BLACK','M')
  hist={key:(months,np.arange(48,dtype=float)+1)}
  args=(months[-1],6,{key:'recent_mean'},{},baseline,lambda *args:None,lambda *args:{},{},10)
  first,_=calibration(hist,*args)
  changed=hist[key][1].copy();changed[-6:]=99999
  second,_=calibration({key:(months,changed)},*args)
  self.assertEqual(first,second);self.assertEqual(len(first[key]),12)
 def test_confidence_requires_measured_error_not_only_point_count(self):
  self.assertEqual(quality([(10,100,-90)]*12)['confidence'],'LOW')
  self.assertEqual(quality([(10,10,0)]*12)['confidence'],'MEDIUM')
  self.assertEqual(quality([(0,0,0)]*12)['confidence'],'LOW')
 def test_insufficient_interval_samples_are_explicit(self):
  low,high,method,count=bounds('recent_mean',1,10,1,{},6)
  self.assertEqual(method,'UNCALIBRATED');self.assertEqual(count,0)
  self.assertLessEqual(low,10);self.assertGreaterEqual(high,10)
 def test_shared_quantiles_are_computed_once_and_preserve_bounds(self):
  from forecasting import forecast
  pool={('recent_mean',h):list(range(-20,30)) for h in range(1,7)}
  summaries=summarize_pools(pool)
  for h in range(1,7):self.assertEqual(bounds('recent_mean',h,10,2,pool,6),bounds('recent_mean',h,10,2,pool,6,summaries))
  data=pd.DataFrame([dict(Reference=str(i),Couleur='B',Taille='M',year_month=m,true_demand=1.) for i in range(40) for m in pd.period_range('2020-01',periods=36,freq='M')])
  original=np.quantile
  with patch('forecast_calibration.np.quantile',wraps=original) as quantile:
   result,_=forecast(data,use_catboost=False,use_hierarchy=False)
  self.assertLessEqual(quantile.call_count,6)
  self.assertTrue(result.forecast_base.eq(1).all())
 def test_training_retains_active_history_instead_of_four_rows_per_series(self):
  months=pd.period_range('2020-01',periods=48,freq='M')
  hist={('ACTIVE','BLACK','M'):(months,np.ones(48)),('OLD','BLACK','M'):(months,np.r_[1.,np.zeros(47)])}
  frame=training_frame(hist,months[-1],metadata={('ACTIVE','BLACK','M'):dict(category='JACKETS')})
  self.assertGreater(len(frame[frame.Reference=='ACTIVE']),20)
  self.assertEqual(len(frame[frame.Reference=='OLD']),1)
  self.assertTrue(frame[frame.Reference=='ACTIVE'].category.eq('JACKETS').all())

if __name__=='__main__':unittest.main()
