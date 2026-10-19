import copy,json,unittest
import catalogue,historical_prices as h
import test_budgeting as fixtures


class AggregateTests(unittest.TestCase):
 def setUp(self):
  self.header=dict(Entete=1,Date='2026-05-01',Magasin='CENTRAL',Nature='COMMANDE',Statut=1,non_facturable=0,Devise='01')
  self.line=dict(Entete=1,Produit='P',Couleur='B',Taille='M',Nature='COMMANDE',Statut=1,Devise='01',Quantite=2,Prix_HT_Devise=100,Remise=10,Total_HT_Devise=180)
 def run_prices(self,lines=None,header=None):
  return h.aggregate({'1':header or self.header},lines or [self.line],{('P','B','M'):'sku'}, {'01':'EUR'},'2026-04-01','2026-09-30',['CENTRAL'])
 def test_net_weighted_mean_does_not_apply_discount_twice(self):
  extra={**self.line,'Quantite':1,'Prix_HT_Devise':150,'Remise':0,'Total_HT_Devise':150}
  result,_=self.run_prices([self.line,extra]);price=result[(('P','B','M'),'EUR')]
  self.assertEqual(price['price'],110);self.assertEqual(price['lines'],2);self.assertEqual(price['units'],3)
  self.assertEqual((price['minPrice'],price['maxPrice']),(90,150))
 def test_rejects_cancelled_unconfirmed_nonbillable_unknown_and_mismatched_data(self):
  for changes in [dict(Statut=0),dict(Statut=2),dict(Statut=None),dict(Devise='USD'),dict(Quantite=0),dict(Quantite=-1),dict(Prix_HT_Devise=None),dict(Remise=None),dict(Total_HT_Devise=999),dict(Taille='L')]:
   with self.subTest(changes=changes):self.assertEqual(self.run_prices([{**self.line,**changes}])[0],{})
  for changes in [dict(Statut=2),dict(non_facturable=1),dict(non_facturable=None),dict(Magasin='DEFECTUEUX'),dict(Date='2025-05-01')]:
   with self.subTest(header=changes):self.assertEqual(self.run_prices(header={**self.header,**changes})[0],{})
 def test_dates_are_inclusive_and_closed_orders_supply_price_evidence(self):
  for date in ('2026-04-01','2026-09-30'):
   self.assertTrue(self.run_prices(header={**self.header,'Date':date,'Statut':3})[0])


class HistoricalCatalogueTests(unittest.TestCase):
 setUp=fixtures.BudgetTests.setUp
 tearDown=fixtures.BudgetTests.tearDown
 seed=fixtures.BudgetTests.seed
 report=fixtures.BudgetTests.report
 def prepare(self):
  base=AggregateTests();base.setUp()
  self.data['negoce_entetes']=[base.header]
  self.data['negoce_lignes']=[{**base.line,'Prix_HT_Devise':150,'Remise':0,'Total_HT_Devise':300}]
  self.seed()
 def test_import_persists_provenance_and_flows_to_budget_after_refresh(self):
  self.prepare();summary=h.import_season(self.c,'2026-04-01','2026-09-30',self.path)
  self.assertEqual(summary['saved'],1)
  row=catalogue.listing(self.c,'EUR')['rows'][0]
  self.assertEqual(row['selling'],150);self.assertEqual(row['purchase'],90)
  legacy=json.loads(self.c.execute("SELECT value FROM planning_state WHERE key=?",('historical_price:sku-P-B-M:EUR',)).fetchone()[0])
  self.assertEqual(legacy['sourceRun'],self.rid)
  self.assertEqual(legacy['startDate'],'2026-04-01')
  catalogue.sync(self.c,self.path,force=True)
  self.assertEqual(catalogue.price_map(self.c,'EUR')[('P','B','M')]['selling'],150)
  self.assertEqual(self.report()['rows'][0]['unitPrice'],150)
  self.assertIn('Customer order',self.report()['rows'][0]['unitPriceSource'])
 def test_manual_prices_and_explicit_clears_are_preserved(self):
  self.prepare();catalogue.sync(self.c,self.path)
  for value in (200,None):
   catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=value)],'EUR')
   summary=h.import_season(self.c,'2026-04-01','2026-09-30',self.path)
   self.assertEqual(summary['preservedManual'],1);self.assertEqual(summary['saved'],0)
   self.assertEqual(catalogue.price_map(self.c,'EUR')[('P','B','M')]['selling'],value)
 def test_manual_update_replaces_historical_default_permanently(self):
  self.prepare();h.import_season(self.c,'2026-04-01','2026-09-30',self.path)
  catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',selling=175)],'EUR');catalogue.sync(self.c,self.path,force=True)
  row=catalogue.listing(self.c,'EUR')['rows'][0]
  self.assertEqual(row['selling'],175);self.assertEqual(row['sellingSource'],'manual');self.assertNotIn('historicalPrice',row)
 def test_period_must_precede_forecast(self):
  self.prepare()
  with self.assertRaises(ValueError):h.import_season(self.c,'2026-04-01','2026-10-01',self.path)
