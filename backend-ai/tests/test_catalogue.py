import sqlite3,unittest
import catalogue,planning,buying,database
import test_budgeting as fixtures

class CatalogueTests(unittest.TestCase):
 setUp=fixtures.BudgetTests.setUp
 tearDown=fixtures.BudgetTests.tearDown
 seed=fixtures.BudgetTests.seed
 report=fixtures.BudgetTests.report
 def test_all_skus_and_verified_joolan_prices_seeded(self):
  result=catalogue.sync(self.c,self.path)
  self.assertEqual(result['count'],1)
  row=catalogue.listing(self.c,'EUR')['rows'][0]
  self.assertEqual(row['purchase'],90);self.assertEqual(row['selling'],100)
 def test_saved_prices_flow_to_budget_and_new_forecast_inputs(self):
  catalogue.sync(self.c,self.path)
  catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',purchase=40,selling=120)],'EUR')
  row=self.report()['rows'][0]
  self.assertEqual((row['unitCost'],row['unitPrice']),(40,120))
  self.assertEqual(row['unitCostSource'],'Saved manually')
  inputs=planning.input_rows(self.c)[0]
  self.assertEqual((inputs['Purchase_Cost'],inputs['Selling_Price']),(40,120))
  final=planning.final_rows(self.c)[0]
  self.assertEqual((final['unit_purchase_cost'],final['unit_selling_price']),(40,120))
  self.assertFalse(final['inventory_known'])
 def test_new_source_refresh_keeps_manual_prices(self):
  catalogue.sync(self.c,self.path);catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=150)],'EUR')
  self.data['skus'][0]['Prix_Achat']=200;self.seed();catalogue.sync(self.c,self.path)
  row=catalogue.listing(self.c,'EUR')['rows'][0]
  self.assertEqual(row['selling'],150);self.assertEqual(row['purchase'],90) # Latest supplier order, not SKU master.
 def test_forecast_rebuild_keeps_catalogue_tables(self):
  catalogue.sync(self.c,self.path);catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=150)],'EUR')
  database._create_schema(self.c)
  self.assertEqual(catalogue.listing(self.c,'EUR')['rows'][0]['selling'],150)
 def test_currency_is_not_silently_converted(self):
  catalogue.sync(self.c,self.path);catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=150)],'USD')
  self.assertEqual(catalogue.price_map(self.c,'EUR')[('P','B','M')]['selling'],100)
  self.assertEqual(catalogue.price_map(self.c,'USD')[('P','B','M')]['selling'],150)
 def test_article_pagination_keeps_all_colours_and_sizes(self):
  catalogue.sync(self.c,self.path)
  original=list(self.c.execute('SELECT * FROM catalogue_skus').fetchone())
  for sku,reference,color,size in [('second','P','RED','S'),('third','Q','BLUE','L')]:
   row=original.copy();row[:4]=[sku,reference,color,size]
   self.c.execute('INSERT INTO catalogue_skus VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',row)
  first=catalogue.listing(self.c,'EUR',limit=1,grouped=True)
  self.assertEqual(first['total'],2)
  self.assertEqual({r['sku'] for r in first['rows']},{'sku-P-B-M','second'})
  second=catalogue.listing(self.c,'EUR',offset=1,limit=1,grouped=True)
  self.assertEqual([r['reference'] for r in second['rows']],['Q'])
  searched=catalogue.listing(self.c,'EUR',search='RED',limit=1,grouped=True)
  self.assertEqual(len(searched['rows']),2)
  self.assertEqual(catalogue.listing(self.c,'EUR',search='absent',grouped=True)['rows'],[])
 def test_budget_draft_does_not_overwrite_catalogue(self):
  report=self.report();key=buying.identity(report['rows'][0])
  buying.simulate(report,[dict(id=key,unitPrice=999)],'forecast')
  self.assertEqual(catalogue.price_map(self.c,'EUR')[('P','B','M')]['selling'],100)
 def test_blank_saved_price_is_unknown_in_budget(self):
  catalogue.sync(self.c,self.path);catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=None)],'EUR')
  self.assertIsNone(self.report()['rows'][0]['unitPrice'])
 def test_cleared_catalogue_prices_do_not_return_from_old_forecast_inputs(self):
  import pandas as pd
  catalogue.sync(self.c,self.path)
  planning.save_inputs(self.c,[dict(Reference='P',Couleur='B',Taille='M',Selling_Price=500,Purchase_Cost=300)])
  catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=None,purchase=None)],'EUR')
  inputs=planning.input_rows(self.c)
  row=next(r for r in inputs if r['Reference']=='P')
  self.assertIsNone(row['Selling_Price']);self.assertIsNone(row['Purchase_Cost'])
  raw=pd.DataFrame([dict(Reference='P',Couleur='B',Taille='M',Selling_Price=700,Purchase_Cost=400,STOCK=2,CDE_four_qte=3)])
  planning.apply_input_rows(raw,inputs)
  self.assertTrue(pd.isna(raw.iloc[0].Selling_Price));self.assertTrue(pd.isna(raw.iloc[0].Purchase_Cost))
  self.assertEqual(raw.iloc[0].STOCK,2)
 def test_invalid_batch_is_atomic(self):
  catalogue.sync(self.c,self.path)
  with self.assertRaises(ValueError):catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=120),dict(sku='bad',selling=-1)],'EUR')
  self.assertEqual(catalogue.price_map(self.c,'EUR')[('P','B','M')]['selling'],100)
 def test_close_reopen_preserves_saved_prices(self):
  catalogue.sync(self.c,self.path);catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=120)],'EUR')
  path=self.path.parent/'saved.db';disk=sqlite3.connect(path);self.c.backup(disk);disk.close()
  reopened=sqlite3.connect(path)
  self.assertEqual(catalogue.price_map(reopened,'EUR')[('P','B','M')]['selling'],120);reopened.close()

if __name__=='__main__':unittest.main()
