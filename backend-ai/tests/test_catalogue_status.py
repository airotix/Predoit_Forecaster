import json
import sqlite3
import unittest

import buying
import catalogue
import catalogue_status as status
import planning
import test_budgeting as fixtures


class CatalogueStatusTests(unittest.TestCase):
    setUp = fixtures.BudgetTests.setUp
    tearDown = fixtures.BudgetTests.tearDown
    seed = fixtures.BudgetTests.seed
    report = fixtures.BudgetTests.report

    def prepare(self, article=1, sku=1):
        self.data['produits'][0]['Actif'] = article
        self.data['skus'][0]['Actif'] = sku
        self.seed()
        catalogue.sync(self.c,self.path)

    def change(self, level='sku', target='sku-P-B-M', active=False):
        return status.save(self.c,[dict(level=level,id=target,active=active,reason='Supplier discontinued this item')])

    def current(self):
        return status.lookup(self.c)['sku-P-B-M']

    def test_initial_values_are_from_article_and_sku_joolan_flags(self):
        self.prepare(article=1,sku=0)
        item=self.current()
        self.assertTrue(item['articleJoolan']);self.assertFalse(item['skuJoolan'])
        self.assertIsNone(item['skuOverride']);self.assertTrue(item['purchasingBlocked'])
        row=catalogue.listing(self.c,'EUR')['rows'][0]
        self.assertEqual(row['status'],item)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM catalogue_status_history').fetchone()[0],0)

    def test_article_override_blocks_every_variant_and_active_sku_cannot_bypass(self):
        self.prepare()
        self.data['skus'].append(dict(self.data['skus'][0],Sku='sku-L',Taille='L'))
        self.seed();catalogue.sync(self.c,self.path)
        self.change('article','P',False)
        self.change('sku','sku-L',True)
        self.assertTrue(all(item['purchasingBlocked'] for item in status.lookup(self.c).values()))
        self.change('article','P',True)
        self.assertFalse(any(item['purchasingBlocked'] for item in status.lookup(self.c).values()))

    def test_active_article_does_not_reactivate_inactive_sku(self):
        self.prepare(article=0,sku=0)
        self.change('article','P',True)
        self.assertTrue(self.current()['purchasingBlocked'])
        self.change(active=True)
        self.assertFalse(self.current()['purchasingBlocked'])

    def test_overrides_survive_refresh_and_reset_follows_latest_joolan_value(self):
        self.prepare()
        self.change(active=False)
        self.data['skus'][0]['Actif']=1
        self.seed();catalogue.sync(self.c,self.path,force=True)
        self.assertFalse(self.current()['active'])
        self.change(active=None)
        self.assertTrue(self.current()['active'])
        self.data['skus'][0]['Actif']=0
        self.seed();catalogue.sync(self.c,self.path)
        self.assertFalse(self.current()['active'])

    def test_unknown_flags_are_not_invented_as_inactive(self):
        self.prepare(article=None,sku='unexpected')
        item=self.current()
        self.assertIsNone(item['active']);self.assertFalse(item['purchasingBlocked'])
        self.assertEqual(catalogue.listing(self.c,'EUR',status='unknown')['total'],1)

    def test_status_filter_matches_article_without_truncating_its_breakdown(self):
        self.prepare()
        self.data['skus'].append(dict(self.data['skus'][0],Sku='sku-L',Taille='L',Actif=0))
        self.seed();catalogue.sync(self.c,self.path)
        result=catalogue.listing(self.c,'EUR',grouped=True,status='inactive')
        self.assertEqual(result['total'],1);self.assertEqual(len(result['rows']),2)
        self.assertEqual(catalogue.listing(self.c,'EUR',status='active')['total'],1)

    def test_default_purchase_zero_but_demand_and_prices_stay_visible(self):
        self.prepare(sku=0)
        row=self.report()['rows'][0]
        self.assertEqual(row['forecast'],20);self.assertEqual(row['purchaseQuantity'],0)
        self.assertEqual(row['unitCost'],90);self.assertEqual(row['unitPrice'],100)
        simulated=buying.simulate(self.report(),quantity_basis='forecast')
        self.assertEqual(simulated['rows'][0]['quantity'],0)
        self.assertEqual(simulated['articlePlan']['articles'][0]['status'],'inactive')
        final=planning.final_rows(self.c)[0]
        self.assertEqual(final['demand_forecast'],20);self.assertEqual(final['recommended_quantity'],0)
        self.assertTrue(final['purchasing_blocked'])

    def test_positive_manual_quantity_is_retained_but_cannot_be_reviewed_or_allocated(self):
        self.prepare(sku=0)
        report=self.report();ident=buying.identity(report['rows'][0])
        edits=[dict(id=ident,quantity=5,reason='Old draft')]
        result=buying.simulate(report,edits,'forecast')
        self.assertEqual(result['rows'][0]['quantity'],5)
        self.assertTrue(any('Inactive SKU' in check for check in result['rows'][0]['blockers']))
        self.assertNotIn(ident,result['covered']['rowIds'])
        self.assertEqual(result['articlePlan']['articles'][0]['status'],'inactive')
        with self.assertRaisesRegex(ValueError,'Inactive SKU'):
            buying.validate(self.c,report,edits,[ident],result['revision'],'forecast')

    def test_atomic_validation_rejects_bad_types_and_unknown_targets(self):
        self.prepare()
        for update in (dict(level='sku',id='sku-P-B-M',active='false'),dict(level='sku',id='missing',active=False)):
            with self.assertRaises(ValueError):
                status.save(self.c,[dict(level='article',id='P',active=False),update])
            self.assertTrue(self.current()['active'])
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM catalogue_status_history').fetchone()[0],0)

    def test_persistence_and_history_do_not_change_raw_source_or_prices(self):
        self.prepare()
        original=catalogue.price_map(self.c,'EUR')[('P','B','M')]
        self.change(active=False);self.change(active=None)
        records=status.history(self.c,'sku-P-B-M','P')
        self.assertEqual(len(records),2);self.assertIsNone(records[0]['active'])
        self.assertEqual(catalogue.price_map(self.c,'EUR')[('P','B','M')],original)
        path=self.path.parent/'status.db';disk=sqlite3.connect(path);self.c.backup(disk);disk.close()
        disk=sqlite3.connect(path)
        self.assertTrue(status.lookup(disk)['sku-P-B-M']['active']);disk.close()

    def test_forecast_publication_does_not_delete_status_overrides(self):
        import database
        self.prepare();self.change(active=False)
        database._create_schema(self.c)
        self.assertFalse(self.current()['active'])

    def test_saved_budget_quantities_are_not_silently_rewritten(self):
        import purchase_draft
        self.prepare()
        lineage=json.loads(self.c.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()[0])
        lineage['runId']='test-forecast'
        self.c.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",(json.dumps(lineage),));self.c.commit()
        report=self.report();view=purchase_draft.view(self.c,report)
        with self.c:
            purchase_draft.store(self.c,report,dict(version=0,forecastRun='test-forecast',revision=view['revision'],edits=[],selected=[]))
        before=purchase_draft.read(self.c,'base')
        self.change(active=False)
        after=purchase_draft.view(self.c,self.report())
        self.assertEqual(after['rows'][0]['quantity'],20)
        self.assertTrue(after['draft']['stale'])
        self.assertTrue(any('Inactive SKU' in check for check in after['rows'][0]['blockers']))
        self.assertEqual(purchase_draft.read(self.c,'base'),before)

    def test_api_status_save_filter_history_and_restore(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import fresh_joolan
        self.prepare()
        path=self.path.parent/'api-status.db';disk=sqlite3.connect(path);self.c.backup(disk);disk.close()
        app=FastAPI();catalogue.install(app,lambda:sqlite3.connect(path))
        with patch.object(fresh_joolan,'SOURCE_DB',self.path),TestClient(app) as client:
            response=client.put('/api/catalogue/status',json=dict(updates=[dict(level='sku',id='sku-P-B-M',active=False,reason='Discontinued')]))
            self.assertEqual(response.status_code,200,response.text)
            result=client.get('/api/catalogue?status=inactive&grouped=true').json()
            self.assertEqual(result['total'],1);self.assertFalse(result['rows'][0]['status']['active'])
            detail=client.get('/api/catalogue/sku/sku-P-B-M').json()
            self.assertEqual(detail['statusHistory'][0]['reason'],'Discontinued')
            response=client.put('/api/catalogue/status',json=dict(updates=[dict(level='sku',id='sku-P-B-M',active=None)]))
            self.assertEqual(response.status_code,200,response.text)
            self.assertTrue(client.get('/api/catalogue').json()['rows'][0]['status']['active'])


class InactivePOTests(unittest.TestCase):
    def test_po_creation_rejects_positive_inactive_quantities(self):
        from test_purchase_orders import PurchaseOrderTests
        fixture=PurchaseOrderTests();fixture.setUp()
        try:
            fixture.simulation['rows'][0]['purchasingBlocked']=True
            with self.assertRaisesRegex(ValueError,'blocked for purchasing'):
                fixture.create()
            self.assertEqual(fixture.c.execute('SELECT COUNT(*) FROM supplier_purchase_orders').fetchone()[0],0)
        finally:fixture.tearDown()

    def test_existing_po_keeps_snapshot_but_checks_live_status(self):
        from test_purchase_orders import PurchaseOrderTests
        fixture=PurchaseOrderTests();fixture.setUp()
        try:
            ident=fixture.create()['created'][0]
            payload=fixture.c.execute('SELECT payload FROM supplier_purchase_orders WHERE id=?',(ident,)).fetchone()[0]
            fixture.c.execute('INSERT INTO catalogue_skus VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('s1','A','BLACK','M','Jacket','DAYTONA73','Jackets','Supplier A',1,'run','now',json.dumps(dict(product=dict(Actif=1),sku=dict(Actif=1)))))
            status.sync_sources(fixture.c)
            status.save(fixture.c,[dict(level='sku',id='s1',active=False)])
            result=fixture.view(ident)
            self.assertTrue(any('Inactive SKU' in check for check in result['checks']))
            self.assertEqual(fixture.c.execute('SELECT payload FROM supplier_purchase_orders WHERE id=?',(ident,)).fetchone()[0],payload)
        finally:fixture.tearDown()
