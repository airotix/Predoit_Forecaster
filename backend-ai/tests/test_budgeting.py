import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import budgeting as b
import database
import fresh_joolan as f
import joolan
import planning


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'source.db'
        self.c=sqlite3.connect(':memory:');database._create_persistent_tables(self.c);database._create_schema(self.c);joolan.ensure_joolan_schema(self.c)
        self.plan=planning.save_season(self.c,dict(name='Winter',startDate='2026-10-01',endDate='2027-03-31',currency='EUR',budget=2000,targetMargin=30))
        self.rid=f.create_run(dict(enseigne='test',documentType='COMMANDE',throughDate='2026-10-07',warehouses=['CENTRAL','DEFECTUEUX'],brands=['DAYTONA73','OTHER']),self.path)
        source=f.connect(self.path);f.update(source,self.rid,status='validated');source.close()
        self.c.execute("INSERT OR REPLACE INTO joolan_state VALUES('fresh_run',?)",(self.rid,))
        self.c.execute('INSERT OR REPLACE INTO pipeline_metadata VALUES(?,?,?)',('lineage',json.dumps(dict(seasonId=self.plan['id'],plan=self.plan,freshRun=self.rid)),'now'))
        self.c.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,financial_note,famille) VALUES('P','B','M',20,10,30,'INVENTORY_UNKNOWN;PRICE_UNKNOWN;COST_UNKNOWN','Jackets')")
        self.c.commit()
        self.data=dict(
          produits=[dict(Produit='P',Marque='DAYTONA73',Famille='Jackets',Designation='Jacket',Taux_TVA_Vente=20),dict(Produit='Q',Marque='OTHER',Famille='Other')],
          skus=[dict(Sku='sku-P-B-M',Produit='P',Couleur='B',Taille='M',Prix_Achat=100,Remise_Achat=10,Prix_Achat_Moyen=80)],
          inventory=[dict(Magasin='central',Produit='P',Couleur='B',Taille='M',Disponible=2,En_Livraison=0)],
          commandes=[dict(Commande=1,Numero_Commande='PO1',Fournisseur='Supplier',Date='2026-09-01',Statut='Validée',Devise='01',Date_Livraison='2026-11-01',Remise1=10,Remise2=5,Remise3=0,Remise4=0,Remise5=0),
                     dict(Commande=2,Numero_Commande='PO2',Fournisseur='Supplier',Date='2026-10-01',Statut='Soldée',Devise='01',Remise1=0,Remise2=0,Remise3=0,Remise4=0,Remise5=0)],
          commandes_produits=[dict(Commande=1,Produit='P',Couleur='B',Taille='M',Prix_Achat_Devise=100,Remise_Achat=10),dict(Commande=2,Produit='P',Couleur='B',Taille='M',Prix_Achat_Devise=90,Remise_Achat=0)],
          commandes_quantites=[dict(Commande=1,Produit='P',Couleur='B',Taille='M',Magasin='CENTRAL',Statut='Validée',Quantite=10,Quantite_Livree=2)],
          tarifs=[dict(Tarif='Negoce',Libelle='Wholesale',HT=0)],
          tarifsproduits=[dict(Tarif='Negoce',Produit='P',Couleur='B',Taille='M',Prix_Vente=120,Remise_Vente=0)],
          devises=[dict(Devise='01',currency_code='EUR',Code='EUR',Nom='Euro'),dict(Devise='02',currency_code='USD',Code='USD',Nom='Dollar')],
          negoce_entetes=[dict(Entete=10,Date='2026-09-01',Client='C1',Magasin='CENTRAL',Nature='COMMANDE',Statut=1,non_facturable=0,Devise='01')],
          negoce_lignes=[dict(Entete=10,Ligne=100,Produit='P',Couleur='B',Taille='M',Nature='COMMANDE',Statut=1,Devise='01',Quantite=2,Prix_HT_Devise=100,Remise=0,Total_HT_Devise=200)])
        self.seed()
        b.save_settings(self.c,dict(costBasisVerified=True,tariffVerified=True,poCostsVerified=True,budgetConfigured=True))
    def tearDown(self):
        b._load_source.cache_clear();b._load_tariff.cache_clear();b._load_currencies.cache_clear();self.c.close();self.tmp.cleanup()
    def seed(self):
        source=f.connect(self.path)
        try:
            with source:
                for dataset,rows in self.data.items():
                    source.execute('DELETE FROM records WHERE run_id=? AND dataset=?',(self.rid,dataset))
                    source.executemany('INSERT INTO records VALUES(?,?,?,?)',[(self.rid,dataset,str(i),f.encode(row)) for i,row in enumerate(rows)])
                    source.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(self.rid,dataset,f.encode(dict(complete=True,expected=len(rows),count=len(rows),fetchedAt=f.now()))))
        finally:source.close()
    def report(self,scenario='base'):return b.build_report(self.c,scenario,self.path)
    def test_budget_counts_existing_po_once_and_nets_receipts_against_new_purchases(self):
        report=self.report();row=report['rows'][0];s=report['summary']
        self.assertEqual(row['incoming'],8)
        self.assertEqual(row['purchaseQuantity'],10)
        self.assertEqual(row['purchaseCost'],900)
        self.assertEqual(s['committedCost'],769.5)
        self.assertEqual(s['knownBudgetUsage'],1669.5)
        self.assertEqual(s['remainingBudget'],330.5)
        self.assertEqual(s['expectedTurnover'],2000) # VAT-inclusive 120 -> net 100.
        self.assertEqual(s['grossMarginPercent'],10)
    def test_foreign_currency_is_not_combined_with_budget_currency(self):
        self.data['commandes'][0]['Devise']='02';self.seed()
        report=self.report()
        self.assertIsNone(report['summary']['committedCost'])
        self.assertIsNone(report['summary']['remainingBudget'])
        self.assertEqual(report['otherCurrencyCommitments'],{'USD':769.5})
        self.assertEqual(report['summary']['knownPurchaseCost'],900)
    def test_missing_currency_labels_do_not_guess_01_means_eur(self):
        self.data['devises']=[];self.seed();report=self.report()
        self.assertIsNone(report['purchaseOrders'][0]['value'])
        self.assertEqual(report['purchaseOrders'][0]['currency'],'01')
    def test_missing_stock_is_unknown_and_known_commitments_stay_visible(self):
        self.data['inventory']=[];self.seed();report=self.report()
        self.assertIsNone(report['rows'][0]['stock'])
        self.assertIsNone(report['rows'][0]['purchaseQuantity'])
        self.assertIsNone(report['summary']['totalPurchaseCost'])
        self.assertEqual(report['summary']['committedCost'],769.5)
    def test_unverified_basis_does_not_show_made_up_money(self):
        b.save_settings(self.c,dict(costBasisVerified=False,tariffVerified=False,poCostsVerified=False))
        report=self.report()
        self.assertIsNone(report['summary']['totalPurchaseCost'])
        self.assertEqual(report['summary']['expectedTurnover'],2000) # Reconciled customer-order prices need no tariff assumption.
        self.assertIsNone(report['summary']['committedCost'])
        self.assertIsNone(report['rows'][0]['unitCost'])
    def test_partial_margin_does_not_block_purchase_budget(self):
        self.data['negoce_lignes']=[];self.seed();report=self.report()
        self.assertTrue(report['summary']['budgetComplete'])
        self.assertIsNone(report['summary']['grossMarginPercent'])
        self.assertEqual(report['summary']['remainingBudget'],330.5)
    def test_closed_and_cancelled_po_do_not_supply_new_stock(self):
        for role in ('Soldée','Annulée'):
            self.data['commandes'][0]['Statut']=role;self.seed();report=self.report()
            self.assertEqual(report['rows'][0]['incoming'],0)
            self.assertEqual(report['rows'][0]['purchaseQuantity'],18)
            self.assertEqual(report['summary']['committedCost'],153.9) # Only delivered two.
    def test_draft_po_never_consumes_budget_or_supply(self):
        self.data['commandes'][0]['Statut']='En saisie';self.seed();report=self.report()
        self.assertEqual(report['rows'][0]['incoming'],0)
        self.assertEqual(report['summary']['committedCost'],0)
    def test_undated_or_overdue_supply_is_not_assumed_available(self):
        for date in (None,'2026-09-01'):
            self.data['commandes'][0]['Date_Livraison']=date;self.seed();report=self.report()
            self.assertIsNone(report['rows'][0]['incoming'])
            self.assertIsNone(report['summary']['remainingBudget'])
            self.assertEqual(report['unallocatedSupplierLines'],1)
    def test_in_transit_stock_is_not_added_again_to_purchase_order_supply(self):
        self.data['inventory'][0]['En_Livraison']=2;self.seed();report=self.report()
        self.assertIsNone(report['rows'][0]['incoming'])
        self.assertIsNone(report['rows'][0]['purchaseQuantity'])
    def test_scenario_changes_proposals_but_not_committed_orders(self):
        base=self.report();optimistic=self.report('optimistic')
        self.assertEqual(optimistic['summary']['committedCost'],base['summary']['committedCost'])
        self.assertEqual(optimistic['rows'][0]['purchaseQuantity'],20)
    def test_other_brands_and_defective_inventory_are_not_pooled(self):
        self.data['inventory'].append(dict(Magasin='DEFECTUEUX',Produit='P',Couleur='B',Taille='M',Disponible=10000,En_Livraison=0))
        self.c.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base,famille) VALUES('Q','B','M',500,'Other')");self.c.commit();self.seed()
        report=self.report();self.assertEqual(len(report['rows']),1);self.assertEqual(report['rows'][0]['stock'],2)
    def test_saving_budget_settings_is_validated_and_persisted(self):
        with self.assertRaises(ValueError):b.save_settings(self.c,dict(costBasisVerified='false'))
        with self.assertRaises(ValueError):b.save_settings(self.c,dict(warehouses=[]))
        b.save_settings(self.c,dict(costField='Prix_Achat_Moyen'))
        self.assertEqual(b.settings(self.c)[0]['costField'],'Prix_Achat_Moyen')
    def test_currency_reference_update_invalidates_cache_without_an_export(self):
        self.data['devises']=[];self.seed();self.assertIsNone(self.report()['summary']['committedCost'])
        self.data['devises']=[dict(Devise='01',currency_code='EUR')];self.seed()
        self.assertEqual(self.report()['summary']['committedCost'],769.5)
    def test_unknown_supplier_status_blocks_receipt_assumptions(self):
        self.data['commandes'][0]['Statut']='Unexpected';self.seed();report=self.report()
        self.assertIsNone(report['rows'][0]['incoming'])
        self.assertFalse(report['summary']['commitmentsComplete'])
    def test_api_currency_lookup_preserves_export_and_never_saves_key(self):
        import api_server
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        source=f.connect(self.path)
        with source:source.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(self.rid,'schema',f.encode(dict(complete=True,tables={'devises':[dict(name=n) for n in ('Devise','Nom','Code','currency_code')]}))))
        source.close()
        api_path=Path(self.tmp.name)/'api.db';disk=sqlite3.connect(api_path);self.c.backup(disk);disk.close()
        remote=Mock();remote.count.return_value=1;remote.query.return_value=[dict(Devise='01',Nom='Euro',Code='EUR',currency_code='EUR')]
        with patch.object(api_server,'get_connection',lambda:sqlite3.connect(api_path)),patch.object(f,'SOURCE_DB',self.path),patch.object(f,'Client',return_value=remote),TestClient(api_server.app) as client:
            result=client.post('/api/budget/currencies',json={'apiKey':'test-secret'})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['imported'],1)
            self.assertEqual(client.get('/api/budget/options').json()['currencies'][0]['iso'],'EUR')
            response=client.get('/api/budget');self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['summary']['remainingBudget'],330.5)
        source=f.connect(self.path)
        try:
            self.assertEqual(len(list(f.rows(source,self.rid,'skus'))),1)
            self.assertNotIn('test-secret',''.join(source.iterdump()))
        finally:source.close()
    def test_api_incomplete_currency_lookup_preserves_previous_reference(self):
        import api_server
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        source=f.connect(self.path)
        with source:source.execute('INSERT OR REPLACE INTO datasets VALUES(?,?,?)',(self.rid,'schema',f.encode(dict(complete=True,tables={'devises':[dict(name=n) for n in ('Devise','Nom','Code','currency_code')]}))))
        source.close()
        api_path=Path(self.tmp.name)/'api.db';disk=sqlite3.connect(api_path);self.c.backup(disk);disk.close()
        remote=Mock();remote.count.return_value=2;remote.query.return_value=[dict(Devise='01',currency_code='EUR')]
        with patch.object(api_server,'get_connection',lambda:sqlite3.connect(api_path)),patch.object(f,'SOURCE_DB',self.path),patch.object(f,'Client',return_value=remote),TestClient(api_server.app) as client:
            result=client.post('/api/budget/currencies',json={'apiKey':'secret'})
            self.assertEqual(result.status_code,400,result.text)
            self.assertNotIn('secret',result.text)
        source=f.connect(self.path)
        try:self.assertEqual(len(list(f.rows(source,self.rid,'devises'))),2)
        finally:source.close()


if __name__=='__main__':unittest.main()
