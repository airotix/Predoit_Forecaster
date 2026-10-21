import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database,joolan,planning,forecasting

def monthly():
    rows=[]
    for key in ('001','002'):
        for i,month in enumerate(pd.period_range('2020-01',periods=48,freq='M')):
            rows.append(dict(Reference=key,Couleur='01',Taille='08',year_month=month,true_demand=float(5+month.month if key=='001' else i%3)))
    return pd.DataFrame(rows)

def prepared(conn):
    database._create_persistent_tables(conn);database._create_schema(conn)
    conn.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,available_inventory,unit_selling_price,unit_purchase_cost,financial_note,confidence,famille) VALUES('001','01','08',20,10,30,5,10,4,'Actual supplied','LOW','F')")
    conn.execute("INSERT INTO pipeline_metadata VALUES('last_run','old','old')")
    conn.commit()

class ForecastTests(unittest.TestCase):
    def test_calendar_gaps_and_all_products_share_horizon(self):
        data=monthly();data=data.drop(data[(data.Reference=='001')&(data.year_month==pd.Period('2020-02'))].index)
        sparse=pd.DataFrame([dict(Reference='new',Couleur='01',Taille='08',year_month=pd.Period('2023-12'),true_demand=3)])
        data=pd.concat([data,sparse]);history,cut=forecasting.calendar_series(data)
        self.assertEqual(history[('001','01','08')][1][1],0)
        pred,_=forecasting.forecast(data,use_catboost=False)
        self.assertEqual(pred.groupby(forecasting.KEYS).size().tolist(),[6,6,6])
        self.assertTrue((pred.forecast_month.min()==pd.Period('2024-01')))
        self.assertTrue((pred.forecast_month.max()==pd.Period('2024-06')))
        self.assertTrue((pred.forecast_conservative<=pred.forecast_base).all())
        self.assertTrue((pred.forecast_optimistic>=pred.forecast_base).all())
    def test_future_data_cannot_change_cutoff_forecast(self):
        data=monthly();cut=pd.Period('2022-06')
        first,_=forecasting.forecast(data,cutoff=cut,use_catboost=False)
        data.loc[data.year_month>cut,'true_demand']=1000000
        second,_=forecasting.forecast(data,cutoff=cut,use_catboost=False)
        pd.testing.assert_frame_equal(first,second)
    def test_training_features_use_only_prior_demand(self):
        frame=monthly();histories,cut=forecasting.calendar_series(frame)
        features=forecasting.training_frame(histories,cut)
        row=features[features.Reference=='001'].iloc[0]
        self.assertEqual(row.lag_1,6)
        self.assertEqual(row.target,7)
        self.assertEqual(row.mean_3,6)
        self.assertEqual(features[features.Reference=='002'].iloc[0].lag_1,0)
    def test_recursive_model_updates_lags(self):
        class Model:
            def predict(self,frame):return frame.lag_1.to_numpy()+1
        hist={('P','C','S'):(pd.period_range('2020-01',periods=1,freq='M'),np.array([2.]))}
        result=forecasting.recursive_predictions(Model(),hist,pd.Period('2020-02'),3)
        self.assertEqual(result[('P','C','S')].tolist(),[3,4,5])
    def test_rolling_backtest_has_calendar_folds_and_metrics(self):
        folds=forecasting.rolling_backtest(monthly(),use_catboost=False)
        self.assertEqual(len(folds),3)
        self.assertEqual(folds[-1]['testEnd'],'2023-12')
        self.assertIn('bias',folds[0]['selected'])
        self.assertEqual(folds[0]['selected']['n'],12)
    def test_plan_cannot_overlap_history(self):
        with self.assertRaisesRegex(ValueError,'after'):forecasting.forecast(monthly(),start='2023-01',use_catboost=False)

