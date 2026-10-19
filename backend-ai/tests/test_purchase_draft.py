import copy,json,sqlite3,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
import database,planning,purchase_draft as draft,projection_detail
import test_buying

class PurchaseDraftTests(unittest.TestCase):
 def setUp(self):
  fixture=test_buying.BuyingTests();fixture.setUp();self.report=fixture.report;self.ident=fixture.key
  self.c=sqlite3.connect(':memory:');database._create_schema(self.c);planning.ensure_schema(self.c)
  self.c.execute('CREATE TABLE IF NOT EXISTS sku_locks(reference TEXT,couleur TEXT,locked INTEGER)')
  self.c.execute('CREATE TABLE IF NOT EXISTS user_overrides(reference TEXT,couleur TEXT,taille TEXT,override_qty REAL,updated_at TEXT,scenario TEXT,plan_id TEXT)')
  season=dict(id='winter',name='Winter',currency='EUR',budget=1000,targetMargin=40,startDate='2026-10-01',endDate='2027-03-31')
  self.c.execute('INSERT INTO planning_seasons VALUES(?,?)',('winter',json.dumps(season)))
  self.c.execute("INSERT INTO planning_state VALUES('active_season','winter')")
  self.lineage=dict(runId='forecast1',seasonId='winter',freshRun='source1',operatingScopeRevision=None)
  self.c.execute('INSERT OR REPLACE INTO pipeline_metadata(key,value) VALUES(?,?)',('lineage',json.dumps(self.lineage)))
  self.c.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,current_stock,pipeline_stock,available_inventory,unit_purchase_cost,unit_selling_price) VALUES('P','BLACK','M',20,10,30,2,8,10,30,100)")
  self.c.commit()
 def tearDown(self):self.c.close()
 def save(self,edits=None,selected=None,**updates):
  view=draft.view(self.c,self.report)
  body=dict(version=view['draft']['version'],forecastRun=view['draft']['forecastRun'],revision=view['revision'],edits=edits or [],selected=selected or [])
  body.update(updates)
  with self.c:return draft.store(self.c,self.report,body)
 def test_persistence_and_shared_quantities_prices_sellthrough(self):
  saved=self.save([dict(id=self.ident,quantity=7,unitCost=40,unitPrice=120,sellThrough=50,reason='Test')],[self.ident])
  loaded=draft.view(self.c,self.report)
  self.assertEqual(loaded['draft']['version'],1);self.assertEqual(loaded['draft']['selected'],[self.ident]);self.assertFalse(loaded['draft']['stale'])
  row=planning.final_rows(self.c)[0]
  self.assertEqual(row['final_quantity'],7);self.assertEqual(row['purchase_cost'],280);self.assertEqual(row['turnover'],420)
  self.assertEqual(row['turnover'],saved['rows'][0]['orderTurnover'])
  self.assertEqual(planning.final_rows(self.c,include_draft=False)[0]['final_quantity'],10)
 def test_default_pack_quantity_survives_handoff_without_manual_edit(self):
  self.report['rows'][0]['orderingRules']=dict(packSize=6)
  saved=self.save()
  self.assertEqual(saved['rows'][0]['quantity'],24)
  self.assertEqual(planning.final_rows(self.c)[0]['final_quantity'],24)
  self.assertEqual(planning.final_rows(self.c)[0]['purchase_cost'],saved['rows'][0]['orderCost'])
 def test_forecast_and_scenario_isolation_retains_old_draft(self):
  self.save([dict(id=self.ident,quantity=7)])
  self.assertEqual(draft.read(self.c,'optimistic')['version'],0)
  self.lineage['runId']='forecast2'
  self.c.execute('UPDATE pipeline_metadata SET value=? WHERE key=?',(json.dumps(self.lineage),'lineage'))
  self.assertEqual(draft.read(self.c,'base')['version'],0)
  self.assertEqual(self.c.execute("SELECT COUNT(*) FROM planning_state WHERE key LIKE 'purchase_draft:%'").fetchone()[0],1)
 def test_conflict_does_not_overwrite(self):
  self.save([dict(id=self.ident,quantity=7)])
  with self.assertRaisesRegex(ValueError,'another page'):self.save([dict(id=self.ident,quantity=9)],version=0)
  self.assertEqual(draft.read(self.c,'base')['edits'][0]['quantity'],7)
 def test_source_prices_and_currency_require_review(self):
  self.save([dict(id=self.ident,quantity=7,unitPrice=120,unitCost=35)])
  self.report['rows'][0]['unitPrice']=140
  self.assertTrue(draft.view(self.c,self.report)['draft']['stale'])
  self.report['summary']['currency']='USD';self.report['rows'][0]['unitCost']=None
  current=draft.view(self.c,self.report)
  self.assertTrue(current['draft']['currencyChanged']);self.assertNotIn('unitPrice',current['draft']['edits'][0])
  self.assertIsNone(current['rows'][0]['orderUnitCost'])
 def test_archives_versions_and_rejects_lock(self):
  self.save([dict(id=self.ident,quantity=7)])
  self.save([dict(id=self.ident,quantity=9)])
  self.assertEqual(self.c.execute("SELECT COUNT(*) FROM planning_state WHERE key LIKE '%:version:1'").fetchone()[0],1)
  self.c.execute("INSERT INTO sku_locks(reference,couleur,locked) VALUES('P','BLACK',1)");self.c.commit()
  with self.assertRaisesRegex(ValueError,'Unlock'):self.save([dict(id=self.ident,quantity=10)])
 def test_quote_price_matches_recommendation_finances(self):
  self.save([dict(id=self.ident,quantity=7,quoteId='0',reason='Confirmed')])
  self.assertEqual(planning.final_rows(self.c)[0]['purchase_cost'],280)
 def test_invalid_inputs_and_context_rejected(self):
  for edit in [dict(id=self.ident,quantity=1.2),dict(id=self.ident,quantity=-1),dict(id=self.ident,unitPrice=True),dict(id='outside',quantity=1)]:
   with self.assertRaises(ValueError):self.save([edit])
  with self.assertRaises(ValueError):self.save(selected=['outside'])
  with self.assertRaisesRegex(ValueError,'forecast changed'):self.save(forecastRun='old')
  with self.assertRaisesRegex(ValueError,'settings or forecast'):self.save(revision='old')
 def test_cleared_price_not_zero_and_whole_forecast_default(self):
  self.save([dict(id=self.ident,unitPrice=None)])
  row=planning.final_rows(self.c)[0]
  self.assertEqual(row['final_quantity'],20);self.assertIsNone(row['turnover'])
 def test_numeric_input_is_canonical_and_financial_rounding_matches(self):
  saved=self.save([dict(id=self.ident,quantity='3',unitCost='1.005',unitPrice='2.005',sellThrough='50')])
  loaded=draft.read(self.c,'base')['edits'][0]
  self.assertIsInstance(loaded['quantity'],float)
  row=planning.final_rows(self.c)[0]
  self.assertEqual(row['purchase_cost'],saved['rows'][0]['orderCost'])
  self.assertEqual(row['turnover'],saved['rows'][0]['orderTurnover'])
  self.assertEqual(round(row['turnover']-row['cost_of_sales'],2),saved['rows'][0]['orderGrossMargin'])

class ProjectionTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');database._create_schema(self.c)
  self.c.executemany('INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,current_stock,pipeline_stock,confirmed_delivered,net_to_order_base) VALUES(?,?,?,?,?,?,?,?,?,?)',[
   ('P','B','30',2.75,1.25,4.5,3,None,100,None),('P','B','UNIQUE',1.5,.5,2.5,None,2,50,None)])
 def tearDown(self):self.c.close()
 def test_scenarios_fractional_sizes_unknowns_and_no_historical_subtraction(self):
  for sc,expected in [('base',2.75),('conservative',1.25),('optimistic',4.5)]:
   result=projection_detail.detail(self.c,'P',sc)
   self.assertEqual(result['colorVariants'][0]['recommendedQty']['30'],expected)
   self.assertIn('UNIQUE',result['colorVariants'][0]['recommendedQty'])
   self.assertIsNone(result['stockSummary']['stockReel']);self.assertIsNone(result['stockSummary']['total'])
   self.assertIsNone(result['colorVariants'][0]['totalDeLeStock']['30'])
  self.c.execute('UPDATE recommendations SET current_stock=3,pipeline_stock=2')
  self.assertEqual(projection_detail.detail(self.c,'P')['stockSummary']['total'],10)
 def test_error_statuses(self):
  for ref,sc,status in [('P','bad',400),('missing','base',404)]:
   with self.assertRaises(HTTPException) as result:projection_detail.detail(self.c,ref,sc)
   self.assertEqual(result.exception.status_code,status)

