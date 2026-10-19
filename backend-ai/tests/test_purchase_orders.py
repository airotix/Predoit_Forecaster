import copy
import csv
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import buying
import database
import purchase_orders as po


def fixture():
    lines = []
    for ref,color,size,supplier,qty,cost in [('A','BLACK','M','Supplier A',4,10),('A','BLACK','L','Supplier A',6,10),('B','BLUE','S','Supplier B',2,None)]:
        row = dict(reference=ref,color=color,size=size,name=ref+' jacket',forecast=qty+1,quantity=qty,
                   orderUnitCost=cost,orderUnitPrice=30,sellThrough=100,quotes=[],quoteId='',
                   costBasis='Saved catalogue',priceBasis='Previous season',blockers=[],orderingRules={})
        row['id'] = buying.identity(row)
        row['purchasePriceDetails'] = dict(supplier=supplier)
        lines.append(row)
    return dict(rows=lines,scenario='base',currency='EUR',revision='budget1',
                draft=dict(version=1,stale=False,seasonId='winter',forecastRun='forecast1',sourceRun='fresh1',scopeRevision='scope1',scenario='base',selected=[lines[0]['id']]),
                summary=dict(budget=150,targetMargin=40,knownCommitments=20,commitmentsComplete=True),
                context=dict(season=dict(name='Winter'),settings=dict(warehouses=['CENTRAL'])),
                articlePlan=dict(articles=[dict(reference='A',status='included',reason='Fits budget'),dict(reference='B',status='waiting',reason='Missing cost')]),
                blockers=['Some proposed orders have unresolved purchase values'])


class PurchaseOrderTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:',check_same_thread=False)
        database._create_schema(self.c); database._create_persistent_tables(self.c); po.ensure(self.c); self.c.commit()
        self.simulation = fixture()
        self.body = dict(version=1,forecastRun='forecast1',revision='budget1',mode='all')

    def tearDown(self):
        self.c.close()

    def create(self, **changes):
        with self.c:
            self.c.execute('BEGIN IMMEDIATE')
            return po.create(self.c,self.simulation,{**self.body,**changes},'source1')

    def view(self, ident, stamp='source1'):
        with patch.object(po,'source_stamp',return_value=stamp):
            return po.view(self.c,ident)

    def test_groups_all_sizes_and_suppliers_and_keeps_missing_values_unknown(self):
        result = self.create()
        self.assertEqual(len(result['created']),2)
        a,b = [self.view(ident) for ident in result['created']]
        self.assertEqual(a['supplier'],'Supplier A'); self.assertEqual(len(a['lines']),2)
        self.assertEqual(a['totals']['purchaseCost'],100)
        self.assertEqual(a['totals']['turnover'],300)
        self.assertEqual(a['totals']['grossMargin'],200)
        self.assertIsNone(b['totals']['purchaseCost']); self.assertIsNone(a['batch']['remaining'])
        self.assertIn('Some purchase prices are missing.',b['checks'])
        self.assertEqual(a['lines'][0]['budgetQuantity'],4)

    def test_repeat_creation_and_later_budget_versions_do_not_duplicate_variants(self):
        first = self.create(); again = self.create()
        self.assertEqual(again['created'],[]); self.assertEqual(again['skippedVariants'],3)
        self.assertEqual(set(again['existing']),set(first['created']))
        self.simulation['draft']['version']=2; self.body['version']=2
        self.simulation['rows'][0]['quantity']=100
        self.assertEqual(self.create()['created'],[])
        self.assertEqual(self.view(first['created'][0])['lines'][0]['quantity'],4)

    def test_selection_modes_and_scenarios_are_isolated(self):
        result = self.create(mode='selected'); doc=self.view(result['created'][0])
        self.assertEqual(len(doc['lines']),1)
        self.assertEqual(len(self.create(mode='fitting')['created']),1)
        self.simulation['scenario']='optimistic'; self.simulation['draft']['scenario']='optimistic'
        self.assertEqual(len(self.create()['created']),2)

    def test_supplier_quote_precedes_catalogue_supplier_and_missing_supplier_stays_unassigned(self):
        row=self.simulation['rows'][0];row['quotes']=[dict(id='quote',supplier='Quoted supplier')];row['quoteId']='quote'
        self.simulation['rows'][1].pop('purchasePriceDetails')
        result=self.create();docs=[self.view(ident) for ident in result['created']]
        self.assertIn('Quoted supplier',{d['supplier'] for d in docs})
        unassigned=next(d for d in docs if not d['supplier'])
        self.assertIn('Assign a supplier.',unassigned['checks'])

    def test_edits_recalculate_finances_and_batch_budget_and_archive_version(self):
        ids=self.create()['created']; doc=self.view(ids[1]); ident=doc['lines'][0]['id']
        with self.c:po.update(self.c,doc['id'],dict(version=1,edits=[dict(id=ident,quantity=8,unitCost=20,unitPrice=40,sellThrough=50)],changeReason='Supplier update'))
        updated=self.view(doc['id'])
        self.assertEqual(updated['version'],2);self.assertEqual(updated['totals']['purchaseCost'],160)
        self.assertEqual(updated['totals']['turnover'],160);self.assertEqual(updated['totals']['grossMargin'],80)
        self.assertEqual(updated['batch']['purchaseCost'],260);self.assertTrue(updated['batch']['overBudget'])
        self.assertEqual(updated['batch']['remaining'],-130)
        self.assertEqual(updated['history'][0]['version'],1)
        self.assertEqual(json.loads(self.c.execute('SELECT payload FROM supplier_po_versions WHERE order_id=?',(doc['id'],)).fetchone()[0])['lines'][0]['quantity'],2)
        with self.assertRaisesRegex(ValueError,'another page'):
            with self.c:po.update(self.c,doc['id'],dict(version=1,edits=[]))

    def test_cancellation_releases_claims_but_preserves_history(self):
        ident=self.create(mode='fitting')['created'][0]
        with self.c:po.update(self.c,ident,dict(version=1,status='cancelled'))
        cancelled=self.view(ident);self.assertEqual(cancelled['status'],'cancelled')
        self.assertEqual(len(self.create(mode='fitting')['created']),1)
        with self.assertRaisesRegex(ValueError,'read-only'):
            with self.c:po.update(self.c,ident,dict(version=2,supplier='other'))

    def test_source_changes_flag_but_never_replace_saved_po(self):
        ident=self.create()['created'][0];doc=self.view(ident,'different')
        self.assertTrue(doc['sourceChanged']);self.assertEqual(doc['lines'][0]['quantity'],4)
        self.c.execute("INSERT OR REPLACE INTO pipeline_metadata(key,value) VALUES('lineage','{}')")
        database._create_schema(self.c)
        self.c.commit()
        self.assertEqual({row['id'] for row in po.listing(self.c,'winter','base')},set(self.create()['existing']))

    def test_invalid_updates_roll_back_and_missing_price_can_be_cleared(self):
        ident=self.create()['created'][0]; line=self.view(ident)['lines'][0]['id']
        for value in (-1,1.5,True,float('inf'),'10'):
            with self.assertRaises(ValueError):
                with self.c:po.update(self.c,ident,dict(version=1,supplier='Do not save',edits=[dict(id=line,quantity=value)]))
            self.assertEqual(self.view(ident)['supplier'],'Supplier A')
        with self.c:po.update(self.c,ident,dict(version=1,edits=[dict(id=line,unitCost=None)]))
        self.assertIsNone(self.view(ident)['totals']['purchaseCost'])

    def test_stale_unsaved_or_conflicting_budget_sources_are_rejected(self):
        for field,value in [('version',0),('stale',True)]:
            simulation=copy.deepcopy(self.simulation); simulation['draft'][field]=value
            with self.assertRaises(ValueError):po.create(self.c,simulation,self.body,'source1')
        with self.assertRaisesRegex(ValueError,'changed'):self.create(revision='old')
        self.create();self.simulation['currency']='USD'
        with self.assertRaisesRegex(ValueError,'another currency'):self.create()

    def test_csv_is_supplier_facing_and_escapes_formula_cells(self):
        ident=self.create()['created'][0]
        with self.c:po.update(self.c,ident,dict(version=1,supplier='=HYPERLINK("bad")',notes='  +formula'))
        with patch.object(po,'source_stamp',return_value='source1'):file=po.export_csv(self.c,ident)
        rows=list(csv.reader(io.StringIO(file['csv'].removeprefix('\ufeff'))))
        self.assertNotIn('Selling / unit',rows[0]);self.assertEqual(rows[1][0],'DRAFT - NOT SENT')
        self.assertTrue(rows[1][3].startswith("'="));self.assertTrue(rows[1][-1].startswith("'"))

    def test_rounding_missing_quantities_and_pack_rules_remain_explicit(self):
        ident=self.create(mode='fitting')['created'][0];line=self.view(ident)['lines'][0]['id']
        with self.c:po.update(self.c,ident,dict(version=1,edits=[dict(id=line,quantity=1,unitCost=1.005,unitPrice=2.005)]))
        doc=self.view(ident);self.assertEqual(doc['lines'][0]['purchaseCost'],1.01)
        self.assertEqual(doc['lines'][0]['turnover'],2.01)
        with self.c:po.update(self.c,ident,dict(version=2,edits=[dict(id=line,quantity=None)]))
        doc=self.view(ident);self.assertIsNone(doc['totals']['purchaseCost']);self.assertIsNone(doc['totals']['units'])
        self.assertIn('Some order quantities are missing.',doc['checks'])

    def test_cross_order_edits_invalid_dates_and_budget_mutation_are_rejected(self):
        ids=self.create()['created'];a,b=[self.view(ident) for ident in ids]
        original=list(self.c.execute('SELECT key,value FROM planning_state'))
        for body in [dict(version=1,edits=[dict(id=b['lines'][0]['id'],quantity=2)]),
                     dict(version=1,orderDate='2026-10-10',deliveryDate='2026-10-09'),
                     dict(version=1,edits=[dict(id=a['lines'][0]['id'],sellThrough=101)])]:
            with self.assertRaises(ValueError):
                with self.c:po.update(self.c,a['id'],body)
        with self.c:po.update(self.c,a['id'],dict(version=1,notes='Local PO note'))
        self.assertEqual(list(self.c.execute('SELECT key,value FROM planning_state')),original)

    def test_partial_or_invalid_source_generation_is_not_allowed(self):
        with self.assertRaisesRegex(ValueError,'changed'):self.create(version=True)
        for row in self.simulation['rows']:row['quantity']=0
        with self.assertRaisesRegex(ValueError,'No positive quantities'):self.create()

    def test_http_create_read_edit_export_and_conflict(self):
        class Connection:
            def __getattr__(inner,name):return getattr(self.c,name)
            def close(inner):pass
            def __enter__(inner):return self.c.__enter__()
            def __exit__(inner,*args):return self.c.__exit__(*args)
        app=FastAPI();po.install(app,Connection);client=TestClient(app)
        with patch('catalogue.sync'),patch('budgeting.build_report',return_value={}),patch('purchase_draft.view',return_value=self.simulation),patch.object(po,'source_stamp',return_value='source1'),patch.object(po,'supplier_options',return_value=['Supplier A']):
            response=client.post('/api/purchase-orders',json=self.body);self.assertEqual(response.status_code,200,response.text)
            ident=response.json()['created'][0]
            self.assertEqual(client.get('/api/purchase-orders',params=dict(season_id='winter')).json()['orders'][0]['status'],'draft')
            doc=client.get('/api/purchase-orders/'+ident).json()
            response=client.put('/api/purchase-orders/'+ident,json=dict(version=doc['version'],notes='Check delivery'))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(client.put('/api/purchase-orders/'+ident,json=dict(version=1)).status_code,409)
            self.assertEqual(client.get('/api/purchase-orders/'+ident+'/export').status_code,200)
