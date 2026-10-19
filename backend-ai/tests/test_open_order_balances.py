import unittest
import pandas as pd
from m7_recommendations import add_current_orders_and_stock


class OpenOrderTests(unittest.TestCase):
 def calculate(self,lines):
  key=dict(Reference='P',Couleur='BLACK',Taille='M')
  raw=pd.DataFrame([dict(**key,Client=str(i),CDE_qte=10,LIV_qte=2,ANN_qte=0,Data_Source='joolan',**line) for i,line in enumerate(lines)])
  stock=pd.DataFrame([dict(**key,STOCK=3,CDE_four_qte=None)])
  return add_current_orders_and_stock(pd.DataFrame([dict(**key,forecast_base=5)]),raw,stock).iloc[0]
 def test_closed_cancelled_and_draft_lines_cannot_become_open(self):
  result=self.calculate([dict(Order_Status=s,RELIQUAT_qte=8) for s in (0,2,3)])
  self.assertEqual(result.confirmed_orders,0);self.assertEqual(result.confirmed_clients,0)
 def test_uses_validated_remaining_not_reconstructed_balance(self):
  result=self.calculate([dict(Order_Status=1,RELIQUAT_qte=4),dict(Order_Status=3,RELIQUAT_qte=0)])
  self.assertEqual(result.confirmed_orders,4);self.assertEqual(result.confirmed_clients,1)
  self.assertEqual(result.confirmed_delivered,4)
  self.assertTrue(pd.isna(result.pipeline_stock));self.assertTrue(pd.isna(result.available_inventory))
 def test_invalid_or_missing_balances_and_statuses_fail(self):
  for line in [dict(Order_Status=1),dict(Order_Status=1,RELIQUAT_qte=-1),dict(Order_Status=1,RELIQUAT_qte=None),dict(Order_Status=9,RELIQUAT_qte=2)]:
   with self.subTest(line=line),self.assertRaises(ValueError):self.calculate([line])


if __name__=='__main__':unittest.main()
