import json,sqlite3,unittest
import pandas as pd
from database import _PIPELINE_TABLES_DDL,_insert_clients
from customer_coverage import report,repair_totals,subtract_months
import datetime as dt

class CoverageTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.executescript(_PIPELINE_TABLES_DDL)
  self.c.executescript('CREATE TABLE order_lines(payload TEXT); CREATE TABLE planning_state(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE planning_seasons(id TEXT PRIMARY KEY,payload TEXT);')
  plan=dict(id='winter',name='Winter',startDate='2026-10-01',endDate='2027-03-31')
  self.c.execute('INSERT INTO planning_state VALUES(?,?)',('active_season','winter'));self.c.execute('INSERT INTO planning_seasons VALUES(?,?)',('winter',json.dumps(plan)))
  self.c.execute('INSERT INTO pipeline_metadata VALUES(?,?,?)',('lineage',json.dumps(dict(freshReport=dict(exportedThrough='2026-10-07'))),''))
  for client,date,q,ref,order in [('A','2022-01-01',5,'P','1'),('A','2026-10-01',2,'P','2'),('A','2026-10-01',3,'Q','2'),('B','2025-05-01',3,'P','3'),('C','2020-01-01',10,'P','4'),('D','2026-10-01',0,'P','5'),('E','2027-01-01',4,'P','6')]:
   self.c.execute('INSERT INTO order_lines VALUES(?)',(json.dumps(dict(Client=client,Date_Commande=date,true_demand=q,Reference=ref,Reference_CDE=order)),))
  for client in 'ABCDE':self.c.execute('INSERT INTO clients(client_id,client_name,total_units,num_skus) VALUES(?,?,?,?)',(client,client,0,0))
 def tearDown(self):self.c.close()
 def test_repair_totals_uses_ledger_and_counts_distinct_products(self):
  repair_totals(self.c)
  self.assertEqual(self.c.execute("SELECT total_units,num_skus FROM clients WHERE client_id='A'").fetchone(),(10,2))
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0],7)
 def test_active_base_and_season_coverage_are_dated_not_visits(self):
  coverage=report(self.c)['coverage']
  self.assertEqual(coverage['activeCustomers'],2);self.assertEqual(coverage['orderedActiveCustomers'],1)
  self.assertEqual(coverage['orderingCoverage'],.5);self.assertEqual(coverage['seasonUnits'],5)
  customers={r['id']:r for r in report(self.c)['customers']}
  self.assertEqual(customers['A']['seasonOrderCount'],1)
  self.assertFalse(customers['C']['active']);self.assertFalse(customers['D']['active']);self.assertFalse(customers['E']['orderedInSeason'])
 def test_no_active_buyers_is_unknown_coverage(self):
  self.c.execute('DELETE FROM order_lines')
  self.assertIsNone(report(self.c)['coverage']['orderingCoverage'])
 def test_month_window_handles_leap_day(self):
  self.assertEqual(subtract_months(dt.date(2024,2,29),24),dt.date(2022,2,28))
 def test_future_loader_accepts_flattened_summary_columns(self):
  _insert_clients(self.c,pd.DataFrame([dict(Client='A',Nom='Customer A',true_demand_sum=123,Reference_nunique=7,year_month_nunique=4,Date_Commande_min='2025-01-01',Date_Commande_max='2026-01-01')]))
  self.assertEqual(self.c.execute("SELECT total_units,num_skus,active_months FROM clients WHERE client_id='A'").fetchone(),(123,7,4))

if __name__=='__main__':unittest.main()
