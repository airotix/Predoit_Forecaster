import datetime as dt
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import automatic_forecast as auto
import database,fresh_joolan as fresh,joolan,operating_scope,server_credentials
import test_fresh_joolan as fixtures

class CredentialTests(unittest.TestCase):
 def test_file_settings_quotes_no_expansion_and_env_override(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'.env';path.write_text('# comment\nexport JOOLAN_API_KEY="literal$KEY#value"\nJOOLAN_ENSEIGNE=legend73 # comment\nNEXT_PUBLIC_KEY=ignored\n')
   values=server_credentials.settings(path,{})
   self.assertEqual(values,{'JOOLAN_API_KEY':'literal$KEY#value','JOOLAN_ENSEIGNE':'legend73'})
   self.assertEqual(server_credentials.settings(path,{'JOOLAN_API_KEY':'process'})['JOOLAN_API_KEY'],'process')
 def test_date_validation(self):
  today=dt.date(2026,10,14)
  self.assertEqual(auto.dates('2026-10-01','2027-03-31',today),('2026-10-01','2027-03-31','2026-10-14'))
  for start,end in [('2026-10-02','2027-03-31'),('2026-10-01','2027-03-15'),('2026-09-01','2027-03-31'),('2026-10-01','2029-03-31')]:
   with self.subTest(start=start,end=end),self.assertRaises(ValueError):auto.dates(start,end,today)

class AutomaticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.path=self.base/'source.db';self.live=self.base/'live.db'
  c=self.connection();database._create_persistent_tables(c);database._create_schema(c);joolan.ensure_joolan_schema(c)
  operating_scope.save(c,dict(brands=['DAYTONA73'],warehouseRoles={'WH':'primary'}),['DAYTONA73'],['WH']);c.close()
  self.data=fixtures.fixture();self.data['produits'][0]['Marque']='DAYTONA73'
  fixtures.FakeClient.data=self.data;fixtures.FakeClient.fail_after_page=False
  self.stock=[dict(Magasin='WH',Produit='P',Couleur='B',Taille='M',En_Stock=3,Disponible=3,En_Reservation=0)]
  self.credentials=patch.object(server_credentials,'credentials',return_value=('secret-never-store','legend73'));self.credentials.start()
  self.clock=patch.object(auto,'dates',return_value=('2026-10-01','2027-03-31','2026-10-14'));self.clock.start()
 def tearDown(self):self.clock.stop();self.credentials.stop();self.tmp.cleanup()
 def connection(self):return sqlite3.connect(self.live)
 def create(self):
  c=self.connection()
  try:return auto.create(c,'2026-10-01','2027-03-31',self.path)
  finally:c.close()
 def export(self,rid,key,path=None,reconcile=False):fresh.run_export(rid,key,path,fixtures.FakeClient,lambda k,c:self.stock,reconcile)
 def publish(self):
  c=self.connection();state=dict(c.execute('SELECT key,value FROM joolan_state'))
  from planning import active_plan
  plan=active_plan(c)
  with c:c.execute("INSERT OR REPLACE INTO pipeline_metadata(key,value) VALUES('lineage',?)",(json.dumps(dict(runId='published',freshRun=state['fresh_run'],seasonId=plan['id'],createdAt=fresh.now())),))
  c.close()
 def status(self,jid):
  c=fresh.connect(self.path)
  try:return auto.read(c,jid)
  finally:c.close()
 def test_end_to_end_export_audit_activation_and_publication_without_key_storage(self):
  job=self.create();auto.execute(job['id'],self.connection,self.path,self.export,self.publish)
  result=self.status(job['id']);self.assertEqual(result['status'],'complete',result)
  self.assertEqual(result['forecastRun'],'published')
  c=fresh.connect(self.path)
  report=json.loads(c.execute('SELECT report FROM runs').fetchone()[0]);self.assertTrue(report['exportAudit']['allComplete'])
  self.assertEqual(len(report['exportAudit']['tables']),len(fresh.REQUIRED_TABLES))
  self.assertNotIn('secret-never-store',''.join(c.iterdump()));c.close()
  self.assertNotIn('rollback',auto.public(result));self.assertNotIn('scope',auto.public(result))
 def test_duplicate_job_rejected(self):
  self.create()
  with self.assertRaisesRegex(ValueError,'already running'):self.create()
 def test_quota_wait_resumes_same_run_and_saved_pages(self):
  fixtures.FakeClient.fail_after_page=True;waits=[]
  job=self.create();auto.execute(job['id'],self.connection,self.path,self.export,self.publish,sleep=waits.append,retry_seconds=1)
  result=self.status(job['id']);self.assertEqual(result['status'],'complete',result);self.assertEqual(waits,[1])
  c=fresh.connect(self.path);self.assertEqual(c.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1);c.close()
 def test_transient_connection_failure_retries_without_key_entry(self):
  waits=[];calls=[]
  class Interrupted(fixtures.FakeClient):
   def query(client,sql):
    if not calls:calls.append(True);raise fresh.ExportError('Connection failed or timed out.')
    return super().query(sql)
  def export(rid,key,path=None,reconcile=False):fresh.run_export(rid,key,path,Interrupted,lambda k,c:self.stock,reconcile)
  job=self.create();auto.execute(job['id'],self.connection,self.path,export,self.publish,sleep=waits.append)
  self.assertEqual(self.status(job['id'])['status'],'complete');self.assertEqual(waits,[30])
 def test_scope_change_does_not_start_a_different_export(self):
  job=self.create();c=self.connection()
  operating_scope.save(c,dict(brands=['OTHER'],warehouseRoles={'WH':'primary'}),['OTHER'],['WH']);c.close()
  auto.execute(job['id'],self.connection,self.path,self.export,self.publish)
  result=self.status(job['id']);self.assertEqual(result['status'],'paused');self.assertIsNone(result['runId'])
 def test_busy_guard_only_applies_to_its_serving_database(self):
  self.create();c=self.connection()
  self.assertTrue(auto.busy(self.path,c));c.close()
  other=sqlite3.connect(':memory:')
  self.assertFalse(auto.busy(self.path,other));other.close()
 def test_failed_forecast_restores_previous_source_and_active_season(self):
  c=self.connection()
  with c:
   c.execute("INSERT INTO joolan_state VALUES('fresh_run','previous')")
   c.execute("INSERT INTO planning_state VALUES('active_season','previous-season')")
  c.close();job=self.create()
  def fail():raise ValueError('Forecast failed')
  auto.execute(job['id'],self.connection,self.path,self.export,fail)
  result=self.status(job['id']);self.assertEqual(result['status'],'paused',result)
  c=self.connection();self.assertEqual(dict(c.execute('SELECT key,value FROM joolan_state'))['fresh_run'],'previous')
  self.assertEqual(c.execute("SELECT value FROM planning_state WHERE key='active_season'").fetchone()[0],'previous-season');c.close()
 def test_unavailable_env_fails_before_creating_job(self):
  with patch.object(server_credentials,'credentials',side_effect=ValueError('Missing key')):
   with self.assertRaisesRegex(ValueError,'Missing key'):self.create()
 def test_removed_credentials_pause_worker_with_readable_error(self):
  job=self.create()
  with patch.object(server_credentials,'credentials',side_effect=ValueError('Missing key')):
   auto.execute(job['id'],self.connection,self.path,self.export,self.publish)
  result=self.status(job['id'])
  self.assertEqual(result['status'],'paused');self.assertEqual(result['error'],'Missing key')
 def test_live_reconciliation_discovers_and_removes_incomplete_saved_table(self):
  job=self.create();rid=fresh.create_run(dict(enseigne='legend73',documentType='COMMANDE',throughDate='2026-10-14',brands=['DAYTONA73'],warehouses=['WH']),self.path)
  self.export(rid,'test',self.path,True)
  c=fresh.connect(self.path);c.execute("DELETE FROM records WHERE run_id=? AND dataset='negoce_lignes' AND record_key='[0]'",(rid,));c.commit()
  config=json.loads(c.execute('SELECT config FROM runs WHERE id=?',(rid,)).fetchone()[0])
  schema=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='schema'",(rid,)).fetchone()[0])['tables']
  with self.assertRaisesRegex(ValueError,'automatic repair'):fresh.reconcile_exports(c,rid,fixtures.FakeClient(),config,schema)
  self.assertIsNone(c.execute("SELECT 1 FROM datasets WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchone());c.close()
 def test_resume_repairs_a_table_marked_complete_with_missing_rows(self):
  rid=fresh.create_run(dict(enseigne='legend73',documentType='COMMANDE',throughDate='2026-10-14',brands=['DAYTONA73'],warehouses=['WH']),self.path)
  self.export(rid,'test',self.path,True)
  c=fresh.connect(self.path)
  with c:c.execute("DELETE FROM records WHERE run_id=? AND dataset='negoce_lignes' AND record_key='[0]'",(rid,))
  fresh.update(c,rid,status='queued');c.close();self.export(rid,'test',self.path,True)
  c=fresh.connect(self.path)
  self.assertEqual(c.execute('SELECT status FROM runs WHERE id=?',(rid,)).fetchone()[0],'validated')
  self.assertEqual(c.execute("SELECT COUNT(*) FROM records WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchone()[0],25);c.close()
 def test_reconciliation_rejects_fields_missing_from_saved_records(self):
  rid=fresh.create_run(dict(enseigne='legend73',documentType='COMMANDE',throughDate='2026-10-14',brands=['DAYTONA73'],warehouses=['WH']),self.path)
  self.export(rid,'test',self.path,True)
  c=fresh.connect(self.path)
  for record_key,payload in c.execute("SELECT record_key,payload FROM records WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchall():
   row=json.loads(payload);row.pop('Quantite_Livree');c.execute("UPDATE records SET payload=? WHERE run_id=? AND dataset='negoce_lignes' AND record_key=?",(json.dumps(row),rid,record_key))
  c.commit()
  config=json.loads(c.execute('SELECT config FROM runs WHERE id=?',(rid,)).fetchone()[0])
  schema=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='schema'",(rid,)).fetchone()[0])['tables']
  with self.assertRaisesRegex(ValueError,'automatic repair'):fresh.reconcile_exports(c,rid,fixtures.FakeClient(),config,schema)
  c.close()
 def test_new_primary_key_tail_extends_verified_history_without_deleting_it(self):
  rid=fresh.create_run(dict(enseigne='legend73',documentType='COMMANDE',throughDate='2026-10-14',brands=['DAYTONA73'],warehouses=['WH']),self.path)
  self.export(rid,'test',self.path,True);c=fresh.connect(self.path)
  meta=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchone()[0]);meta['where']='old-bounded'
  with c:c.execute("UPDATE datasets SET metadata=? WHERE run_id=? AND dataset='negoce_lignes'",(json.dumps(meta),rid))
  self.data['negoce_lignes'].append({**self.data['negoce_lignes'][0],'Ligne':25})
  client=fixtures.FakeClient()
  client.count=lambda table,where='':25 if table=='negoce_lignes' and where=='old-bounded' else len(self.data[table])
  config=json.loads(c.execute('SELECT config FROM runs WHERE id=?',(rid,)).fetchone()[0]);schema=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='schema'",(rid,)).fetchone()[0])['tables']
  with self.assertRaisesRegex(ValueError,'automatic repair'):fresh.reconcile_exports(c,rid,client,config,schema)
  self.assertEqual(c.execute("SELECT COUNT(*) FROM records WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchone()[0],25)
  extended=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchone()[0])
  self.assertEqual(extended['expected'],26);self.assertFalse(extended['complete'])
  fresh.export_table(c,rid,client,'negoce_lignes',config)
  self.assertEqual(c.execute("SELECT COUNT(*) FROM records WHERE run_id=? AND dataset='negoce_lignes'",(rid,)).fetchone()[0],26)
  self.assertTrue(fresh.reconcile_exports(c,rid,client,config,schema)['allComplete']);c.close()
 def test_new_period_retains_verified_field_mappings_without_copying_budget(self):
  from planning import save_season,active_plan
  from budgeting import save_settings,settings
  c=self.connection()
  save_season(c,dict(name='Earlier',startDate='2026-04-01',endDate='2026-09-30',currency='EUR',budget=1000,targetMargin=40))
  save_settings(c,dict(costBasisVerified=True,tariffVerified=True,poCostsVerified=True,budgetConfigured=True))
  c.close();job=self.create();auto.execute(job['id'],self.connection,self.path,self.export,self.publish)
  self.assertEqual(self.status(job['id'])['status'],'complete')
  c=self.connection();configured,plan=settings(c)
  self.assertTrue(configured['costBasisVerified']);self.assertTrue(configured['tariffVerified'])
  self.assertFalse(configured['budgetConfigured']);self.assertEqual(plan['budget'],0)
  self.assertEqual(active_plan(c)['startDate'],'2026-10-01');c.close()
