import copy
import csv
import io
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import po_validation as validation
import purchase_orders as po
import test_purchase_orders as fixtures


class POValidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PurchaseOrderTests();self.fixture.setUp();self.c=self.fixture.c
        self.context=dict(seasonId='winter',forecastRun='forecast1',scenario='base')
        self.report=dict(summary=dict(currency='EUR',seasonBudget=150,targetMargin=40,budgetConfigured=True,
                                      knownCommittedCost=20,commitmentsComplete=True),
                         rows=[dict(r,stock=0,incoming=0,orderingRules={}) for r in self.fixture.simulation['rows']],
                         source=dict(runId='fresh1',historyThrough='2026-10-19'),supplierOptions=['Supplier A','Supplier B'])
        self.stamp=patch.object(po,'source_stamp',return_value='source1');self.stamp.start()
        self.ctx=patch('purchase_draft.context',side_effect=lambda *args:dict(self.context));self.ctx.start()

    def tearDown(self):
        self.ctx.stop();self.stamp.stop();self.fixture.tearDown()

    def draft(self):return self.fixture.create(mode='selected')['created'][0]
    def submit(self,ident,version=1):
        with self.c:return validation.submit(self.c,ident,version)
    def review(self,ident):return validation.review(self.c,ident,self.report)
    def finalize(self,ident,**changes):
        doc=po._read(self.c,ident)
        body=dict(version=doc['version'],reviewer='Test buyer',reason='Reviewed supplier, gross demand and financial totals',confirmed=True)
        with self.c:return validation.finalize(self.c,ident,{**body,**changes},self.report)

    def test_selected_budget_articles_go_to_editable_po_then_final_validation(self):
        ident=self.draft();self.assertEqual(po._read(self.c,ident)['status'],'draft')
        self.assertTrue(self.fixture.simulation['blockers']) # Unselected budget rows are unresolved.
        with self.assertRaises(ValueError):self.finalize(ident)
        self.submit(ident);review=self.review(ident)
        self.assertEqual(review['blockers'],[])
        self.assertEqual(review['budget']['remaining'],90)
        final=self.finalize(ident)
        self.assertEqual(final['status'],'validated');self.assertEqual(final['version'],3)
        self.assertEqual(final['validation']['confirmedSupplier'],'Supplier A')
        self.assertEqual(len(po.view(self.c,ident)['history']),2)
        file=po.export_csv(self.c,ident)
        self.assertTrue(file['filename'].endswith('-final.csv'))
        row=list(csv.DictReader(io.StringIO(file['csv'].removeprefix('\ufeff'))))[0]
        self.assertEqual(row['Status'],'VALIDATED - NOT SENT');self.assertEqual(row['Quantity'],'4')
        with self.assertRaises(ValueError):
            with self.c:po.update(self.c,ident,dict(version=3,edits=[dict(id=final['lines'][0]['id'],quantity=999)]))
        with self.assertRaises(ValueError):self.finalize(ident)

    def test_supplier_is_selected_in_po_and_pending_edits_return_to_draft(self):
        ident=self.draft()
        with self.c:po.update(self.c,ident,dict(version=1,supplier=''))
        self.submit(ident,2);self.assertIn('Select a supplier in the PO editor.',self.review(ident)['blockers'])
        with self.c:po.update(self.c,ident,dict(version=3,supplier='Supplier B',changeReason='Buyer selected alternate supplier'))
        self.assertEqual(po._read(self.c,ident)['status'],'draft')
        self.submit(ident,4);self.assertEqual(self.finalize(ident)['supplier'],'Supplier B')

    def test_prices_quantities_and_supplier_edits_survive_the_handoff(self):
        ident=self.draft();line=po._read(self.c,ident)['lines'][0]['id']
        with self.c:po.update(self.c,ident,dict(version=1,supplier='Supplier B',changeReason='Negotiated offer',
                                               edits=[dict(id=line,quantity=6,unitCost=12,unitPrice=40)]))
        self.submit(ident,2);final=self.finalize(ident)
        self.assertEqual((final['lines'][0]['quantity'],final['lines'][0]['unitCost'],final['lines'][0]['unitPrice']),(6,12,40))
        self.assertEqual(final['validation']['totals']['purchaseCost'],72)

    def test_current_stock_delivery_inactive_rules_and_margin_cannot_be_bypassed(self):
        ident=self.draft();self.submit(ident)
        for field,value in [('stock',None),('incoming',None),('requiresDeliveryReview',True),
                            ('purchasingBlocked',True),('orderingRules',dict(minUnits=10))]:
            original=copy.deepcopy(self.report['rows'][0]);self.report['rows'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.finalize(ident)
            self.report['rows'][0]=original
        self.report['summary']['targetMargin']=90
        with self.assertRaises(ValueError):self.finalize(ident)

    def test_budget_checks_use_other_created_pos_and_current_commitments(self):
        ident=self.draft();self.submit(ident)
        self.report['summary']['knownCommittedCost']=120
        with self.assertRaisesRegex(ValueError,'exceed'):self.finalize(ident)
        self.report['summary'].update(knownCommittedCost=20,commitmentsComplete=False)
        with self.assertRaisesRegex(ValueError,'commitments are incomplete'):self.finalize(ident)
        self.report['summary']['commitmentsComplete']=True
        others=self.fixture.create(mode='all')['created']
        self.assertTrue(others)
        with self.assertRaisesRegex(ValueError,'unresolved purchase costs'):self.finalize(ident)
        for other in others:
            with self.c:po.update(self.c,other,dict(version=1,status='cancelled'))
        self.assertEqual(self.finalize(ident)['status'],'validated')

    def test_validated_pos_from_other_publications_and_scenarios_consume_budget(self):
        first=self.draft();self.submit(first);self.finalize(first)
        self.fixture.simulation['draft'].update(forecastRun='forecast2',scenario='optimistic')
        self.fixture.simulation['scenario']='optimistic'
        self.fixture.body['forecastRun']='forecast2'
        second=self.draft();self.context.update(forecastRun='forecast2',scenario='optimistic')
        self.submit(second);self.report['summary']['seasonBudget']=90
        self.assertEqual(self.review(second)['budget']['knownPOCost'],80)
        with self.assertRaisesRegex(ValueError,'exceed'):self.finalize(second)

    def test_finalization_requires_current_version_and_explicit_review(self):
        ident=self.draft();self.submit(ident)
        for values in [dict(version=True),dict(version=1),dict(reviewer=''),dict(reason=''),dict(confirmed=False)]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.finalize(ident,**values)
        self.assertEqual(po._read(self.c,ident)['version'],2)
        self.context['forecastRun']='new-publication'
        with self.assertRaisesRegex(ValueError,'another season or forecast'):self.finalize(ident)

    def test_missing_selected_quantity_is_not_silently_dropped_from_the_po(self):
        self.fixture.simulation['rows'][0]['quantity']=None
        with self.assertRaisesRegex(ValueError,'Set an order quantity'):self.draft()

    def test_native_supplier_currency_is_retained_in_final_export(self):
        row=self.fixture.simulation['rows'][0]
        row.update(quoteId='usd',quotes=[dict(id='usd',supplier='Supplier A',unitCost=10,
            fx=dict(nativeCurrency='USD',nativeUnitCost=12.5,exchangeRate=1.25))])
        ident=self.draft();self.submit(ident);self.finalize(ident)
        exported=list(csv.DictReader(io.StringIO(po.export_csv(self.c,ident)['csv'].removeprefix('\ufeff'))))[0]
        self.assertEqual(exported['Currency'],'USD');self.assertEqual(float(exported['Line purchase cost']),50)

    def test_catalogue_fx_survives_without_a_budget_supplier_selection(self):
        row=self.fixture.simulation['rows'][0]
        row['purchasePriceDetails']=dict(supplier='Supplier A',currency='EUR',price=10,orderId='order-55',
            fx=dict(nativeCurrency='USD',nativeUnitCost=12.5,exchangeRate=1.25))
        ident=self.draft();doc=po._read(self.c,ident)
        self.assertEqual(doc['supplierCurrency'],'USD');self.assertEqual(doc['lines'][0]['supplierUnitCost'],12.5)
        self.assertEqual(doc['lines'][0]['purchasePriceDetails']['orderId'],'order-55')
        self.submit(ident);self.finalize(ident)

    def test_http_create_edit_submit_review_finalize_download_and_lock(self):
        class Connection:
            def __getattr__(inner,name):return getattr(self.c,name)
            def close(inner):pass
            def __enter__(inner):return self.c.__enter__()
            def __exit__(inner,*args):return self.c.__exit__(*args)
        app=FastAPI();po.install(app,Connection);client=TestClient(app)
        with patch('catalogue.sync'),patch('budgeting.build_report',return_value=self.report),patch('purchase_draft.view',return_value=self.fixture.simulation):
            created=client.post('/api/purchase-orders',json={**self.fixture.body,'mode':'selected'})
            self.assertEqual(created.status_code,200,created.text);ident=created.json()['created'][0]
            self.assertEqual(client.get(f'/api/purchase-orders/{ident}/final-export').status_code,409)
            sent=client.post(f'/api/purchase-orders/{ident}/submit',json=dict(version=1))
            self.assertEqual(sent.status_code,200,sent.text)
            review=client.get(f'/api/purchase-orders/{ident}/validation')
            self.assertEqual(review.status_code,200,review.text);self.assertEqual(review.json()['blockers'],[])
            final=client.post(f'/api/purchase-orders/{ident}/validate',json=dict(version=2,reviewer='Buyer',reason='Reviewed',confirmed=True))
            self.assertEqual(final.status_code,200,final.text)
            self.assertIn('-final.csv',client.get(f'/api/purchase-orders/{ident}/final-export').json()['filename'])
            self.assertEqual(client.put(f'/api/purchase-orders/{ident}',json=dict(version=3,supplier='Other')).status_code,409)


if __name__=='__main__':unittest.main()
