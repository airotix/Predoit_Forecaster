import unittest
import pandas as pd
from m7_recommendations import add_financial_overlay

class FinancialOverlayTests(unittest.TestCase):
 def test_mixed_known_and_unknown_quantities_remain_numeric_and_unknown(self):
  frame=pd.DataFrame({'Reference':['P','Q'],'Couleur':['B','B'],**{f'net_to_order_{s}':pd.Series([2.0,None],dtype=object) for s in ('base','conservative','optimistic')}})
  prices=pd.DataFrame({'Reference':['P','Q'],'Couleur':['B','B'],'avg_price':pd.Series([10.0,None],dtype=object)})
  result=add_financial_overlay(frame,prices)
  self.assertEqual(result.iloc[0].expected_revenue_base,20)
  self.assertEqual(result.iloc[0].margin_rate_base,.5)
  self.assertTrue(pd.isna(result.iloc[1].expected_revenue_base))
  self.assertTrue(pd.isna(result.iloc[1].margin_rate_base))

if __name__=='__main__':unittest.main()
