import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
import api_server as api
from database import _create_persistent_tables,_create_schema
from recommendation_view import purchase_total,validate_edits

class RecommendationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db'
  c=sqlite3.connect(self.path);_create_persistent_tables(c);_create_schema(c)
  for size,quantity in [('S',10),('M',20)]:
   c.execute('INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,financial_note) VALUES(?,?,?,?,?,?,?)',('P','BLACK',size,quantity,quantity/2,quantity*2,'INVENTORY_UNKNOWN;COST_UNKNOWN;PRICE_UNKNOWN'))
  c.execute('INSERT INTO historical_demand(reference,couleur,taille,year_month,true_demand) VALUES(?,?,?,?,?)',('P','BLACK','S','2025-01',7))
  c.commit();c.close();self.mock=patch.object(api,'get_connection',lambda:sqlite3.connect(self.path));self.mock.start()
 def tearDown(self):self.mock.stop();self.tmp.cleanup()
 def get(self,scenario='base'):
  return api.get_recommendations(season=None,scenario=scenario,search=None,status=None,category=None)[0]
 def test_forecast_is_not_zero_when_purchase_is_unknown(self):
  r=self.get();self.assertEqual(r['currentScenarioTotal'],30);self.assertIsNone(r['purchaseTotals']['base'])
  self.assertTrue(all(s['recommended'] is None and s['finalQty'] is None for s in r['sizeBreakdown']))
  self.assertEqual(r['historicalSizes'],{'S':7});self.assertFalse(r['financialImpact']['complete'])
 def test_save_is_scenario_specific_and_preserves_forecasts(self):
  api.update_recommendation('P','BLACK',dict(scenario='base',sizeBreakdown=[dict(size='S',finalQty=4),dict(size='M',finalQty=6)],reason='Test'))
  r=self.get();self.assertEqual(r['purchaseTotals']['base'],10);self.assertEqual(r['currentScenarioTotal'],30)
  self.assertFalse(r['financialImpact']['complete'])
  self.assertIsNone(self.get('optimistic')['purchaseTotals']['optimistic'])
 def test_lock_idempotent_and_blocks_edits_then_unlocks(self):
  self.assertEqual(api.lock_recommendation('P','BLACK',{})['status'],'locked')
  self.assertEqual(api.lock_recommendation('P','BLACK',{})['status'],'locked')
  with self.assertRaises(HTTPException) as ex:api.update_recommendation('P','BLACK',dict(sizeBreakdown=[dict(size='S',finalQty=1)]))
  self.assertEqual(ex.exception.status_code,409)
  api.unlock_recommendation('P','BLACK',{})
  api.update_recommendation('P','BLACK',dict(sizeBreakdown=[dict(size='S',finalQty=1)]))
 def test_reset_removes_saved_overrides(self):
  api.update_recommendation('P','BLACK',dict(sizeBreakdown=[dict(size='S',finalQty=1)]))
  reset=next(r.endpoint for r in api.app.routes if getattr(r,'path','')=='/api/recommendations/{reference}/{couleur}/override')
  reset('P','BLACK','base');self.assertTrue(all(s['manualOverride'] is None for s in self.get()['sizeBreakdown']))
 def test_invalid_batch_is_atomic(self):
  with self.assertRaises(HTTPException):api.update_recommendation('P','BLACK',dict(sizeBreakdown=[dict(size='S',finalQty=1),dict(size='M',finalQty=-1)]))
  c=sqlite3.connect(self.path);self.assertEqual(c.execute('SELECT COUNT(*) FROM user_overrides').fetchone()[0],0);c.close()
 def test_invalid_and_duplicate_values(self):
  for value in (True,None,-1,float('nan')):
   with self.assertRaises(ValueError):validate_edits([dict(taille='S')],dict(sizeBreakdown=[dict(size='S',finalQty=value)]))
  with self.assertRaises(ValueError):validate_edits([dict(taille='S')],dict(sizeBreakdown=[dict(size='S',finalQty=1)]*2))
 def test_purchase_total_preserves_unknown(self):
  self.assertIsNone(purchase_total([dict(final_quantity=0),dict(final_quantity=None)]))

if __name__=='__main__':unittest.main()
