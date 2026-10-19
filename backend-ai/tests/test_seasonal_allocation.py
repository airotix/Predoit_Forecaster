import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import pandas as pd
import catalogue
import database
import operating_scope
import planning
import seasonal_allocation as allocation


class AllocationTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');database._create_schema(self.c);planning.ensure_schema(self.c);catalogue.ensure(self.c)
  self.plan=planning.save_season(self.c,dict(name='Winter',startDate='2026-10-01',endDate='2027-03-31',currency='EUR',budget=1000,targetMargin=40))
  scope=operating_scope.save(self.c,dict(brands=['DAYTONA73'],warehouseRoles={'CENTRAL':'primary'}),['DAYTONA73'],['CENTRAL'])
  self.lineage=dict(runId='run',freshRun='source',seasonId=self.plan['id'],plan=self.plan,forecastStart='2026-10',forecastEnd='2027-03',operatingScopeRevision=scope['revision'])
  self.c.execute("INSERT OR REPLACE INTO pipeline_metadata VALUES('lineage',?,'now')",(json.dumps(self.lineage),))
  for sku,ref,size,code,brand in [('a1','A','M','H26','DAYTONA73'),('a2','A','S','H26','DAYTONA73'),('b1','B','M','P27','DAYTONA73'),('c1','C','M','CORE','DAYTONA73'),('f1','F','M','FW27','DAYTONA73'),('x1','X','M','H26','OTHER')]:
   self.c.execute('INSERT INTO catalogue_skus VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(sku,ref,'BLACK',size,'Style '+ref,brand,'Jacket','Supplier',1,'source','now',json.dumps(dict(product={'saison':code}))))
  for ref,size,base in [('A','M',2.5),('A','S',0),('C','M',3),('F','M',0),('X','M',99)]:
   for m in pd.period_range('2026-10',periods=6,freq='M'):
    self.c.execute('INSERT INTO forecast_monthly(reference,couleur,taille,forecast_month,forecast_base,forecast_conservative,forecast_optimistic,season_booked) VALUES(?,?,?,?,?,?,?,?)',(ref,'BLACK',size,str(m),base,base/2,base*2,1 if ref=='A' and size=='M' and m.month==10 else 0))
  self.c.commit()
 def tearDown(self):self.c.close()
 def get(self,**kwargs):return allocation.listing(self.c,**kwargs)
 def test_codes_filter_articles_and_interval_sums_only_selected_months(self):
  result=self.get(start='2026-11',end='2026-12',codes=['H26'])
  self.assertEqual(result['total'],1);article=result['rows'][0]
  self.assertEqual(article['reference'],'A');self.assertEqual(article['forecast'],5)
  self.assertEqual(article['rows'][0]['booked'],0)
  self.assertEqual(self.get(start='2026-10',end='2026-10',codes=['H26'])['rows'][0]['forecast'],2.5)
 def test_missing_forecast_is_unknown_and_actual_zero_remains_zero(self):
  result=self.get(codes=['H26','P27','CORE','FW27'])
  by={r['reference']:r for r in result['rows']}
  self.assertIsNone(by['B']['forecast']);self.assertEqual(by['B']['missingVariants'],1)
  self.assertEqual(by['F']['forecast'],0);self.assertEqual(by['A']['rows'][1]['forecast'],0)
  self.assertIsNone(result['summary']['totalForecastUnits']);self.assertEqual(result['summary']['knownForecastUnits'],33)
  self.assertNotIn('X',by)
 def test_incomplete_monthly_series_does_not_become_full_interval_total(self):
  self.c.execute("DELETE FROM forecast_monthly WHERE reference='A' AND taille='M' AND forecast_month='2026-11'")
  result=self.get(codes=['H26'])['rows'][0]
  self.assertIsNone(result['forecast']);self.assertEqual(result['forecastedVariants'],1)
  self.assertEqual(result['knownForecast'],0)
 def test_outside_publication_and_changed_source_are_not_filled_with_zero(self):
  result=self.get(start='2027-04',end='2027-05',codes=['H26'])
  self.assertFalse(result['published']['matching']);self.assertIsNone(result['rows'][0]['forecast'])
  self.assertTrue(any('outside' in n for n in result['notices']))
  self.c.execute("UPDATE catalogue_skus SET source_run='next'")
  self.assertIsNone(self.get(codes=['H26'])['rows'][0]['forecast'])
 def test_saved_allocation_is_per_planning_season_and_does_not_change_forecasts(self):
  before=self.c.execute('SELECT SUM(forecast_base) FROM forecast_monthly').fetchone()[0]
  allocation.save(self.c,dict(startMonth='2026-10',endMonth='2026-11',codes=['H26']))
  result=self.get();self.assertTrue(result['saved']);self.assertEqual(result['allocation']['codes'],['H26']);self.assertEqual(result['rows'][0]['forecast'],5)
  planning.save_season(self.c,dict(name='Next',startDate='2027-04-01',endDate='2027-09-30',currency='EUR',budget=1000,targetMargin=40))
  self.assertFalse(self.get()['saved']);self.assertEqual(self.c.execute('SELECT SUM(forecast_base) FROM forecast_monthly').fetchone()[0],before)
 def test_duplicate_sku_identity_does_not_duplicate_forecast_or_split_article_page(self):
  row=list(self.c.execute("SELECT * FROM catalogue_skus WHERE sku='a1'").fetchone());row[0]='a-duplicate'
  self.c.execute('INSERT INTO catalogue_skus VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',row)
  result=self.get(codes=['H26'],limit=1)['rows'][0]
  self.assertEqual(result['forecast'],15);self.assertEqual(len(result['rows']),2)
  self.assertEqual(len(result['rows'][0]['skus']),2)
 def test_scenario_selection_and_invalid_filters(self):
  self.assertEqual(self.get(codes=['H26'],scenario='optimistic')['rows'][0]['forecast'],30)
  for fields in [dict(codes=['not-a-code']),dict(start='2026-10-01'),dict(end='2026-01'),dict(start='2026-01',end='2030-12'),dict(scenario='bad')]:
   with self.subTest(fields=fields),self.assertRaises(ValueError):self.get(**fields)
 def test_article_label_casing_uses_joolan_field_contract(self):
  self.c.execute("UPDATE catalogue_skus SET details=? WHERE reference='F'",(json.dumps(dict(product={'Saison':'RECONDUIT'})),))
  self.assertEqual(self.get(codes=['RECONDUIT'])['rows'][0]['reference'],'F')
 def test_removed_saved_code_does_not_prevent_loading_new_choices(self):
  allocation.save(self.c,dict(startMonth='2026-10',endMonth='2026-11',codes=['H26']))
  self.c.execute("UPDATE catalogue_skus SET current=0 WHERE reference='A'")
  result=self.get();self.assertEqual(result['allocation']['codes'],[])
  self.assertTrue(any('absent' in n for n in result['notices']))
 def test_api_get_save_and_invalid_selection(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'allocation.db';self.c.commit()
   copy=sqlite3.connect(path)
   try:self.c.backup(copy)
   finally:copy.close()
   app=FastAPI();allocation.install(app,lambda:sqlite3.connect(path))
   with TestClient(app) as client:
    self.assertEqual(client.get('/api/seasonal-allocation',params={'codes':json.dumps(['H26'])}).json()['rows'][0]['forecast'],15)
    self.assertEqual(client.put('/api/seasonal-allocation',json=dict(startMonth='2026-10',endMonth='2026-12',codes=['CORE'])).status_code,200)
    self.assertEqual(client.get('/api/seasonal-allocation').json()['allocation']['codes'],['CORE'])
    self.assertEqual(client.put('/api/seasonal-allocation',json=dict(startMonth='2026-10',endMonth='2026-12',codes=['bad'])).status_code,400)


if __name__=='__main__':unittest.main()
