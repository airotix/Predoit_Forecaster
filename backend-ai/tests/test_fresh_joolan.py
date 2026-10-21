"""Fresh-only integration tests. No network, real credentials or production data."""
import copy
import csv
import datetime as dt
import json
import os
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import database
import fresh_joolan as fresh
import joolan

@contextmanager
def closed_transaction(conn):
    try:
        with conn:yield conn
    finally:conn.close()


def fixture():
    headers=[];lines=[]
    for i in range(25):
        date=f'{2022+i//12}-{i%12+1:02d}-05'
        headers.append(dict(Entete=i,Date=date,Nature='COMMANDE',Client='C',Magasin='WH'))
        lines.append(dict(Ligne=i,Entete=i,Produit='P',Couleur='B',Taille='M',Quantite=10,Quantite_Livree=6,Quantite_Annulee=1))
    return dict(negoce_entetes=headers,negoce_lignes=lines,produits=[dict(Produit='P',Designation='Jacket',Famille='F',Saison='Winter')],
                skus=[dict(Produit='P',Couleur='B',Taille='M',Sku='SKU1')],negoce_clients=[dict(Client='C')])


class FakeClient:
    data=None
    fail_after_page=False
    def __init__(self,*args):pass
    def close(self):pass
    def query(self,sql):
        return [dict(TABLE_NAME=t,COLUMN_NAME=k,DATA_TYPE='text',COLUMN_KEY='') for t,rs in self.data.items() for k in rs[0]]
    def count(self,table,where=''):return len(self.data[table])
    def table_snapshot(self,table,log,document_type='',start_date='',end_date='',extra_where=''):
        primary={'negoce_entetes':['Entete'],'negoce_lignes':['Ligne'],'produits':['Produit'],'skus':['Sku'],'negoce_clients':['Client'],'stocks':['Magasin','Produit','Couleur','Taille']}[table]
        return dict(expected=len(self.data[table]),primary=primary,columns=list(self.data[table][0]),order=primary,where='',upper=[self.data[table][-1][k] for k in primary])
    def table_rows(self,table,batch,log,meta,checkpoint=None):
        for index in range(meta.get('exported',0),len(self.data[table])):
            r=self.data[table][index]
            yield r
            meta['exported']=index+1;meta['cursor']=[r[k] for k in meta['primary']]
            checkpoint()
            if self.fail_after_page and table=='negoce_lignes':
                type(self).fail_after_page=False
                raise fresh.RateLimitError('quota')


class FreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.path=self.base/'source.db';self.serving_path=self.base/'live.db'
        self.c=sqlite3.connect(self.serving_path)
        database._create_persistent_tables(self.c);joolan.ensure_joolan_schema(self.c)
        self.config=dict(enseigne='legend73',documentType='COMMANDE',throughDate='2024-01-10',warehouses=['WH'])
        self.data=fixture();FakeClient.data=self.data;FakeClient.fail_after_page=False
        self.stock=[dict(Magasin='WH',Produit='P',Couleur='B',Taille='M',En_Stock=8,Disponible=3,En_Reservation=5)]
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def export(self):
        rid=fresh.create_run({**self.config,'apiKey':'never-save-this'},self.path)
        fresh.run_export(rid,'never-save-this',self.path,FakeClient,lambda k,c:self.stock)
        return rid,fresh.status(self.path)['run']
    def test_roundtrip_and_stock_semantics_exclude_old_data_and_credentials(self):
        rid,run=self.export();self.assertEqual(run['status'],'validated',run)
        fresh.activate(rid,self.c,self.path)
        path=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
        with open(path,encoding='utf-8',newline='') as f:records=list(csv.DictReader(f))
        self.assertEqual(len(records),25);self.assertEqual(records[0]['STOCK'],'3.0')
        self.assertEqual(records[0]['CDE_four_qte'],'')
        self.assertTrue(all(r['Data_Source']=='joolan' for r in records))
        self.assertNotIn(b'never-save-this',self.path.read_bytes())
        with closed_transaction(fresh.connect(self.path)) as c:
            self.assertNotIn('never-save-this',''.join(str(r) for r in c.iterdump()))
    def test_quota_resume_keeps_only_complete_pages_without_duplicates(self):
        FakeClient.fail_after_page=True
        rid,run=self.export();self.assertEqual(run['status'],'needs_credentials')
        with closed_transaction(fresh.connect(self.path)) as c:self.assertEqual(len(list(fresh.rows(c,rid,'negoce_lignes'))),1)
        fresh.claim_resume(rid,self.path)
        with self.assertRaises(ValueError):fresh.claim_resume(rid,self.path)
        fresh.run_export(rid,'key',self.path,FakeClient,lambda k,c:self.stock)
        self.assertEqual(fresh.status(self.path)['run']['status'],'validated')
        with closed_transaction(fresh.connect(self.path)) as c:self.assertEqual(len(list(fresh.rows(c,rid,'negoce_lignes'))),25)
    def test_stock_resume_never_redownloads_completed_source_tables(self):
        rid=fresh.create_run(self.config,self.path)
        def fail(key,config):raise ValueError('Stock endpoint denied')
        fresh.run_export(rid,'key',self.path,FakeClient,fail)
        self.assertEqual(fresh.status(self.path)['run']['status'],'needs_credentials')
        fresh.claim_resume(rid,self.path)
        # Even remote counts can change since capture: the complete history is frozen.
        with patch.object(FakeClient,'query',side_effect=AssertionError('Schema already saved')),patch.object(FakeClient,'count',side_effect=AssertionError('History already complete')),patch.object(FakeClient,'table_rows',side_effect=AssertionError('No historical redownload')):
            fresh.run_export(rid,'key',self.path,FakeClient,lambda k,c:self.stock)
        self.assertEqual(fresh.status(self.path)['run']['status'],'validated')
    def test_stock_permission_failure_uses_fresh_query_rows_and_keeps_missing_unknown(self):
        self.data['stocks']=self.stock
        self.config['warehouses']=['WH','OTHER']
        rid=fresh.create_run(self.config,self.path)
        def fail(key,config):raise ValueError('Joolan stock endpoint rejected: permission denied')
        fresh.run_export(rid,'key',self.path,FakeClient,fail)
        run=fresh.status(self.path)['run']
        self.assertEqual(run['status'],'validated',run)
        self.assertEqual(run['report']['inventorySource'],'query.do:stocks')
        self.assertEqual(run['report']['missingStockVariants'],1)
        with closed_transaction(fresh.connect(self.path)) as c:
            meta=json.loads(c.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='inventory'",(rid,)).fetchone()[0])
            self.assertFalse(meta['explicitZeroCoverage'])
            self.assertEqual(len(list(fresh.rows(c,rid,'inventory'))),1)
    def test_stock_quota_pauses_without_attempting_query_fallback(self):
        self.data['stocks']=self.stock
        rid=fresh.create_run(self.config,self.path)
        def fail(key,config):raise fresh.RateLimitError('quota')
        fresh.run_export(rid,'key',self.path,FakeClient,fail)
        self.assertEqual(fresh.status(self.path)['run']['phase'],'Paused at Joolan quota')
        with closed_transaction(fresh.connect(self.path)) as c:
            self.assertFalse(c.execute("SELECT 1 FROM datasets WHERE run_id=? AND dataset='stocks'",(rid,)).fetchone())
    def test_stock_error_preserves_reason_without_exposing_credentials(self):
        payload={'result':'ko','error_message':'Permission denied for secret-key https://go.joolan.com/?api-key=secret-key'}
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=io.StringIO(json.dumps(payload))
            with self.assertRaises(ValueError) as error:fresh.full_stock('secret-key',self.config)
        self.assertIn('Permission denied',str(error.exception))
        self.assertNotIn('secret-key',str(error.exception));self.assertNotIn('https://',str(error.exception))
    def test_each_new_export_uses_new_remote_data(self):
        first,_=self.export();fresh.activate(first,self.c,self.path)
        self.data['negoce_lignes'][0]['Quantite']=12
        second,run=self.export();self.assertNotEqual(first,second);self.assertEqual(run['status'],'validated')
        with closed_transaction(fresh.connect(self.path)) as c:
            self.assertEqual(next(fresh.rows(c,first,'negoce_lignes'))['Quantite'],10)
            self.assertEqual(next(fresh.rows(c,second,'negoce_lignes'))['Quantite'],12)
        self.assertEqual(fresh.status(self.path)['activeRun'],first)
    def test_invalid_new_generation_cannot_replace_active(self):
        first,_=self.export();fresh.activate(first,self.c,self.path)
        self.data['negoce_lignes'][0]['Quantite']=-5
        second,run=self.export();self.assertEqual(run['status'],'needs_mapping')
        with self.assertRaises(ValueError):fresh.activate(second,self.c,self.path)
        self.assertEqual(fresh.status(self.path)['activeRun'],first)
    def test_missing_cancellations_do_not_turn_into_zero(self):
        for r in self.data['negoce_lignes']:r.pop('Quantite_Annulee')
        _,run=self.export();self.assertEqual(run['status'],'needs_mapping')
        self.assertIn('Quantite_Annulee',' '.join(run['report']['blockers']))
    def test_documented_statuses_preserve_booked_demand_and_close_balances(self):
        for h in self.data['negoce_entetes']:h['Statut']=3
        for line in self.data['negoce_lignes']:line.pop('Quantite_Annulee')
        self.data['negoce_lignes'][0].update(Statut=0,Quantite_Livree=0)
        self.data['negoce_lignes'][1]['Statut']=2
        rid,run=self.export()
        self.assertEqual(run['status'],'validated',run)
        self.assertEqual(run['report']['excludedDraftLines'],1)
        self.assertFalse(run['report']['cancellationsComplete'])
        fresh.activate(rid,self.c,self.path)
        path=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
        with open(path,encoding='utf-8') as f:records=list(csv.DictReader(f))
        self.assertEqual(len(records),24)
        cancelled=next(r for r in records if r['Order_Status']=='2.0')
        self.assertEqual(cancelled['ANN_qte'],'4.0')
        closed=next(r for r in records if r['Order_Status']=='3.0')
        self.assertEqual(closed['CDE_qte'],'10.0')
        self.assertEqual(closed['RELIQUAT_qte'],'0.0')
        self.assertEqual(closed['Cancellations_Known'],'False')
    def test_negative_available_stock_survives_model_preparation(self):
        self.stock[0]['Disponible']=-3
        rid,run=self.export();self.assertEqual(run['status'],'validated')
        fresh.activate(rid,self.c,self.path)
        path=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
        from m1_data_preparation import load_data,parse_and_prepare
        data=parse_and_prepare(load_data(path))
        self.assertTrue(data.STOCK.eq(-3).all())
    def test_warehouse_casing_matches_selected_master_code(self):
        self.stock[0]['Magasin']='wh'
        rid,run=self.export();self.assertEqual(run['status'],'validated',run)
        fresh.activate(rid,self.c,self.path)
        path=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
        with open(path,encoding='utf-8') as f:self.assertEqual(next(csv.DictReader(f))['STOCK'],'3.0')
    def test_overdelivery_retains_actuals_without_increasing_booked_demand(self):
        line=dict(Quantite=1,Quantite_Livree=2,Statut=1)
        q=fresh.order_quantities(line,{})
        self.assertEqual((q['ordered'],q['delivered'],q['remaining']),(1,2,0))
        self.assertEqual(q['overdelivered'],1)
        q=fresh.order_quantities({**line,'Statut':2},{})
        self.assertEqual(q['cancelled'],0)
    def test_small_signed_adjustment_is_retained_raw_and_disclosed_not_trained(self):
        original=self.data['negoce_lignes']
        self.data['negoce_lignes']=[{**original[i%25],'Ligne':i} for i in range(1001)]
        self.data['negoce_lignes'][0]['Quantite']=-1
        rid,run=self.export();self.assertEqual(run['status'],'validated',run)
        self.assertEqual(run['report']['excludedAdjustmentLines'],1)
        fresh.activate(rid,self.c,self.path)
        path=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
        with open(path,encoding='utf-8') as f:self.assertEqual(len(list(csv.DictReader(f))),1000)
        with closed_transaction(fresh.connect(self.path)) as c:self.assertEqual(len(list(fresh.rows(c,rid,'negoce_lignes'))),1001)
    def test_material_adjustment_units_block_even_when_line_count_is_small(self):
        original=self.data['negoce_lignes']
        self.data['negoce_lignes']=[{**original[i%25],'Ligne':i} for i in range(1001)]
        self.data['negoce_lignes'][0]['Quantite']=-1000
        _,run=self.export();self.assertEqual(run['status'],'needs_mapping')
        self.assertIn('0.1%',' '.join(run['report']['blockers']))
    def test_revalidation_uses_saved_complete_source_without_remote_reads(self):
        rid,_=self.export()
        with closed_transaction(fresh.connect(self.path)) as c:fresh.update(c,rid,status='needs_mapping')
        with patch.object(fresh,'Client',side_effect=AssertionError('No live API needed')):
            report=fresh.revalidate_run(rid,self.path)
        self.assertTrue(report['readyForForecast'])
        self.assertEqual(fresh.status(self.path)['run']['status'],'validated')
    def test_reused_header_ids_remain_isolated_by_store_and_customer_when_cached(self):
        self.c.execute('CREATE TEMP TABLE order_headers(id TEXT,store TEXT,customer TEXT,payload TEXT)')
        for store,customer,date in [('A','C','2023-01-01'),('B','D','2024-01-01')]:
            self.c.execute('INSERT INTO order_headers VALUES(?,?,?,?)',('1',store,customer,fresh.encode(dict(Date=date))))
        resolve=fresh.header_resolver(self.c)
        for _ in range(2):
            self.assertEqual(resolve(dict(Entete=1,Magasin='A',Client='C'))['Date'],'2023-01-01')
            self.assertEqual(resolve(dict(Entete=1,Magasin='B',Client='D'))['Date'],'2024-01-01')
        with self.assertRaises(ValueError):resolve(dict(Entete=1))
    def test_missing_warehouse_balance_remains_unknown(self):
        self.config['warehouses']=['WH','OTHER']
        rid,run=self.export();self.assertEqual(run['report']['missingStockVariants'],1)
        fresh.activate(rid,self.c,self.path)
        path=fresh.export_pipeline(self.c,self.base/'unused.csv',self.path)
        with open(path,encoding='utf-8') as f:self.assertEqual(next(csv.DictReader(f))['STOCK'],'')
    def test_ambiguous_header_join_is_rejected(self):
        self.data['negoce_entetes'].append({**self.data['negoce_entetes'][0],'Magasin':'OTHER'})
        # Bypass duplicate PK extraction to exercise the local join itself.
        rid=fresh.create_run(self.config,self.path)
        schema={t:[dict(name=k) for k in rs[0]] for t,rs in self.data.items()}
        with closed_transaction(fresh.connect(self.path)) as c:
            for t,rs in {**self.data,'inventory':self.stock}.items():
                c.executemany('INSERT INTO records VALUES(?,?,?,?)',[(rid,t,str(i),fresh.encode(r)) for i,r in enumerate(rs)])
            result=fresh.validate(c,rid,schema,self.config)
            self.assertFalse(result['readyForForecast']);self.assertEqual(result['invalidOrderLines'],1)
    def test_interrupted_worker_becomes_resumable(self):
        rid=fresh.create_run(self.config,self.path)
        with closed_transaction(fresh.connect(self.path)) as c:
            c.execute("UPDATE runs SET status='running',pid=123,updated_at='2020-01-01T00:00:00+00:00'")
        with patch.object(fresh,'process_alive',return_value=False):
            self.assertEqual(fresh.status(self.path)['run']['status'],'needs_credentials')
    def test_cli_cannot_use_an_old_file_or_fallback(self):
        import main
        with self.assertRaisesRegex(ValueError,'External data files'):main.run_phase1('previous.csv')
        with patch.object(database,'get_connection',lambda:sqlite3.connect(self.serving_path)):
            with self.assertRaisesRegex(ValueError,'fresh Joolan'):main.run_phase1()
    def test_fresh_pipeline_trains_closed_months_and_publishes_lineage(self):
        import main
        rid,run=self.export();fresh.activate(rid,self.c,self.path)
        with patch.object(fresh,'SOURCE_DB',self.path),patch.object(database,'DB_FILE',self.serving_path),patch.object(database,'get_connection',lambda:sqlite3.connect(self.serving_path)),patch.object(main,'BASE_DIR',self.base),patch.dict(os.environ,{'FORECASTER_DISABLE_CATBOOST':'1'}):
            result=main.run_phase1()
        self.assertEqual(result['lineage']['source'],'fresh')
        self.assertEqual(result['lineage']['freshRun'],rid)
        self.assertEqual(result['lineage']['cutoff'],'2023-12')
        self.assertEqual(str(result['data']['monthly_sku_color_size'].year_month.max()),'2024-01')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0],25)
        self.assertEqual(self.c.execute('SELECT SUM(true_demand) FROM client_orders').fetchone()[0],225)
        self.assertEqual(self.c.execute('SELECT current_stock FROM recommendations').fetchone()[0],3)


