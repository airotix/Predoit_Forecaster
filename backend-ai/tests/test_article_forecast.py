import unittest
import numpy as np
import pandas as pd
from article_forecast import shares,article_values,predict_challengers
from forecasting import baseline

class ArticleForecastTests(unittest.TestCase):
 def test_size_and_colour_allocations_add_to_article_total(self):
  end=pd.Period('2026-09');months=pd.period_range(end-23,end,freq='M')
  a=('P','BLACK','S');b=('P','RED','M')
  histories={a:(months,np.repeat(2.,24)),b:(months,np.repeat(6.,24))}
  self.assertEqual(shares(histories,[a,b],end),{a:.25,b:.75})
  self.assertTrue((article_values(histories,[a,b],end)==8).all())
  result=predict_challengers(histories,{'P':dict(method='recent_mean',keys=[a,b])},end,6,baseline)
  np.testing.assert_allclose(result[a]+result[b],np.repeat(8.,6))
 def test_future_observations_do_not_change_past_allocation(self):
  months=pd.period_range('2025-01',periods=24,freq='M');end=pd.Period('2025-12')
  a=('P','BLACK','S');b=('P','RED','M')
  histories={a:(months,np.r_[np.ones(12),np.repeat(999.,12)]),b:(months,np.ones(24))}
  self.assertEqual(shares(histories,[a,b],end),{a:.5,b:.5})
 def test_dormant_fallback_reads_only_the_selected_article(self):
  class NoFullScan(dict):
   def items(self):raise AssertionError('Do not scan unrelated article histories')
  months=pd.period_range('2025-01',periods=24,freq='M');end=months[-1]
  a=('P','BLACK','S');b=('P','RED','M')
  histories=NoFullScan({a:(months,np.r_[np.ones(12),np.zeros(12)]),b:(months,np.r_[np.repeat(3.,12),np.zeros(12)])})
  self.assertEqual(shares(histories,[a,b],end),{a:.25,b:.75})

if __name__=='__main__':unittest.main()