class PublicationTests(unittest.TestCase):
    def test_complete_pipeline_publishes_aligned_forecasts_inputs_and_ledger(self):
        import main
        from m1_data_preparation import EXPECTED_COLUMNS
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);path=base/'db';csv_path=base/'orders.csv'
            rows=[]
            for i,month in enumerate(pd.period_range('2022-01',periods=24,freq='M')):
                row={k:0 if k.endswith(('_qte','_ht')) or k in ('Prix','STOCK') else '' for k in EXPECTED_COLUMNS}
                row.update(Client='C',Reference='P',Couleur='B',Taille='M',Reference_CDE='O'+str(i),Date_Commande=str(month)+'-01',Critere='Hiver('+str(month.year)+')',CDE_qte=5,LIV_qte=5,RELIQUAT_qte=0,STOCK=2,CDE_four_qte=1,Prix=10,Selling_Price=10,Purchase_Cost=4,Famille='F',Rayon='R',Saison='S',Nom='Customer')
                rows.append(row)
            pd.DataFrame(rows).to_csv(csv_path,index=False)
            with patch.object(database,'DB_FILE',path),patch.object(database,'get_connection',lambda:sqlite3.connect(path)),patch.object(main,'BASE_DIR',base),patch.dict(os.environ,{'FORECASTER_DISABLE_CATBOOST':'1'}):
                results=main._run_phase1(str(csv_path))
            conn=sqlite3.connect(path)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM forecast_monthly').fetchone()[0],6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM forecast_monthly WHERE model_forecast_base IS NOT NULL AND season_booked IS NOT NULL').fetchone()[0],6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0],24)
            self.assertEqual(conn.execute('SELECT current_stock,pipeline_stock,unit_purchase_cost FROM recommendations').fetchone(),(2,1,4))
            self.assertTrue(planning.financial_summary(conn)['financialComplete'])
            self.assertEqual(results['lineage']['forecastStart'],'2024-01')
            self.assertEqual(results['lineage']['forecastEnd'],'2024-06');conn.close()
    def test_drop_create_rollback_restores_previous_data(self):
        conn=sqlite3.connect(':memory:');prepared(conn)
        database._create_schema(conn);conn.rollback()
        self.assertEqual(conn.execute('SELECT forecast_base FROM recommendations').fetchone()[0],20)
        conn.close()
    def test_populate_failure_preserves_published_and_persistent_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'db';conn=sqlite3.connect(path);prepared(conn)
            conn.execute("INSERT INTO sku_locks VALUES('001','01',1,'local','now')");conn.commit();conn.close()
            with patch.object(database,'DB_FILE',path),patch.object(database,'get_connection',lambda:sqlite3.connect(path)),patch.object(database,'_insert_recommendations',side_effect=RuntimeError('failure')):
                with self.assertRaises(RuntimeError):database.populate_database({})
            conn=sqlite3.connect(path)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM recommendations').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT locked FROM sku_locks').fetchone()[0],1);conn.close()

