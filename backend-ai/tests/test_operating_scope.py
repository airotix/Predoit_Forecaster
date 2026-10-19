import csv,json,sqlite3,unittest
from unittest.mock import patch
import operating_scope as scope
import database,budgeting,fresh_joolan as fresh
import test_fresh_joolan as fixtures
import test_budgeting as budget_fixtures

class ScopeTests(unittest.TestCase):
 setUp=fixtures.FreshTests.setUp
 tearDown=fixtures.FreshTests.tearDown
 export=fixtures.FreshTests.export
 def test_roles_cannot_pool_faulty_clearance_or_consignment_into_primary(self):
  selected=scope.save(self.c,dict(brands=['DAYTONA73'],warehouseRoles={'CENTRAL':'primary','DESTOCK_VD':'clearance','DEFECTUEUX':'faulty','CUSTOMER':'consignment'}),['DAYTONA73'],['CENTRAL','DESTOCK_VD','DEFECTUEUX','CUSTOMER'])
  self.assertEqual(scope.primary(selected),['CENTRAL'])
  for w in ('DESTOCK_VD','DEFECTUEUX','CUSTOMER'):self.assertFalse(scope.eligible_order(selected,w))
  with self.assertRaises(ValueError):scope.save(self.c,dict(brands=['DAYTONA73'],warehouseRoles={'CENTRAL':'primary','DEFECTUEUX':'primary'}),['DAYTONA73'],['CENTRAL','DEFECTUEUX'])
 def test_revision_survives_reload_and_changes_only_with_rules(self):
  data=dict(brands=['A'],warehouseRoles={'WH':'primary'})
  first=scope.save(self.c,data,['A','B'],['WH'])
  self.assertEqual(first['revision'],scope.save(self.c,data,['A','B'],['WH'])['revision'])
  self.assertEqual(scope.read(self.c)['brands'],['A'])
  second=scope.save(self.c,{**data,'brands':['B']},['A','B'],['WH'])
  self.assertNotEqual(first['revision'],second['revision'])
 def test_budget_uses_primary_and_global_brands_even_with_old_season_settings(self):
  import planning
  planning.save_season(self.c,dict(name='Test',startDate='2024-02-01',endDate='2024-07-31',currency='EUR',budget=100,targetMargin=40))
  scope.save(self.c,dict(brands=['A'],warehouseRoles={'CENTRAL':'primary','CUSTOMER':'consignment'}),['A'],['CENTRAL','CUSTOMER'])
  config,_=budgeting.settings(self.c)
  self.assertEqual(config['brands'],['A']);self.assertEqual(config['warehouses'],['CENTRAL'])
  with self.assertRaises(ValueError):budgeting.save_settings(self.c,dict(warehouses=['CUSTOMER']))
 def test_scoped_pipeline_filters_brands_and_transfer_stores_keeps_missing_stock_unknown(self):
  self.config['warehouses']=['WH','CUSTOMER']
  self.data['produits'][0]['Marque']='A'
  self.data['produits'].append({**self.data['produits'][0],'Produit':'LEGACY','Marque':'OLD'})
  self.data['skus'].append({**self.data['skus'][0],'Produit':'LEGACY','Sku':'SKU2'})
  self.data['negoce_lignes'].append({**self.data['negoce_lignes'][0],'Ligne':999,'Produit':'LEGACY'})
  self.data['negoce_entetes'][0]['Magasin']='CUSTOMER'
  self.stock.append({**self.stock[0],'Magasin':'CUSTOMER','Disponible':99})
  rid,run=self.export();self.assertEqual(run['status'],'validated')
  fresh.activate(rid,self.c,self.path)
  scope.save(self.c,dict(brands=['A'],warehouseRoles={'WH':'primary','CUSTOMER':'consignment'}),['A','OLD'],['WH','CUSTOMER'])
  output=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
  with open(output,encoding='utf-8') as stream:records=list(csv.DictReader(stream))
  self.assertEqual(len(records),24)
  self.assertTrue(all(r['Reference']=='P' and r['Magasin']=='WH' for r in records))
  self.assertTrue(all(r['STOCK']=='3.0' for r in records))
 def test_publication_after_scope_change_preserves_previous_forecast(self):
  database._create_schema(self.c)
  self.c.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base) VALUES('P','B','M',123)");self.c.commit()
  scope.save(self.c,dict(brands=['A'],warehouseRoles={'WH':'primary'}),['A'],['WH'])
  with patch.object(database,'DB_FILE',self.serving_path),patch.object(database,'get_connection',lambda:sqlite3.connect(self.serving_path)):
   with self.assertRaisesRegex(ValueError,'Business scope changed'):
    database.populate_database(dict(lineage=dict(source='fresh',freshRun='run',operatingScopeRevision='old')))
  self.assertEqual(self.c.execute('SELECT forecast_base FROM recommendations').fetchone()[0],123)

