import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zlib

import pandas as pd
import joolan
import history_store
from m1_data_preparation import EXPECTED_COLUMNS, _standardize_columns


def legacy(date='2026-02-26'):
    row = {c: '' for c in EXPECTED_COLUMNS}
    row.update(Client='0007', Reference='000123', Couleur='01', Taille='08',
               Reference_CDE='001', Date_Commande=date, LIV_qte=2, RELIQUAT_qte=3,
               CDE_qte=5, ANN_qte=0, STOCK=100, CDE_four_qte=40, Prix=20)
    return row


def trade(date='2026-02-27', number='002', quantity=7):
    return dict(Order_Number=number, Customer='0007', Product='000123',
                Order_Date=date, Store='A', Colour='01', Size='08',
                Ordered_Quantity=quantity, Delivered_Quantity=0,
                Cancelled_Quantity=0, Document_Type='ORDER', Line_Number='1')


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.csv = self.base/'base.csv'
        pd.DataFrame([legacy(), legacy()]).to_csv(self.csv, index=False)
        self.path = self.base/'history.db'
        self.source = sqlite3.connect(':memory:')
        joolan.ensure_joolan_schema(self.source)
        self.source.execute("INSERT INTO joolan_state VALUES('customer_order_type','ORDER')")
        self.source.commit()

    def tearDown(self):
        self.source.close(); self.tmp.cleanup()

    def snapshot(self, rows, start='2026-02-01', end='2026-03-31'):
        joolan.replace_snapshot(self.source, rows, 'query-api',
                               dict(documentType='ORDER', startDate=start, endDate=end, enseigne='account'))

    def build(self):
        return history_store.build(self.source, self.csv, self.path)

    def test_csv_boundary_retains_repeated_lines_and_skips_joolan_overlap(self):
        self.snapshot([trade(date='2026-02-26'), trade()])
        result = self.build()
        self.assertEqual(result['legacyRows'], 2)
        self.assertEqual(result['joolanRows'], 1)
        self.assertEqual(result['totalRows'], 3)
        self.assertEqual(result['csvCutoff'], '2026-02-26')
        self.assertEqual(result['gaps'], [])
        self.assertEqual(self.build()['totalRows'], 3)

    def test_refresh_changes_quantities_and_removes_deleted_lines_only_in_scope(self):
        self.snapshot([trade(), trade(date='2026-03-03', number='003')])
        self.build()
        self.snapshot([trade(quantity=9)], start='2026-02-27', end='2026-02-28')
        self.assertEqual(self.build()['joolanRows'], 2)
        conn = history_store.connection(self.path)
        try:
            payload = conn.execute("SELECT payload FROM history_rows WHERE source='joolan' AND order_date='2026-02-27'").fetchone()[0]
            self.assertEqual(json.loads(zlib.decompress(payload))['CDE_qte'], 9)
        finally:
            conn.close()

    def test_invalid_csv_rebuild_preserves_previous_baseline(self):
        self.snapshot([trade()]); self.build()
        pd.DataFrame([legacy(date='invalid')]).to_csv(self.csv,index=False)
        with self.assertRaisesRegex(ValueError, 'invalid dates'):
            self.build()
        conn=history_store.connection(self.path)
        try:
            self.assertEqual(history_store.summary(conn)['legacyRows'], 2)
        finally: conn.close()

    def test_date_gap_is_detected_and_pipeline_export_refuses_it(self):
        self.snapshot([trade(date='2026-03-02')], start='2026-03-01')
        self.assertTrue(self.build()['gaps'])
        with patch('config.DATA_FILE_PATH', str(self.csv)):
            with self.assertRaisesRegex(ValueError, 'date gaps'):
                history_store.export_pipeline(self.base/'pipeline.csv', self.source, self.path)

    def test_pipeline_contains_both_sources_and_never_uses_historical_stock(self):
        self.snapshot([trade()]); self.build()
        with patch('config.DATA_FILE_PATH', str(self.csv)):
            path=history_store.export_pipeline(self.base/'pipeline.csv', self.source, self.path)
        frame=pd.read_csv(path,dtype=str)
        self.assertEqual(len(frame),3)
        self.assertEqual(set(frame.Data_Source), {'legacy','joolan'})
        self.assertTrue(frame.STOCK.isna().all())
        self.assertEqual(frame.Reference.iloc[0],'000123')
        self.assertEqual(frame.Taille.iloc[0],'08')

    def test_observed_corrupted_headers_have_explicit_semantic_aliases(self):
        frame=_standardize_columns(pd.DataFrame(columns=['R馭駻ence','R馭駻ence_CDE','Client','Couleur','Taille','Prix','Date_Commande','CDE_qte','LIV_qte','RELIQUAT_qte']))
        self.assertIn('Reference',frame)
        self.assertIn('Reference_CDE',frame)

    def test_unconfirmed_types_are_preserved_raw_without_entering_forecast_history(self):
        self.snapshot([trade()])
        self.source.execute("DELETE FROM joolan_state WHERE key='customer_order_type'")
        self.source.commit()
        result=self.build()
        self.assertEqual(result['rawJoolanRows'],1)
        self.assertEqual(result['joolanRows'],0)
        self.assertEqual(result['storedRows'],3)
        self.assertTrue(result['needsOrderType'])

    def test_negative_quantity_stays_in_raw_history_but_is_excluded_from_model_input(self):
        bad=legacy();bad['RELIQUAT_qte']=-1
        pd.DataFrame([legacy(),bad]).to_csv(self.csv,index=False)
        self.snapshot([trade()])
        result=self.build()
        self.assertEqual(result['legacyRows'],2)
        self.assertEqual(result['legacyQuarantinedRows'],1)
        with patch('config.DATA_FILE_PATH',str(self.csv)):
            path=history_store.export_pipeline(self.base/'pipeline.csv',self.source,self.path)
        self.assertEqual(len(pd.read_csv(path)),2)

    def test_combined_pipeline_trains_on_closed_months_but_retains_current_actuals(self):
        import database, main, planning, os
        baseline=[legacy(str(month.start_time.date())) for month in pd.period_range('2022-01','2023-12',freq='M')]
        pd.DataFrame(baseline).to_csv(self.csv,index=False)
        serving=self.base/'forecast.db'
        source=sqlite3.connect(serving)
        database._create_persistent_tables(source)
        joolan.replace_snapshot(source,[trade(date='2024-01-20',quantity=7),trade(date='2024-02-05',number='003',quantity=5)],'query-api',
                                dict(documentType='ORDER',startDate='2023-12-02',endDate='2024-02-10',enseigne='account'))
        joolan.confirm_order_type(source,'ORDER')
        planning.save_season(source,dict(name='Plan',startDate='2024-02-01',endDate='2024-07-31',currency='EUR',budget=1000,targetMargin=20))
        with patch('config.DATA_FILE_PATH',str(self.csv)),patch.object(history_store,'DEFAULT_PATH',self.path):
            joolan.select_forecast_source(source,'combined')
            source.close()
            with patch.object(database,'DB_FILE',serving),patch.object(database,'get_connection',lambda:sqlite3.connect(serving)),patch.object(main,'BASE_DIR',self.base),patch.dict(os.environ,{'FORECASTER_DISABLE_CATBOOST':'1'}):
                results=main._run_phase1()
        self.assertEqual(results['lineage']['source'],'combined')
        self.assertEqual(results['lineage']['cutoff'],'2024-01')
        self.assertEqual(results['lineage']['forecastStart'],'2024-02')
        self.assertEqual(str(results['data']['monthly_sku_color_size'].year_month.max()),'2024-02')
        self.assertTrue(results['lineage']['cancellationsComplete'])