class FreshApiTests(unittest.TestCase):
    def test_policy_blocks_legacy_inputs_and_stale_forecasts(self):
        import api_server
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'api.db'
            with patch.object(api_server,'get_connection',lambda:sqlite3.connect(path)),TestClient(api_server.app) as client:
                for route in ('/api/joolan/file','/api/joolan/sync','/api/joolan/forecast-source','/api/history/build','/api/ingest/file','/api/planning/inputs'):
                    self.assertEqual(client.post(route,json={}).status_code,409,route)
                for route in ('/api/dashboard','/api/orders','/api/customer-detail','/api/export'):
                    self.assertEqual(client.get(route).status_code,409,route)
                self.assertFalse(client.get('/api/forecast/readiness').json()['ready'])
                self.assertEqual(client.get('/api/dashboard',headers={'Origin':'https://evil.example'}).status_code,403)
                with closed_transaction(sqlite3.connect(path)) as c:
                    c.execute("INSERT OR REPLACE INTO joolan_state VALUES('fresh_run','new')")
                    c.execute("INSERT OR REPLACE INTO pipeline_metadata VALUES('lineage',?, 'now')",(json.dumps({'freshRun':'old'}),))
                self.assertEqual(client.get('/api/dashboard').status_code,409)


if __name__=='__main__':unittest.main()