class ScopeBalanceTests(unittest.TestCase):
 setUp=budget_fixtures.BudgetTests.setUp
 tearDown=budget_fixtures.BudgetTests.tearDown
 seed=budget_fixtures.BudgetTests.seed
 def test_available_is_not_hidden_just_because_physical_is_unknown(self):
  result=scope.balances(self.c,self.path)
  row=next(r for r in result['balances'] if r['warehouse']=='CENTRAL')
  self.assertIsNone(row['physical']);self.assertEqual(row['available'],2)
 def test_customer_master_codes_can_be_classified_without_fabricating_stock(self):
  self.data['magasins']=[dict(Magasin='CUSTOMER_VIRTUAL')];self.seed()
  result=scope.balances(self.c,self.path)
  self.assertIn('CUSTOMER_VIRTUAL',result['warehouses'])
  row=next(r for r in result['balances'] if r['warehouse']=='CUSTOMER_VIRTUAL')
  self.assertEqual(row['role'],'unclassified');self.assertIsNone(row['physical']);self.assertIsNone(row['available'])
 def test_balances_preserve_negative_available_and_flag_duplicate_rows(self):
  self.data['inventory'][0].update(En_Stock=3,Disponible=-2);self.seed()
  result=scope.balances(self.c,self.path)
  row=next(r for r in result['balances'] if r['warehouse']=='CENTRAL')
  self.assertEqual(row['available'],-2)
  self.data['inventory'].append(self.data['inventory'][0].copy());self.seed()
  result=scope.balances(self.c,self.path)
  row=next(r for r in result['balances'] if r['warehouse']=='CENTRAL')
  self.assertEqual(row['invalidRecords'],1);self.assertIsNone(row['available'])
 def test_saved_scope_blocks_stale_insights_but_settings_and_scope_stay_available(self):
  import api_server
  from fastapi.testclient import TestClient
  path=self.path.parent/'api.db';disk=sqlite3.connect(path);self.c.backup(disk);disk.close()
  with patch.object(api_server,'get_connection',lambda:sqlite3.connect(path)),patch.object(fresh,'SOURCE_DB',self.path),TestClient(api_server.app) as client:
   response=client.put('/api/operating-scope',json=dict(brands=['DAYTONA73'],warehouseRoles={'CENTRAL':'primary','DEFECTUEUX':'faulty'}))
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(client.get('/api/dashboard').status_code,409)
   self.assertEqual(client.get('/api/operating-scope').status_code,200)
   config=client.get('/api/budget/options').json()['settings']
   self.assertEqual(config['warehouses'],['CENTRAL'])
   denied=client.put('/api/operating-scope',json=dict(brands=['DAYTONA73'],warehouseRoles={'CENTRAL':'primary','DEFECTUEUX':'primary'}))
   self.assertEqual(denied.status_code,400)

if __name__=='__main__':unittest.main()