class DraftApiTests(unittest.TestCase):
 def setUp(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  import budget_routes
  fixture=PurchaseDraftTests();fixture.setUp()
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'draft.db'
  c=sqlite3.connect(self.path);fixture.c.backup(c);c.close();fixture.tearDown()
  self.report=fixture.report;self.ident=fixture.ident
  self.report_patch=patch('budgeting.build_report',side_effect=lambda *a,**k:copy.deepcopy(self.report));self.report_patch.start()
  self.sync_patch=patch('catalogue.sync',return_value={});self.sync_patch.start()
  app=FastAPI();budget_routes.install(app,self.connect);self.client=TestClient(app)
 def connect(self):return sqlite3.connect(self.path)
 def tearDown(self):self.client.close();self.report_patch.stop();self.sync_patch.stop();self.tmp.cleanup()
 def test_persist_review_conflict_and_immutable_snapshot(self):
  current=self.client.get('/api/budget/draft').json()
  body=dict(scenario='base',version=0,forecastRun='forecast1',revision=current['revision'],
            edits=[dict(id=self.ident,quantity=7,quoteId='0',reason='Confirmed supplier quote')],selected=[self.ident])
  saved=self.client.put('/api/budget/draft',json=body);self.assertEqual(saved.status_code,200,saved.text)
  self.assertEqual(self.client.get('/api/budget/draft').json()['rows'][0]['quantity'],7)
  self.assertEqual(self.client.put('/api/budget/draft',json=body).status_code,409)
  review_body=dict(scenario='base',version=1,forecastRun='forecast1')
  reviewed=self.client.post('/api/budget/draft/review',json=review_body);self.assertEqual(reviewed.status_code,200,reviewed.text)
  self.assertEqual(reviewed.json()['orders'][0]['orderCost'],280)
  self.assertEqual(reviewed.json()['draftVersion'],1)
  body['version']=1;body['edits'][0]['quantity']=8
  self.assertEqual(self.client.put('/api/budget/draft',json=body).status_code,200)
  self.assertEqual(self.client.post('/api/budget/draft/review',json=review_body).status_code,409)
  self.assertEqual(self.client.get('/api/budget/reviews').json()[0]['orders'][0]['quantity'],7)
 def test_missing_inputs_cannot_be_validated_and_failure_is_atomic(self):
  self.report['rows'][0]['stock']=None
  current=self.client.get('/api/budget/draft').json()
  body=dict(scenario='base',version=0,forecastRun='forecast1',revision=current['revision'],
            edits=[dict(id=self.ident,quantity=7,quoteId='0',reason='Test')],selected=[self.ident])
  self.assertEqual(self.client.put('/api/budget/draft',json=body).status_code,200)
  self.assertEqual(self.client.post('/api/budget/draft/review',json=dict(scenario='base',version=1,forecastRun='forecast1')).status_code,409)
  self.assertEqual(self.client.get('/api/budget/reviews').json(),[])
 def test_recommendation_edits_share_the_draft_and_detect_conflicts(self):
  import api_server
  c=self.connect();c.execute('CREATE TABLE joolan_state(key TEXT PRIMARY KEY,value TEXT)');c.execute("INSERT INTO joolan_state VALUES('source_policy','fresh_only')");c.commit();c.close()
  body=dict(scenario='base',draftVersion=0,forecastRun='forecast1',sizeBreakdown=[dict(size='M',finalQty=7)],reason='Demand adjustment')
  with patch.object(api_server,'get_connection',self.connect):
   saved=api_server.update_recommendation('P','BLACK',body)
   self.assertEqual(saved['draftVersion'],1)
   with self.assertRaises(HTTPException) as result:api_server.update_recommendation('P','BLACK',body)
   self.assertEqual(result.exception.status_code,409)
  self.assertEqual(self.client.get('/api/budget/draft').json()['rows'][0]['quantity'],7)
