import unittest
import pandas as pd
from forecasting import rolling_backtest

class FullAssortmentTests(unittest.TestCase):
 def test_launch_only_units_are_scored_and_reported(self):
  data=[dict(Reference='A',Couleur='BLACK',Taille='M',year_month=m,true_demand=1.,brand='KNOWN') for m in pd.period_range('2023-01',periods=36,freq='M')]
  data += [dict(Reference='NEW',Couleur='BLACK',Taille='M',year_month=m,true_demand=100.,brand='NEW_BRAND') for m in pd.period_range('2025-07',periods=6,freq='M')]
  result=rolling_backtest(pd.DataFrame(data),folds=1,use_catboost=False)[0]
  self.assertEqual(result['selected']['actualUnits'],606)
  self.assertEqual(result['selected']['n'],12)
  self.assertEqual(result['newVariants'],1)
  self.assertEqual(result['missingForecastUnits'],600)
  self.assertGreater(result['selected']['wape'],99)
  self.assertEqual(result['knownVariantMetrics']['wape'],0)
  self.assertEqual(result['articlePeriodMetrics']['actualUnits'],606)
  self.assertEqual(result['articlePeriodMetrics']['n'],2)
  self.assertEqual(result['variantPeriodMetrics']['n'],2)
  self.assertEqual(result['segments']['brand']['NEW_BRAND']['selected']['actualUnits'],600)
  self.assertEqual(result['segments']['brand']['NEW_BRAND']['missingForecastUnits'],600)

if __name__=='__main__':unittest.main()
