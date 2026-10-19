import unittest
import test_budgeting as fixtures
import catalogue
import budgeting

class SupplierImportTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.BudgetTests();self.fixture.setUp()
  self.fixture.data['commandes'][0]['Date']='2026-10-01'
  self.fixture.data['commandes']=self.fixture.data['commandes'][:1]
  self.fixture.data['commandes_produits']=self.fixture.data['commandes_produits'][:1]
  self.fixture.data['skus'][0]['Prix_Achat']=0
  self.fixture.seed()
 def tearDown(self):self.fixture.tearDown()
 def test_missing_cost_is_filled_once_with_traceable_net_supplier_price(self):
  f=self.fixture;catalogue.sync(f.c,f.path,force=True)
  row=f.c.execute('SELECT purchase,purchase_source FROM catalogue_prices WHERE currency=?',('EUR',)).fetchone()
  self.assertAlmostEqual(row[0],76.95);self.assertTrue(row[1].startswith('supplier:'))
  detail=catalogue.listing(f.c,'EUR')['rows'][0]['purchasePriceDetails']
  self.assertEqual(detail['currency'],'EUR');self.assertEqual(detail['orderNumber'],'PO1')
  catalogue.sync(f.c,f.path,force=True)
  self.assertAlmostEqual(f.c.execute("SELECT purchase FROM catalogue_prices WHERE currency='EUR'").fetchone()[0],76.95)
 def test_manually_cleared_price_remains_cleared(self):
  f=self.fixture;catalogue.sync(f.c,f.path,force=True)
  catalogue.save_prices(f.c,[dict(sku='sku-P-B-M',purchase=None)],'EUR')
  catalogue.sync(f.c,f.path,force=True)
  self.assertEqual(f.c.execute("SELECT purchase,purchase_source FROM catalogue_prices WHERE currency='EUR'").fetchone(),(None,'manual'))
 def test_stock_and_supplier_receipts_share_one_netting_contract(self):
  rows=budgeting.inventory_for_forecast(self.fixture.c,self.fixture.path)
  self.assertEqual(rows[0]['STOCK'],2);self.assertEqual(rows[0]['CDE_four_qte'],8)

if __name__=='__main__':unittest.main()
