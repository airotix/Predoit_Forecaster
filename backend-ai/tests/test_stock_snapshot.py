import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import database
import projection_detail
import stock_snapshot


class StockSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'source.db'
        self.conn = sqlite3.connect(':memory:')
        database._create_schema(self.conn)
        import catalogue
        catalogue.ensure(self.conn)
        self.conn.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base,current_stock,pipeline_stock,season_booked,confirmed_delivered,net_to_order_base) VALUES('P','BLACK','M',90,11,5,30,20,74)")
        self.lineage = dict(freshRun='published', operatingScope=dict(warehouseRoles={'CENTRAL':'primary', 'DEFECTUEUX':'faulty', 'CUSTOMER':'consignment'}))
        self.conn.execute("INSERT INTO pipeline_metadata(key,value) VALUES('lineage',?)", (json.dumps(self.lineage),))
        self.source = sqlite3.connect(self.path)
        self.source.executescript('CREATE TABLE runs(id TEXT,status TEXT,config TEXT); CREATE TABLE datasets(run_id TEXT,dataset TEXT,metadata TEXT); CREATE TABLE records(run_id TEXT,dataset TEXT,record_key TEXT,payload TEXT);')
        for rid in ('published','newer'):
            self.source.execute('INSERT INTO runs VALUES(?,?,?)', (rid,'validated',json.dumps(dict(warehouses=['CENTRAL','DEFECTUEUX','CUSTOMER']))))
            self.source.execute('INSERT INTO datasets VALUES(?,?,?)', (rid,'inventory',json.dumps(dict(complete=True,source='query.do:stocks',fetchedAt='2026-10-19T12:00:00Z'))))
        self.record = dict(Produit='P',Couleur='BLACK',Taille='M',Magasin='CENTRAL',En_Stock=15,Disponible=14,Reliquat_Fournisseur=29,En_Commande=6,Attribue=1,Theorique=37)
        self.add(self.record)
        self.add(dict(self.record,Magasin='DEFECTUEUX',En_Stock=500))
        self.add(dict(self.record,Magasin='CUSTOMER',En_Stock=500))
        self.add(dict(self.record,En_Stock=999),rid='newer')

    def add(self, record, rid='published'):
        self.source.execute('INSERT INTO records VALUES(?,?,?,?)',(rid,'inventory',str(self.source.total_changes),json.dumps(record)))
        self.source.commit()

    def read(self, keys=None):
        return stock_snapshot.read(self.conn,'P',keys or {('BLACK','M')},self.path)

    def tearDown(self):
        self.source.close();self.conn.close();self.tmp.cleanup()

    def test_exact_source_fields_published_snapshot_and_primary_warehouses(self):
        result=self.read()
        self.assertEqual(result['warehouses'],['CENTRAL'])
        self.assertEqual(result['sourceRun'],'published')
        self.assertEqual(result['summary'],dict(stock=15,toReceive=29,clients=6,allocated=1,theoretical=37,available=14))
        self.assertEqual(result['completeVariants'],1)
        self.assertEqual(result['snapshotAt'],'2026-10-19T12:00:00Z')

    def test_missing_rows_and_missing_fields_are_not_zero(self):
        result=self.read({('BLACK','M'),('BLACK','XL')})
        self.assertIsNone(result['colors'][0]['stock']['XL'])
        self.assertIsNone(result['summary']['stock'])
        self.assertEqual(result['recordedSummary']['stock'],15)
        self.assertEqual(result['missingVariants'],1)
        self.add(dict(self.record,Taille='S',Theorique=None))
        result=self.read()
        self.assertIsNone(result['summary']['theoretical'])
        self.assertEqual(result['summary']['stock'],30)

    def test_negative_theoretical_and_real_zero_are_preserved_without_recalculation(self):
        self.add(dict(self.record,Taille='XL6',En_Stock=0,Disponible=0,Reliquat_Fournisseur=0,En_Commande=1,Attribue=0,Theorique=-1))
        result=self.read()
        self.assertEqual(result['colors'][0]['theoretical']['XL6'],-1)
        self.assertEqual(result['colors'][0]['stock']['XL6'],0)
        self.assertEqual(result['summary']['theoretical'],36)
        # Preserve source truth even if a row does not reconcile algebraically.
        self.add(dict(self.record,Taille='L',Theorique=123))
        self.assertEqual(self.read()['colors'][0]['theoretical']['L'],123)

    def test_all_primary_warehouses_required_and_duplicates_unknown(self):
        self.lineage['operatingScope']['warehouseRoles']['SECOND']='primary'
        self.conn.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",(json.dumps(self.lineage),))
        self.assertIsNone(self.read()['summary']['stock'])
        self.add(dict(self.record,Magasin='SECOND',En_Stock=2,Disponible=1))
        self.assertEqual(self.read()['summary']['stock'],17)
        self.add(self.record)
        self.assertIsNone(self.read()['summary']['stock'])

    def test_forecast_and_period_receipts_remain_separate(self):
        before=self.conn.total_changes
        result=projection_detail.detail(self.conn,'P',source_path=self.path)
        color=result['colorVariants'][0]
        self.assertEqual(color['recommendedQty']['M'],90)
        self.assertEqual(color['totalDeFournisseur']['M'],5)
        self.assertEqual(color['availableStock']['M'],11)
        self.assertEqual(color['totalDeLeStock']['M'],74)
        self.assertEqual(result['warehouseStock']['summary']['toReceive'],29)
        self.assertEqual(result['warehouseStock']['summary']['available'],14)
        self.assertEqual(self.conn.total_changes,before)

    def test_missing_or_incomplete_published_export_never_uses_newer_export(self):
        self.source.execute("UPDATE datasets SET metadata=? WHERE run_id='published'",(json.dumps(dict(complete=False)),));self.source.commit()
        self.assertIsNone(self.read())
        self.assertIsNone(stock_snapshot.read(self.conn,'P',set(),Path(self.tmp.name)/'absent.db'))

    def test_older_publication_without_roles_never_pools_other_stores(self):
        self.conn.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",(json.dumps(dict(freshRun='published')),))
        result=self.read()
        self.assertEqual(result['warehouses'],['CENTRAL'])
        self.assertEqual(result['summary']['stock'],15)

    def test_catalogue_only_sizes_remain_unknown_and_have_no_forecast(self):
        self.conn.execute("INSERT INTO catalogue_skus(sku,reference,color,size,current,source_run) VALUES('sku-x','P','BLACK','XL7',1,'published')")
        result=projection_detail.detail(self.conn,'P',source_path=self.path)
        self.assertIsNone(result['warehouseStock']['colors'][0]['stock']['XL7'])
        self.assertNotIn('XL7',result['colorVariants'][0]['recommendedQty'])


if __name__=='__main__':unittest.main()
