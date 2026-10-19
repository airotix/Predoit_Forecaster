import copy
import csv
import io
import json
import unittest
from unittest.mock import patch

import buying
import price_review
import purchase_orders
import test_buying as buying_fixtures
import test_purchase_draft as draft_fixtures


class SupplierEvidenceTests(unittest.TestCase):
    def setUp(self):
        fixture=buying_fixtures.BuyingTests();fixture.setUp()
        self.report=fixture.report;self.ident=fixture.key

    def test_last_catalogue_order_is_selectable_outside_commitment_period(self):
        self.report['purchaseOrders']=[]
        self.report['rows'][0]['purchasePriceDetails']=dict(supplier='Supplier',currency='EUR',price=41,
            orderId='last-year',orderDate='2025-09-01',matchLevel='Same article and colour · matching prices agree')
        quote=buying.simulate(self.report)['rows'][0]['quotes'][0]
        self.assertEqual(quote['date'],'2025-09-01')
        result=buying.simulate(self.report,[dict(id=self.ident,quoteId=quote['id'],reason='Confirmed last supplier transaction')])
        self.assertEqual(result['rows'][0]['orderUnitCost'],41)
        self.assertEqual(result['rows'][0]['supplier'],'Supplier')
        self.assertEqual(result['rows'][0]['blockers'],[])

    def test_quote_ids_are_stable_on_ledger_reorder_but_change_with_price(self):
        original=buying.simulate(self.report)['rows'][0]['quotes'][0]['id']
        other=copy.deepcopy(self.report['purchaseOrders'][0]);other.update(reference='Other',orderId='other')
        self.report['purchaseOrders'].insert(0,other)
        self.assertEqual(buying.simulate(self.report)['rows'][0]['quotes'][0]['id'],original)
        self.report['purchaseOrders'][1]['unitCost']=50
        with self.assertRaisesRegex(ValueError,'Supplier price changed'):
            buying.simulate(self.report,[dict(id=self.ident,quoteId=original)])

    def test_manual_catalogue_selling_price_still_needs_confirmation(self):
        self.report['rows'][0]['catalogueSellingManual']=True
        row=buying.simulate(self.report,[dict(id=self.ident,quoteId='0',reason='Supplier selected')])['rows'][0]
        self.assertIn('Price assumptions are simulation only',row['blockers'])

    def test_foreign_evidence_and_unknown_manual_supplier_are_rejected(self):
        self.report['rows'][0]['purchasePriceDetails']=dict(supplier='Foreign',currency='USD',price=41,orderId='1',orderDate='2026-09-01')
        self.assertEqual(len(buying.simulate(self.report)['rows'][0]['quotes']),1)
        with self.assertRaisesRegex(ValueError,'saved Joolan'):
            buying.simulate(self.report,[dict(id=self.ident,supplier='Invented supplier')])


