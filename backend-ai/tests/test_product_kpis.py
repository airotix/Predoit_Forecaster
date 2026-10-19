import sqlite3
import unittest
from product_kpis import attach_history,recent_size_history,install

class ProductKPITests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:',check_same_thread=False)
  self.c.executescript('CREATE TABLE historical_demand(reference TEXT,couleur TEXT,taille TEXT,year_month TEXT,true_demand REAL); CREATE TABLE pipeline_metadata(key TEXT,value TEXT); CREATE TABLE order_lines(payload TEXT);')
  self.c.executemany('INSERT INTO historical_demand VALUES(?,?,?,?,?)',[
   ('P','BLACK','S','2025-10',12),('P','BLACK','S','2026-01',8.5),('P','BLACK','M','2026-10',10),('P','RED','S','2026-01',100)])
  self.c.execute('INSERT INTO pipeline_metadata VALUES(?,?)',('lineage','{"cutoff":"2026-09","forecastStart":"2026-10","forecastEnd":"2027-03","freshReport":{"exportedThrough":"2026-10-07"},"demandDefinition":"Booked orders"}'))
 def tearDown(self):self.c.close()
 def test_history_and_forecast_are_separate_and_sizes_sum_to_history(self):
  p=attach_history(self.c,[dict(skuId='P|BLACK',forecastUnits=999)])[0]
  self.assertEqual(p['historicalDemand'],30.5);self.assertEqual(p['totalUnitsSold'],30.5)
  self.assertEqual(p['forecastUnits'],999);self.assertEqual(p['sizeBreakdown'],{'M':10,'S':20.5})
  self.assertEqual(sum(p['sizeBreakdown'].values()),p['historicalDemand'])
  self.assertEqual(p['trainingCutoff'],'2026-09');self.assertEqual(p['historyEnd'],'2026-10')
 def test_missing_history_is_unknown_not_zero(self):
  p=attach_history(self.c,[dict(skuId='NEW|WHITE',forecastUnits=50)])[0]
  self.assertIsNone(p['historicalDemand']);self.assertEqual(p['sizeBreakdown'],{})
 def test_colour_scope_is_not_combined(self):
  p=attach_history(self.c,[dict(skuId='P|RED',forecastUnits=1)])[0]
  self.assertEqual(p['historicalDemand'],100)
 def test_recorded_zero_is_distinct_from_unknown(self):
  self.c.execute('INSERT INTO historical_demand VALUES(?,?,?,?,?)',('ZERO','BLACK','S','2026-01',0))
  p=attach_history(self.c,[dict(skuId='ZERO|BLACK',forecastUnits=5)])[0]
  self.assertEqual(p['historicalDemand'],0);self.assertEqual(p['sizeBreakdown'],{'S':0})

 def test_chart_uses_only_the_six_complete_months_before_forecast(self):
  self.c.executemany('INSERT INTO historical_demand VALUES(?,?,?,?,?)',[
   ('P','BLACK','S','2026-03',900),('P','BLACK','S','2026-04',4),
   ('P','BLACK','M','2026-09',7),('P','BLACK','M','2026-09',2),
   ('P','BLACK','XL','2026-11',800),('P','RED','S','2026-04',600)])
  chart=recent_size_history(self.c,'P','BLACK')
  self.assertEqual(chart['startDate'],'2026-04-01');self.assertEqual(chart['endDate'],'2026-09-30')
  self.assertEqual(chart['sizeBreakdown'],{'M':9,'S':4});self.assertEqual(chart['totalUnits'],13)
  self.assertGreater(attach_history(self.c,[dict(skuId='P|BLACK')])[0]['historicalDemand'],13)

 def test_recent_window_crosses_year_boundary_and_excludes_the_forecast_month(self):
  self.c.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",('{"forecastStart":"2026-03"}',))
  self.c.executemany('INSERT INTO historical_demand VALUES(?,?,?,?,?)',[
   ('P','BLACK','M','2025-08',900),('P','BLACK','M','2025-09',2),('P','BLACK','L','2026-02',3),('P','BLACK','XL','2026-03',700)])
  chart=recent_size_history(self.c,'P','BLACK')
  self.assertEqual(chart['startDate'],'2025-09-01');self.assertEqual(chart['endDate'],'2026-02-28')
  self.assertEqual(chart['sizeBreakdown'],{'L':3,'M':2,'S':20.5})

 def test_no_recent_history_does_not_fall_back_to_older_history(self):
  chart=recent_size_history(self.c,'P','BLACK')
  self.assertEqual(chart['sizeBreakdown'],{});self.assertEqual(chart['totalUnits'],0)
  self.c.execute('INSERT INTO historical_demand VALUES(?,?,?,?,?)',('P','BLACK','XL','2026-06',0))
  self.assertEqual(recent_size_history(self.c,'P','BLACK')['sizeBreakdown'],{'XL':0})

 def test_missing_or_invalid_forecast_start_is_explicit(self):
  for value in ['{}','{"forecastStart":"bad"}']:
   self.c.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",(value,))
   with self.assertRaises(ValueError):recent_size_history(self.c,'P','BLACK')

 def test_http_query_preserves_colour_slashes_and_validates_inputs(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  class Connection:
   def __getattr__(inner,name):return getattr(self.c,name)
   def close(inner):pass
  self.c.execute('INSERT INTO historical_demand VALUES(?,?,?,?,?)',('P','BLUE/WHITE','M','2026-06',3))
  app=FastAPI();install(app,Connection);client=TestClient(app)
  response=client.get('/api/products/size-history',params=dict(reference='P',color='BLUE/WHITE'))
  self.assertEqual(response.status_code,200);self.assertEqual(response.json()['sizeBreakdown'],{'M':3})
  self.assertEqual(client.get('/api/products/size-history',params=dict(reference='',color='BLACK')).status_code,422)
  self.c.execute("UPDATE pipeline_metadata SET value='{}' WHERE key='lineage'")
  self.assertEqual(client.get('/api/products/size-history',params=dict(reference='P',color='BLACK')).status_code,409)

if __name__=='__main__':unittest.main()