class InputAndOrderTests(unittest.TestCase):
    def test_iso_and_french_dates_keep_correct_calendar_months(self):
        from m1_data_preparation import parse_order_dates
        dates=parse_order_dates(pd.Series(['2023-12-01','01/12/2023','2023-02-01','13/02/2023']))
        self.assertEqual(dates.dt.strftime('%Y-%m-%d').tolist(),['2023-12-01','2023-12-01','2023-02-01','2023-02-13'])
    def test_cancellations_are_preserved_in_customer_demand(self):
        conn=sqlite3.connect(':memory:')
        row=dict(Order_Number='O',Customer='C',Order_Date='2026-01-01',Product='P',Ordered_Quantity=10,Delivered_Quantity=3,Cancelled_Quantity=2,Document_Type='ORDER')
        joolan.replace_snapshot(conn,[row],'test');joolan.confirm_order_type(conn,'ORDER')
        frame=joolan.pipeline_dataframe(conn)
        self.assertEqual(frame.RELIQUAT_qte.iloc[0],5)
        from m1_data_preparation import parse_and_prepare
        self.assertEqual(parse_and_prepare(frame).true_demand.iloc[0],8)
        conn.close()
    def test_failed_stream_preserves_prior_joolan_snapshot(self):
        conn=sqlite3.connect(':memory:')
        row=dict(Order_Number='O',Customer='C',Order_Date='2026-01-01',Product='P',Ordered_Quantity=10,Delivered_Quantity=3,Document_Type='ORDER')
        joolan.replace_snapshot(conn,[row],'test')
        def incomplete():
            for i in range(1100):yield dict(row,Order_Number=str(i))
            raise RuntimeError('Network failed')
        with self.assertRaises(RuntimeError):joolan.replace_snapshot(conn,incomplete(),'test')
        self.assertEqual(joolan.snapshot_summary(conn)['totalRows'],1)
        self.assertEqual(joolan.snapshot_rows(conn)[0]['Order_Number'],'O');conn.close()
    def test_line_identity_normalizes_equivalent_dates(self):
        from ingestion import with_line_keys
        row=dict(Client='C',Reference='P',Couleur='B',Taille='M',Reference_CDE='A',Date_Commande='2026-01-01')
        self.assertEqual(with_line_keys(pd.DataFrame([row])).Source_Line_Key.iloc[0],with_line_keys(pd.DataFrame([dict(row,Date_Commande='2026-01-01 00:00:00')])).Source_Line_Key.iloc[0])
    def test_unknown_inventory_and_prices_remain_unknown(self):
        conn=sqlite3.connect(':memory:');joolan.ensure_joolan_schema(conn)
        row=dict(Order_Number='O',Customer='C',Order_Date='2026-01-01',Product='P',Ordered_Quantity=2.5,Delivered_Quantity=0,Document_Type='ORDER')
        joolan.replace_snapshot(conn,[row],'test');joolan.confirm_order_type(conn,'ORDER')
        df=joolan.pipeline_dataframe(conn)
        self.assertIsNone(df.STOCK.iloc[0]);self.assertIsNone(df.Prix.iloc[0]);conn.close()
    def test_customer_order_type_is_required_and_excludes_other_documents(self):
        conn=sqlite3.connect(':memory:')
        row=dict(Order_Number='O',Customer='C',Order_Date='2026-01-01',Product='P',Ordered_Quantity=2.5,Delivered_Quantity=0,Document_Type='ORDER')
        joolan.replace_snapshot(conn,[row,dict(row,Order_Number='I',Document_Type='INVOICE')],'test')
        with self.assertRaises(ValueError):joolan.select_forecast_source(conn,'joolan')
        joolan.confirm_order_type(conn,'ORDER');self.assertEqual(len(joolan.pipeline_dataframe(conn)),1);conn.close()
    def test_distinct_orders_and_repeated_lines_survive_identity_mapping(self):
        from ingestion import with_line_keys
        frame=pd.DataFrame([dict(Client='C',Reference='P',Couleur='B',Taille='M',Reference_CDE='A',Date_Commande='2026-01-01'),dict(Client='C',Reference='P',Couleur='B',Taille='M',Reference_CDE='B',Date_Commande='2026-01-01')])
        frame=pd.concat([frame,frame.iloc[[0]]],ignore_index=True)
        self.assertEqual(with_line_keys(frame).Source_Line_Key.nunique(),3)
    def test_season_budget_and_real_costs_drive_final_metrics(self):
        conn=sqlite3.connect(':memory:');prepared(conn)
        plan=planning.save_season(conn,dict(name='Plan',startDate='2024-01-01',endDate='2024-06-30',currency='EUR',budget=200,targetMargin=40))
        conn.execute("INSERT INTO pipeline_metadata VALUES('lineage',?,'now')",(json.dumps({'seasonId':plan['id']}),))
        conn.execute("INSERT INTO user_overrides(reference,couleur,taille,override_qty,created_at,updated_at,plan_id) VALUES('001','01','08',7,'now','now',?)",(plan['id'],));conn.commit()
        summary=planning.financial_summary(conn)
        self.assertEqual(summary['totalPurchaseCost'],28)
        self.assertEqual(summary['seasonBudget'],200)
        self.assertAlmostEqual(summary['budgetUsage'],14)
        self.assertEqual(summary['expectedTurnover'],200)
        self.assertEqual(summary['grossMarginPercent'],60);conn.close()
    def test_bad_cost_input_is_rejected(self):
        conn=sqlite3.connect(':memory:');planning.ensure_schema(conn)
        with self.assertRaises(ValueError):planning.save_inputs(conn,[dict(Reference='P',Couleur='C',Taille='S',Purchase_Cost=-1)])
        conn.close()

