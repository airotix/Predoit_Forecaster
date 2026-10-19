import copy
import csv
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

import budgeting as b
import catalogue
import database
import fresh_joolan as fresh
import purchase_orders as po
import purchasing_inputs
import supplier_fx as fx
import test_budgeting as fixtures
import test_purchase_orders as po_fixtures


def evidence():
    return [dict(Mouvement=1,Nature='Réception',Devise='USD',Taux_Devise=1.25,Prix_Achat_Devise=125,Prix_Achat=100),
            dict(Mouvement=2,Nature='Réception',Devise='USD',Taux_Devise=1.25,Prix_Achat_Devise=50,Prix_Achat=40),
            dict(Mouvement=3,Nature='Réception',Devise='EUR',Taux_Devise=1,Prix_Achat_Devise=10,Prix_Achat=10)]


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.execute('CREATE TABLE planning_state(key TEXT PRIMARY KEY,value TEXT)')
    def tearDown(self):self.c.close()
    def test_verified_direction_and_pair_are_persisted_and_tenant_scoped(self):
        record=fx.verify(self.c,evidence(),{'USD':'USD','EUR':'EUR'},'test')
        converted=fx.convert(125,'USD','EUR',1.25,record)
        self.assertEqual(converted['unitCost'],100)
        self.assertEqual(converted['nativeUnitCost'],125)
        self.assertEqual(converted['rateSource'],'commandes.Taux_Devise')
        self.assertEqual(fx.policy(self.c,dict(enseigne='other')),{})
        self.assertIsNone(fx.convert(100,'GBP','EUR',1.25,record))
    def test_ambiguous_inconsistent_or_missing_base_evidence_cannot_enable_fx(self):
        for rows in [evidence()[:2],evidence()[1:], [dict(r,Taux_Devise=1) for r in evidence()],
                     [dict(r,Prix_Achat=1) if r['Devise']=='USD' else r for r in evidence()]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):fx.verify(self.c,rows,{'USD':'USD','EUR':'EUR'},'test')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM planning_state').fetchone()[0],0)
    def test_missing_nonfinite_and_nonpositive_rates_are_not_defaulted(self):
        record=fx.verify(self.c,evidence(),{'USD':'USD','EUR':'EUR'},'test')
        for rate in [None,0,-1,True,float('inf'),'']:
            self.assertIsNone(fx.convert(125,'USD','EUR',rate,record))
        self.assertIsNone(fx.convert(125,'USD','EUR',1.25,{}))
        self.assertIsNone(fx.convert(125,None,'EUR',1.25,record))
        self.assertIsNone(fx.convert(.000000001,'USD','EUR',1.25,record))
    def test_reference_nom_must_be_an_explicit_supported_iso_code(self):
        mapping=b._currency_map({'currencies':[dict(Devise='02',Nom='USD'),dict(Devise='03',Nom='American dollar')]})
        self.assertEqual(mapping['02'],'USD');self.assertNotIn('03',mapping)


class ImportedFXTests(unittest.TestCase):
    setUp=fixtures.BudgetTests.setUp
    tearDown=fixtures.BudgetTests.tearDown
    seed=fixtures.BudgetTests.seed
    report=fixtures.BudgetTests.report

    def enable(self):return fx.verify(self.c,evidence(),{'USD':'USD','EUR':'EUR'},'test')
    def row(self):catalogue.sync(self.c,self.path);return catalogue.listing(self.c,'EUR')['rows'][0]
    def test_latest_foreign_order_can_supply_traceable_eur_catalogue_default(self):
        self.enable();self.data['commandes'][1].update(Devise='02',Taux_Devise=1.25);self.seed()
        row=self.row()
        self.assertEqual(row['purchase'],72)
        self.assertEqual(row['purchasePriceDetails']['fx']['nativeUnitCost'],90)
        self.assertEqual(row['purchasePriceDetails']['fx']['exchangeRate'],1.25)
        self.assertEqual(row['purchasePriceDetails']['orderId'],'2')
    def test_native_currency_survives_and_manual_values_are_never_overwritten(self):
        self.enable();self.data['commandes'][1].update(Devise='02',Taux_Devise=1.25);self.seed();self.row()
        self.assertEqual(catalogue.listing(self.c,'USD')['rows'][0]['purchase'],90)
        catalogue.save_prices(self.c,[dict(sku='sku-P-B-M',purchase=7)],'EUR')
        self.assertEqual(self.row()['purchase'],7)
    def test_zero_order_price_is_not_replaced_by_sku_master_or_a_zero_cost(self):
        self.enable()
        for line in self.data['commandes_produits']:line['Prix_Achat_Devise']=0
        self.seed();row=self.row()
        self.assertIsNone(row['purchase'])
        self.assertEqual(row['purchasePriceDetails']['reasonCode'],'ZERO_OR_INVALID_PRICE')
    def test_different_supplier_is_a_review_candidate_not_an_automatic_default(self):
        self.data['produits'][0]['Fournisseur']='New supplier';self.seed();row=self.row()
        self.assertIsNone(row['purchase'])
        detail=row['purchasePriceDetails'];self.assertEqual(detail['reasonCode'],'SUPPLIER_CHANGED')
        self.assertEqual(detail['alternatives'][0]['supplier'],'Supplier')
        self.assertTrue(detail['alternatives'][0]['requiresReview'])
        import buying
        report=self.report();result=buying.simulate(report)
        candidate=result['rows'][0]['quotes'][0]
        self.assertTrue(candidate['requiresReview'])
        selected=buying.simulate(report,[dict(id=result['rows'][0]['id'],quoteId=candidate['id'],reason='Review alternative')])
        self.assertIn('Price assumptions are simulation only',selected['rows'][0]['blockers'])
    def test_missing_rate_keeps_foreign_price_visible_without_an_eur_guess(self):
        self.enable();self.data['commandes']=self.data['commandes'][1:]
        self.data['commandes'][0].update(Devise='02',Taux_Devise=None)
        self.data['commandes_produits']=self.data['commandes_produits'][1:];self.seed();row=self.row()
        self.assertIsNone(row['purchase'])
        self.assertEqual(row['purchasePriceDetails']['reasonCode'],'FX_UNAVAILABLE')
        self.assertEqual(row['purchasePriceDetails']['otherCurrencyCandidates'][0]['price'],90)
    def test_commitments_keep_native_value_and_use_the_same_recorded_rate(self):
        self.enable();self.data['commandes'][0].update(Devise='02',Taux_Devise=1.25);self.seed()
        report=self.report();order=report['purchaseOrders'][0]
        self.assertEqual(order['currency'],'USD')
        self.assertEqual(order['nativeValue'],769.5)
        self.assertEqual(order['value'],615.6)
        self.assertEqual(report['summary']['committedCost'],615.6)
    def test_a_receipt_past_due_inside_the_season_is_not_counted_as_scheduled_supply(self):
        self.data['commandes'][0]['Date_Livraison']='2026-10-05';self.seed();report=self.report()
        self.assertIsNone(report['rows'][0]['incoming'])
        self.assertIn('Overdue',report['rows'][0]['inputIssues']['incoming'])


