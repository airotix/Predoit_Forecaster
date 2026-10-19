import copy
import json
import unittest

import catalogue
import order_prices as prices
import purchase_draft
import test_budgeting as fixtures


class OrderPriceTests(unittest.TestCase):
    setUp = fixtures.BudgetTests.setUp
    tearDown = fixtures.BudgetTests.tearDown
    seed = fixtures.BudgetTests.seed
    report = fixtures.BudgetTests.report

    def row(self, currency='EUR'):
        catalogue.sync(self.c, self.path)
        return catalogue.listing(self.c, currency)['rows'][0]

    def add_sale(self, date, price, order=11, **changes):
        self.data['negoce_entetes'].append(dict(self.data['negoce_entetes'][0], Entete=order, Date=date))
        self.data['negoce_lignes'].append(dict(self.data['negoce_lignes'][0], Entete=order, Ligne=order * 10,
            Prix_HT_Devise=price, Total_HT_Devise=price * 2, **changes))
        self.seed()

    def test_latest_actual_order_replaces_master_and_average(self):
        self.add_sale('2026-10-03', 125)
        row = self.row()
        self.assertEqual((row['purchase'], row['selling']), (90, 125))
        self.assertEqual(row['purchasePriceDetails']['orderNumber'], 'PO2')
        self.assertEqual(row['sellingPriceDetails']['orderId'], '11')
        self.assertEqual(row['sellingPriceDetails']['customer'], 'C1')
        self.assertEqual(self.report()['rows'][0]['unitPrice'], 125)

    def test_future_and_cancelled_prices_are_excluded(self):
        self.add_sale('2026-10-08', 500)
        self.add_sale('2026-10-04', 600, order=12, Statut=2)
        self.assertEqual(self.row()['selling'], 100)
        self.assertEqual(self.row()['sellingPriceDetails']['orderDate'], '2026-09-01')

    def test_conflicting_latest_date_is_unknown_without_older_fallback(self):
        self.add_sale('2026-10-03', 125)
        self.add_sale('2026-10-03', 130, order=12)
        row = self.row()
        self.assertIsNone(row['selling'])
        self.assertIn('Conflicting', row['sellingPriceDetails']['reason'])
        self.assertIsNone(self.report()['rows'][0]['unitPrice'])

    def test_price_reconciliation_discount_and_native_currency(self):
        self.add_sale('2026-10-03', 150)
        line = self.data['negoce_lignes'][-1]
        line.update(Remise=10, Total_HT_Devise=270)
        self.seed()
        self.assertEqual(self.row()['selling'], 135)
        self.data['negoce_entetes'][-1]['Devise'] = '02'
        line.update(Devise='02')
        self.seed()
        self.assertEqual(self.row()['selling'], 100)
        self.assertEqual(self.row('USD')['selling'], 135)
        line.update(Total_HT_Devise=999)
        self.seed()
        self.assertIsNone(self.row('USD')['selling'])

    def test_no_master_or_tariff_fallback_when_orders_are_missing(self):
        self.data['commandes_produits'] = []
        self.data['negoce_lignes'] = []
        self.seed()
        row = self.row()
        self.assertIsNone(row['purchase'])
        self.assertIsNone(row['selling'])
        inputs = catalogue.price_map(self.c, 'EUR')[('P', 'B', 'M')]
        self.assertIsNone(inputs['purchase'])
        self.assertIsNone(self.report()['rows'][0]['unitCost'])

    def test_incomplete_source_cannot_select_a_misleading_latest_price(self):
        source = prices.f.connect(self.path)
        with source:
            source.execute("UPDATE datasets SET metadata=? WHERE run_id=? AND dataset='negoce_lignes'", (json.dumps(dict(complete=False)), self.rid))
        source.close()
        self.assertIsNone(self.row()['selling'])

    def test_manual_values_and_clears_survive_refresh_and_can_be_reset(self):
        self.row()
        catalogue.save_prices(self.c, [dict(sku='sku-P-B-M', purchase=7, selling=None)], 'EUR')
        self.add_sale('2026-10-03', 125)
        self.assertEqual((self.row()['purchase'], self.row()['selling']), (7, None))
        prices.reset(self.c, [dict(sku='sku-P-B-M', side='purchase'), dict(sku='sku-P-B-M', side='selling')], 'EUR')
        self.assertEqual((self.row()['purchase'], self.row()['selling']), (90, 125))

    def test_uniform_size_fallback_is_labelled_and_conflicts_prevent_it(self):
        self.data['skus'].append(dict(self.data['skus'][0], Sku='size-L', Taille='L'))
        self.seed()
        catalogue.sync(self.c, self.path)
        rows = {r['size']: r for r in catalogue.listing(self.c, 'EUR')['rows']}
        self.assertEqual(rows['L']['selling'], 100)
        self.assertIn('prices agree', rows['L']['sellingPriceDetails']['matchLevel'])
        self.add_sale('2026-10-03', 125)
        self.add_sale('2026-10-03', 130, order=12)
        catalogue.sync(self.c, self.path)
        self.assertTrue(all(r['selling'] is None for r in catalogue.listing(self.c, 'EUR')['rows']))

    def test_cutoff_prevents_future_price_leakage_and_change_keeps_provenance(self):
        self.row()
        self.add_sale('2026-10-03', 125)
        self.assertEqual(self.row()['sellingPriceDetails']['previousPrice'], 100)
        prices.sync(self.c, self.path, through_date='2026-09-30')
        self.assertEqual(catalogue.listing(self.c, 'EUR')['rows'][0]['selling'], 100)

    def test_nonbillable_or_nonprimary_orders_do_not_supply_selling_price(self):
        for changes in (dict(non_facturable=1), dict(Magasin='DEFECTUEUX'), dict(Magasin='CONSIGNMENT'), dict(Nature='FACTURE')):
            with self.subTest(changes=changes):
                original = copy.deepcopy(self.data['negoce_entetes'][0])
                self.data['negoce_entetes'][0].update(changes)
                self.seed()
                self.assertIsNone(self.row()['selling'])
                self.data['negoce_entetes'][0] = original

    def test_reused_document_ids_require_unique_store_customer_join(self):
        self.data['negoce_entetes'].append(dict(self.data['negoce_entetes'][0], Magasin='OTHER', Client='C2'))
        self.seed()
        self.assertIsNone(self.row()['selling'])
        self.data['negoce_lignes'][0].update(Magasin='CENTRAL',Client='C1')
        self.seed()
        self.assertEqual(self.row()['selling'],100)


class SavedDraftPriceTests(unittest.TestCase):
    def test_saved_automatic_prices_stay_until_explicit_refresh(self):
        from test_purchase_draft import PurchaseDraftTests
        fixture = PurchaseDraftTests();fixture.setUp()
        try:
            saved = fixture.save()
            original = saved['rows'][0]['orderUnitPrice']
            fixture.report['rows'][0]['unitPrice'] = 999
            current = purchase_draft.view(fixture.c, fixture.report)
            self.assertEqual(current['rows'][0]['orderUnitPrice'], original)
            self.assertTrue(current['draft']['stale'])
            kept = fixture.save()
            self.assertEqual(kept['rows'][0]['orderUnitPrice'], original)
            updated = fixture.save(refreshPrices=True)
            self.assertEqual(updated['rows'][0]['orderUnitPrice'], 999)
        finally:
            fixture.tearDown()