class ApiReliabilityTests(unittest.TestCase):
    def legacy_file(self,number='A',quantity=3):
        from m1_data_preparation import EXPECTED_COLUMNS
        row={k:0 if k.endswith(('_qte','_ht')) or k in ('Prix','STOCK') else '' for k in EXPECTED_COLUMNS}
        row.update(Client='0001',Reference='0002',Couleur='01',Taille='08',Reference_CDE=number,Date_Commande='2026-01-02',Critere='Hiver(2026)',CDE_qte=quantity,LIV_qte=quantity,Nom='Customer')
        return pd.DataFrame([row]).to_csv(index=False).encode()
    def test_repeated_and_incremental_file_imports_keep_full_history(self):
        import config,ingestion
        with patch.object(config,'DATA_FILE_PATH',str(Path(self.tmp.name)/'absent.csv')),patch.object(ingestion,'BASE_DIR',Path(self.tmp.name)):
            for number,qty in [('A',3),('A',3),('B',5)]:
                response=self.client.post('/api/ingest/file',files={'file':('orders.csv',self.legacy_file(number,qty),'text/csv')})
                self.assertEqual(response.status_code,200,response.text)
            conn=sqlite3.connect(self.path)
            self.assertEqual(conn.execute('SELECT SUM(true_demand) FROM historical_demand').fetchone()[0],8)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT client_id,first_order FROM clients').fetchone(),('0001','2026-01-02'));conn.close()
    def test_failed_file_publication_restores_actuals_and_append_file(self):
        import config,ingestion
        with patch.object(config,'DATA_FILE_PATH',str(Path(self.tmp.name)/'absent.csv')),patch.object(ingestion,'BASE_DIR',Path(self.tmp.name)):
            response=self.client.post('/api/ingest/file',files={'file':('orders.csv',self.legacy_file(),'text/csv')})
            self.assertEqual(response.status_code,200,response.text)
            path=ingestion._ingest_append_path();old=path.read_bytes()
            with patch.object(self.api,'dedupe_and_upsert',side_effect=RuntimeError('Publication failed')):
                response=self.client.post('/api/ingest/file',files={'file':('orders.csv',self.legacy_file('B',5),'text/csv')})
            self.assertEqual(response.status_code,400)
            self.assertEqual(path.read_bytes(),old)
            conn=sqlite3.connect(self.path)
            self.assertEqual(conn.execute('SELECT SUM(true_demand) FROM historical_demand').fetchone()[0],3);conn.close()
    def setUp(self):
        import api_server
        self.api=api_server;self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'api.db'
        conn=sqlite3.connect(self.path);prepared(conn);conn.close()
        self.patch=patch.object(self.api,'get_connection',lambda:sqlite3.connect(self.path));self.patch.start()
        from fastapi.testclient import TestClient
        self.client=TestClient(self.api.app);self.client.__enter__()
        # Exercise archived serving/ingestion behavior in this isolated legacy fixture.
        # Production fresh-only policy is covered by test_fresh_joolan.
        conn=sqlite3.connect(self.path)
        conn.execute("DELETE FROM joolan_state WHERE key='source_policy'");conn.commit();conn.close()
        conn=sqlite3.connect(self.path)
        conn.execute("UPDATE joolan_state SET value='legacy' WHERE key='forecast_source'");conn.commit();conn.close()
    def tearDown(self):self.client.__exit__(None,None,None);self.patch.stop();self.tmp.cleanup()
    def test_get_export_includes_override_and_selected_scenario(self):
        conn=sqlite3.connect(self.path);conn.execute("INSERT INTO user_overrides(reference,couleur,taille,override_qty,created_at,updated_at,scenario) VALUES('001','01','08',7,'now','now','optimistic')");conn.commit();conn.close()
        response=self.client.get('/api/export?format=json&scenario=optimistic')
        self.assertEqual(response.status_code,200,response.text)
        row=response.json()[0];self.assertEqual(row['demand_forecast'],30);self.assertEqual(row['final_quantity'],7);self.assertEqual(row['purchase_cost'],28)
    def test_unknown_financials_block_approved_export_but_allow_draft(self):
        conn=sqlite3.connect(self.path);conn.execute("UPDATE recommendations SET financial_note='COST_UNKNOWN' ");conn.commit();conn.close()
        self.assertEqual(self.client.get('/api/export?purpose=approved').status_code,409)
        self.assertEqual(self.client.get('/api/export?purpose=draft').status_code,200)
    def test_locked_and_negative_overrides_are_rejected(self):
        response=self.client.put('/api/recommendations/001/01',json={'sizeBreakdown':[{'size':'08','finalQty':-1}]})
        self.assertEqual(response.status_code,400)
        self.client.post('/api/recommendations/001/01/lock')
        response=self.client.put('/api/recommendations/001/01',json={'sizeBreakdown':[{'size':'08','finalQty':7}]})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.post('/api/recommendations/001/01/unlock',json={}).status_code,200)
        self.assertEqual(self.client.put('/api/recommendations/001/01',json={'sizeBreakdown':[{'size':'08','finalQty':7}]}).status_code,200)
    def test_final_recommendation_totals_match_exports_and_costs(self):
        self.client.put('/api/recommendations/001/01',json={'sizeBreakdown':[{'size':'08','finalQty':7}],'scenario':'optimistic'})
        response=self.client.get('/api/recommendations?scenario=optimistic')
        self.assertEqual(response.status_code,200,response.text)
        row=response.json()[0]
        self.assertEqual(row['scenarios']['optimistic']['total'],30)
        self.assertEqual(row['scenarios']['base']['total'],20)
        self.assertEqual(row['purchaseTotals']['optimistic'],7)
        self.assertEqual(row['purchaseTotals']['base'],15)
        self.assertEqual(row['financialImpact']['purchaseCost'],28)
        self.assertEqual(row['financialImpact']['grossMargin'],180)
    def test_duplicate_refresh_is_not_queued(self):
        with patch.object(self.api,'_forecast_pending',True):self.assertEqual(self.client.post('/api/forecast/refresh').status_code,409)
    def test_untrusted_browser_origin_is_rejected(self):
        self.assertEqual(self.client.get('/api/export',headers={'Origin':'https://untrusted.example'}).status_code,403)
    def test_season_creation_is_persisted(self):
        result=self.client.post('/api/seasons',json=dict(name='Plan',startDate='2024-01-01',endDate='2024-06-30',currency='EUR',budget=200,targetMargin=40))
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.client.get('/api/seasons/active').json()['budget'],200)
    def test_changed_inputs_and_unknown_cancellations_block_approval(self):
        conn=sqlite3.connect(self.path)
        lineage=dict(source='legacy',inputsHash=planning.inputs_fingerprint([]),createdAt='2026-01-01',cancellationsComplete=False)
        conn.execute("INSERT INTO pipeline_metadata VALUES('lineage',?,'now')",(json.dumps(lineage),));conn.commit();conn.close()
        self.assertEqual(self.client.get('/api/export?purpose=approved').status_code,409)
        conn=sqlite3.connect(self.path);lineage['cancellationsComplete']=True
        conn.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",(json.dumps(lineage),));conn.commit();conn.close()
        self.assertEqual(self.client.get('/api/export?purpose=approved').status_code,200)
        conn=sqlite3.connect(self.path)
        planning.save_inputs(conn,[dict(Reference='001',Couleur='01',Taille='08',Purchase_Cost=5)])
        conn.close()
        self.assertEqual(self.client.get('/api/export?purpose=approved').status_code,409)
        self.assertEqual(self.client.get('/api/export?purpose=draft').status_code,200)

if __name__=='__main__':unittest.main()