class NativePOTests(unittest.TestCase):
    def setUp(self):
        self.fixture=po_fixtures.PurchaseOrderTests();self.fixture.setUp()
        self.c=self.fixture.c;self.simulation=self.fixture.simulation
        self.native=dict(unitCost=10,currency='EUR',nativeUnitCost=12.5,nativeCurrency='USD',exchangeRate=1.25,
            verificationId='verified',method='native / recorded order rate')
        for row in self.simulation['rows'][:2]:
            row['quotes']=[dict(id='usd',supplier='Supplier A',fx=self.native,unitCost=10)]
            row['quoteId']='usd'
    def tearDown(self):self.fixture.tearDown()
    def view(self,ident):return self.fixture.view(ident)
    def test_po_csv_is_in_supplier_currency_but_financial_totals_are_in_eur(self):
        result=self.fixture.create(mode='selected');doc=self.view(result['created'][0])
        self.assertEqual(doc['currency'],'EUR');self.assertEqual(doc['supplierCurrency'],'USD')
        self.assertEqual(doc['totals']['purchaseCost'],40)
        self.assertEqual(doc['supplierTotals']['purchaseCost'],50)
        with patch.object(po,'source_stamp',return_value='source1'):export=po.export_csv(self.c,doc['id'])
        rows=list(csv.DictReader(io.StringIO(export['csv'].removeprefix('\ufeff'))))
        self.assertEqual(rows[0]['Currency'],'USD')
        self.assertEqual(float(rows[0]['Purchase / unit']),12.5)
        self.assertEqual(float(rows[0]['Line purchase cost']),50)
    def test_native_edit_recalculates_budget_cost_and_currency_groups_do_not_mix(self):
        self.simulation['rows'][1]['quotes']=[];self.simulation['rows'][1]['quoteId']=''
        docs=[self.view(i) for i in self.fixture.create()['created']]
        usd=next(d for d in docs if d['supplierCurrency']=='USD')
        self.assertTrue(any(d['supplierCurrency']=='EUR' and d['supplier']=='Supplier A' for d in docs))
        line=usd['lines'][0]['id']
        with self.c:po.update(self.c,usd['id'],dict(version=1,changeReason='Supplier negotiated USD cost',edits=[dict(id=line,supplierUnitCost=25)]))
        updated=self.view(usd['id'])
        self.assertEqual(updated['lines'][0]['unitCost'],20)
        self.assertEqual(updated['totals']['purchaseCost'],80)
        self.assertEqual(updated['supplierTotals']['purchaseCost'],100)
        with self.assertRaises(ValueError):
            with self.c:po.update(self.c,usd['id'],dict(version=2,edits=[dict(id=line,supplierUnitCost=20,unitCost=10)]))

    def test_native_price_amendment_requires_a_reason_even_if_budget_rounding_hides_it(self):
        result=self.fixture.create(mode='selected');ident=result['created'][0]
        doc=self.view(ident);line=doc['lines'][0]
        with self.c:po.update(self.c,ident,dict(version=1,edits=[dict(id=line['id'],supplierUnitCost=12.5000001)]))
        updated=self.view(ident)
        self.assertEqual(updated['lines'][0]['unitCost'],line['unitCost'])
        self.assertIn('Record a reason for the PO quantity or price changes.',updated['checks'])


class ReconciliationTests(unittest.TestCase):
    def test_filters_and_counts_keep_missing_source_and_draft_values_distinct(self):
        fixture=po_fixtures.fixture();row=fixture['rows'][0]
        for r in fixture['rows']:r.update(unitCost=None,unitPrice=30,stock=None,incoming=None)
        fixture['context']['source']=dict(historyThrough='2026-10-19')
        report=purchasing_inputs.view(fixture,'purchase','A',0,1)
        self.assertEqual(report['summary']['purchase'],3)
        self.assertEqual(len(report['rows']),1)
        self.assertEqual(report['rows'][0]['draftPurchaseCost'],10)
        self.assertIsNone(report['rows'][0]['purchaseCost'])
        with self.assertRaises(ValueError):purchasing_inputs.view(fixture,'invented')