class PriceReviewApiTests(unittest.TestCase):
    setUp=draft_fixtures.DraftApiTests.setUp
    connect=draft_fixtures.DraftApiTests.connect
    tearDown=draft_fixtures.DraftApiTests.tearDown

    def save(self,**overrides):
        current=self.client.get('/api/budget/draft').json()
        edits=dict(id=self.ident,quantity=7,quoteId=current['rows'][0]['quotes'][0]['id'],
                   unitCost=45,unitPrice=110,reason='Agreed supplier update and wholesale price')
        edits.update(overrides)
        body=dict(scenario='base',version=current['draft']['version'],forecastRun='forecast1',revision=current['revision'],edits=[edits],selected=[self.ident])
        response=self.client.put('/api/budget/draft',json=body)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def confirm(self,saved,**changes):
        body=dict(scenario='base',version=saved['draft']['version'],forecastRun='forecast1',revision=saved['revision'],
                  selected=[self.ident],reviewer='Buyer',reason='Confirmed current supplier agreement and selling price')
        body.update(changes)
        return self.client.post('/api/budget/draft/prices/review',json=body)

    def test_saved_override_confirmation_financial_review_and_po_csv_reconcile(self):
        self.report['season']['name']='Winter';self.report['settings']['warehouses']=['CENTRAL']
        purchase_orders.install(self.client.app,self.connect)
        saved=self.save()
        review_body=dict(scenario='base',version=1,forecastRun='forecast1')
        self.assertEqual(self.client.post('/api/budget/draft/review',json=review_body).status_code,409)
        confirmed=self.confirm(saved)
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        current=confirmed.json();row=current['rows'][0]
        self.assertEqual(row['blockers'],[])
        self.assertEqual(row['orderCost'],315)
        self.assertEqual(row['orderTurnover'],770)
        self.assertEqual(row['orderGrossMargin'],455)
        self.assertEqual(row['priceReview']['reviewer'],'Buyer')
        reviewed=self.client.post('/api/budget/draft/review',json=review_body)
        self.assertEqual(reviewed.status_code,200,reviewed.text)
        self.assertEqual(reviewed.json()['orders'][0]['priceReview']['id'],row['priceReview']['id'])
        with patch.object(purchase_orders,'source_stamp',return_value='source1'):
            created=self.client.post('/api/purchase-orders',json=dict(scenario='base',version=1,forecastRun='forecast1',revision=current['revision'],mode='selected'))
            self.assertEqual(created.status_code,200,created.text)
            ident=created.json()['created'][0]
            doc=self.client.get('/api/purchase-orders/'+ident).json()
            self.assertEqual(doc['supplier'],'Supplier')
            self.assertEqual(doc['totals']['purchaseCost'],315)
            self.assertEqual(doc['totals']['turnover'],770)
            self.assertEqual(doc['lines'][0]['priceReview']['id'],row['priceReview']['id'])
            exported=self.client.get('/api/purchase-orders/'+ident+'/export').json()
            records=list(csv.DictReader(io.StringIO(exported['csv'].removeprefix('\ufeff'))))
            self.assertEqual(float(records[0]['Quantity']),7)
            self.assertEqual(float(records[0]['Purchase / unit']),45)
            self.assertEqual(float(records[0]['Line purchase cost']),315)
            edited=self.client.put('/api/purchase-orders/'+ident,json=dict(version=1,changeReason='New PO-only selling assumption',edits=[dict(id=self.ident,unitPrice=120)]))
            self.assertEqual(edited.status_code,200,edited.text)
            self.assertIsNone(edited.json()['lines'][0]['priceReview'])
            self.assertEqual(edited.json()['lines'][0]['budgetPriceReview']['id'],row['priceReview']['id'])
            self.assertTrue(any('differ from the budget price confirmation' in c for c in edited.json()['checks']))
        # Later draft changes invalidate the price confirmation, not old reviews.
        self.save(unitCost=46)
        changed=self.client.get('/api/budget/draft').json()
        self.assertIsNone(changed['rows'][0]['priceReview'])
        self.assertIn('Price assumptions are simulation only',changed['rows'][0]['blockers'])
        self.assertEqual(self.client.get('/api/budget/reviews').json()[0]['orders'][0]['orderUnitCost'],45)

    def test_confirmation_survives_reload_but_not_supplier_source_or_currency_changes(self):
        saved=self.save()
        self.assertEqual(self.confirm(saved).status_code,200)
        self.assertIsNotNone(self.client.get('/api/budget/draft').json()['rows'][0]['priceReview'])
        # Source/settings revisions cannot reuse an earlier confirmation.
        self.report['source']['revision']='new-source'
        current=self.client.get('/api/budget/draft').json()
        self.assertTrue(current['draft']['stale'])
        self.assertIsNone(current['rows'][0]['priceReview'])
        self.assertEqual(self.confirm(saved).status_code,409)

    def test_selecting_same_quote_restores_order_cost_and_preserves_old_archive(self):
        saved=self.save()
        body=dict(scenario='base',version=1,forecastRun='forecast1',revision=saved['revision'],selected=[self.ident],
                  edits=[dict(id=self.ident,quoteId=saved['rows'][0]['quoteId'],reason='Restore original supplier price')])
        restored=self.client.put('/api/budget/draft',json=body)
        self.assertEqual(restored.status_code,200,restored.text)
        self.assertEqual(restored.json()['rows'][0]['orderUnitCost'],40)
        self.assertEqual(self.client.get('/api/budget/draft').json()['rows'][0]['orderUnitCost'],40)
        c=self.connect()
        previous=json.loads(c.execute("SELECT value FROM planning_state WHERE key LIKE 'purchase_draft:%:version:1'").fetchone()[0])
        self.assertEqual(previous['resolvedInputs'][self.ident]['cost'],45)
        c.close()

    def test_supplier_and_currency_changes_require_new_confirmation(self):
        self.report['supplierOptions']=['Supplier','Replacement']
        saved=self.save();self.assertEqual(self.confirm(saved).status_code,200)
        changed=self.save(quoteId='',supplier='Replacement')
        self.assertIsNone(changed['rows'][0]['priceReview'])
        self.assertIn('Price assumptions are simulation only',changed['rows'][0]['blockers'])
        self.assertEqual(self.confirm(changed).status_code,200)
        self.report['summary']['currency']='USD'
        current=self.client.get('/api/budget/draft').json()
        self.assertTrue(current['draft']['currencyChanged'])
        self.assertIsNone(current['rows'][0]['priceReview'])

    def test_removing_an_edit_field_does_not_approve_its_retained_snapshot_price(self):
        saved=self.save()
        response=self.client.put('/api/budget/draft',json=dict(scenario='base',version=1,forecastRun='forecast1',revision=saved['revision'],selected=[self.ident],
            edits=[dict(id=self.ident,quoteId=saved['rows'][0]['quoteId'],reason='Keep saved selling assumption')]))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['rows'][0]['orderUnitPrice'],110)
        self.assertIn('Price assumptions are simulation only',response.json()['rows'][0]['blockers'])

    def test_known_supplier_manual_price_can_be_reviewed_without_any_quote(self):
        self.report['purchaseOrders']=[];self.report['supplierOptions']=['Supplier']
        current=self.client.get('/api/budget/draft').json()
        response=self.client.put('/api/budget/draft',json=dict(scenario='base',version=0,forecastRun='forecast1',revision=current['revision'],
            selected=[self.ident],edits=[dict(id=self.ident,supplier='Supplier',unitCost=42,unitPrice=110,reason='Agreed replacement price')]))
        self.assertEqual(response.status_code,200,response.text)
        confirmed=self.confirm(response.json())
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        self.assertEqual(confirmed.json()['rows'][0]['blockers'],[])

    def test_confirmation_never_clears_stock_budget_or_margin_blocks(self):
        self.report['rows'][0]['stock']=None
        self.report['summary']['seasonBudget']=10
        saved=self.save(unitPrice=46)
        current=self.confirm(saved).json()
        self.assertIn('Stock or incoming supply unresolved',current['rows'][0]['blockers'])
        self.assertIn('Below margin target',current['rows'][0]['blockers'])
        self.assertIn('Buying budget exceeded',current['blockers'])
        self.assertEqual(self.client.post('/api/budget/draft/review',json=dict(scenario='base',version=1,forecastRun='forecast1')).status_code,409)

    def test_missing_prices_invalid_reviewer_stale_version_and_spoofed_approval_rejected_atomically(self):
        saved=self.save(unitPrice=None)
        for change in ({},{'reviewer':''},{'reason':''},{'version':True},{'selected':['outside']}):
            self.assertEqual(self.confirm(saved,**change).status_code,409)
        c=self.connect()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM planning_state WHERE key LIKE 'price_review:%'").fetchone()[0],0)
        c.close()
        for field in ('priceReview','priceReviewRequired'):
            response=self.client.put('/api/budget/draft',json=dict(scenario='base',version=1,forecastRun='forecast1',revision=saved['revision'],
                edits=[dict(id=self.ident,**{field:True})]))
            self.assertEqual(response.status_code,409)

    def test_confirmations_are_context_scoped_and_do_not_change_joolan_or_catalogue(self):
        saved=self.save();self.assertEqual(self.confirm(saved).status_code,200)
        c=self.connect()
        context=dict(seasonId='winter',forecastRun='forecast1',sourceRun='source1',scopeRevision=None,scenario='base')
        self.assertEqual(len(price_review.approvals(c,context)),1)
        self.assertEqual(price_review.approvals(c,{**context,'forecastRun':'another-run'}),{})
        record=json.loads(c.execute("SELECT value FROM planning_state WHERE key LIKE 'price_review:%'").fetchone()[0])
        self.assertIn('not verified',record['identityBasis'])
        c.close()
