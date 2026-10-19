import copy
import json
import sqlite3
import unittest
import buying

class BuyingTests(unittest.TestCase):
 def setUp(self):
  self.report=dict(rows=[dict(reference='P',color='BLACK',size='M',name='Jacket',category='Outerwear',forecast=20,stock=2,incoming=8,purchaseQuantity=10.2,unitCost=30,unitPrice=100)],
   purchaseOrders=[dict(reference='P',color='BLACK',size='M',unitCost=40,value=200,ordered=5,delivered=0,currency='EUR',supplier='Supplier',orderNumber='PO1',orderId='1',receiptDate='2026-11-01')],
   summary=dict(currency='EUR',targetMargin=40,knownCommittedCost=200,seasonBudget=1000,budgetConfigured=True,commitmentsComplete=True),
   source=dict(revision='r1',runId='fresh'),scenario='base',season=dict(id='winter'),settings=dict(brands=['DAYTONA73']))
  self.key=buying.identity(self.report['rows'][0])
 def test_rounding_supplier_cost_and_sell_through(self):
  result=buying.simulate(self.report,[dict(id=self.key,quoteId='0',sellThrough=50,reason='Conservative sell-through')])
  r=result['rows'][0]
  self.assertEqual(r['quantity'],11);self.assertEqual(r['orderCost'],440)
  self.assertEqual(r['orderTurnover'],550);self.assertEqual(r['orderGrossMargin'],330)
  self.assertEqual(r['orderMarginRate'],60);self.assertEqual(result['summary']['balance'],360)
  self.assertEqual(r['blockers'],[])
 def test_default_sku_price_is_estimate_not_supplier_approval(self):
  self.assertIn('Select a Joolan supplier price',buying.simulate(self.report)['rows'][0]['blockers'])
 def test_launch_review_requires_explicit_acknowledgement_and_reason(self):
  self.report['rows'][0]['requiresAssortmentReview']=True
  self.assertIn('Launch/assortment estimate requires planner review',buying.simulate(self.report)['rows'][0]['blockers'])
  result=buying.simulate(self.report,[dict(id=self.key,assortmentReviewed=True,reason='Planner checked the launch analogue')])
  self.assertNotIn('Launch/assortment estimate requires planner review',result['rows'][0]['blockers'])
  self.assertTrue(result['rows'][0]['assortmentReviewed'])
 def test_forecast_quantity_and_whole_article_grouping(self):
  extra=copy.deepcopy(self.report['rows'][0]);extra.update(size='L',forecast=2.3)
  self.report['rows'].append(extra)
  result=buying.simulate(self.report,quantity_basis='forecast')
  self.assertEqual([r['quantity'] for r in result['rows']],[20,3])
  self.assertEqual(len(result['articlePlan']['articles']),1)
  self.assertEqual(result['articlePlan']['articles'][0]['purchaseCost'],690)
  self.assertEqual(result['articlePlan']['articles'][0]['status'],'included')
 def test_budget_exclusion_distinct_from_missing_prices_and_margin(self):
  for ref,price,cost in [('Q',100,30),('R',None,30),('S',35,30)]:
   row=copy.deepcopy(self.report['rows'][0]);row.update(reference=ref,unitPrice=price,unitCost=cost)
   self.report['rows'].append(row)
  result=buying.simulate(self.report,quantity_basis='forecast')
  decisions={a['reference']:a for a in result['articlePlan']['articles']}
  self.assertEqual(decisions['P']['status'],'included')
  self.assertEqual(decisions['Q']['status'],'budget')
  self.assertEqual(decisions['Q']['shortfall'],400)
  self.assertEqual(decisions['R']['status'],'waiting')
  self.assertEqual(decisions['S']['status'],'margin')
 def test_entered_selling_price_enables_provisional_allocation(self):
  self.report['rows'][0]['unitPrice']=None;self.report['summary']['commitmentsComplete']=False
  result=buying.simulate(self.report,[dict(id=self.key,unitPrice=100,reason='Draft')],'forecast')
  self.assertEqual(result['articlePlan']['articles'][0]['status'],'included')
  self.assertTrue(result['articlePlan']['provisional'])
  self.assertIn('Price assumptions are simulation only',result['rows'][0]['blockers'])
 def test_cleared_quantity_or_price_remains_unknown(self):
  for field in ('quantity','unitCost','unitPrice'):
   result=buying.simulate(self.report,[dict(id=self.key,**{field:None})],'forecast')
   self.assertEqual(result['articlePlan']['articles'][0]['status'],'waiting')
   self.assertIsNone(result['articlePlan']['articles'][0]['purchaseCost'])
 def test_unknown_price_does_not_become_zero(self):
  self.report['rows'][0]['unitPrice']=None
  r=buying.simulate(self.report)['rows'][0]
  self.assertIsNone(r['orderTurnover']);self.assertIsNone(r['orderMarginRate'])
 def test_manual_prices_are_only_assumptions(self):
  r=buying.simulate(self.report,[dict(id=self.key,quoteId='0',unitCost=1,reason='What if')])['rows'][0]
  self.assertIn('Price assumptions are simulation only',r['blockers'])
 def test_low_margin_and_over_budget_block(self):
  self.report['rows'][0]['unitPrice']=50
  result=buying.simulate(self.report,[dict(id=self.key,quoteId='0',quantity=30,reason='Test')])
  self.assertIn('Below margin target',result['rows'][0]['blockers']);self.assertIn('Buying budget exceeded',result['blockers'])
 def test_incomplete_commitments_block(self):
  self.report['summary']['commitmentsComplete']=False
  self.assertIn('Existing supplier commitments are incomplete',buying.simulate(self.report)['blockers'])
 def test_invalid_edits_rejected(self):
  for edit in (dict(quantity=-1),dict(quantity=1.5),dict(sellThrough=101),dict(unitCost=float('nan')),dict(quantity=True),dict(quoteId='missing')):
   with self.subTest(edit=edit),self.assertRaises(ValueError):buying.simulate(self.report,[dict(id=self.key,**edit)])
 def test_validation_snapshot_and_stale_revision(self):
  c=sqlite3.connect(':memory:');c.execute('CREATE TABLE planning_state(key TEXT PRIMARY KEY,value TEXT)')
  edits=[dict(id=self.key,quoteId='0',reason='Confirmed supplier price')]
  result=buying.simulate(self.report,edits)
  record=buying.validate(c,self.report,edits,[self.key],result['revision'])
  stored=json.loads(c.execute('SELECT value FROM planning_state').fetchone()[0])
  self.assertEqual(stored['id'],record['id']);self.assertEqual(stored['orders'][0]['orderCost'],440)
  altered=copy.deepcopy(self.report);altered['summary']['seasonBudget']=300;altered['season']['budget']=300
  with self.assertRaisesRegex(ValueError,'changed'):buying.validate(c,altered,edits,[self.key],result['revision'])
  with self.assertRaises(ValueError):buying.validate(c,self.report,[],[self.key],result['revision'])
  self.assertEqual(c.execute('SELECT COUNT(*) FROM planning_state').fetchone()[0],1)
  c.close()
 def test_unresolved_stock_cannot_be_approved_by_quantity_override(self):
  self.report['rows'][0]['stock']=None
  r=buying.simulate(self.report,[dict(id=self.key,quoteId='0',quantity=10,reason='Test')])['rows'][0]
  self.assertIn('Stock or incoming supply unresolved',r['blockers'])
 def test_foreign_currency_quote_is_not_mixed_into_budget(self):
  self.report['purchaseOrders'][0]['currency']='USD'
  self.assertEqual(buying.simulate(self.report)['rows'][0]['quotes'],[])

 def test_covered_subset_excludes_unknowns_without_claiming_full_budget(self):
  extra=copy.deepcopy(self.report['rows'][0]);extra.update(reference='Q',stock=None,purchaseQuantity=None)
  self.report['rows'].append(extra);self.report['summary']['commitmentsComplete']=False
  self.report['unallocatedSupplierLines']=3
  result=buying.simulate(self.report)
  c=result['covered']
  self.assertEqual(c['recommendationCount'],1);self.assertEqual(c['excludedRecommendations'],1)
  self.assertEqual(c['purchaseCost'],330);self.assertEqual(c['turnover'],1100)
  self.assertEqual(c['commitments'],200);self.assertEqual(c['balanceAfterCovered'],470)
  self.assertFalse(c['fullPlanComplete']);self.assertEqual(c['excludedSupplierLines'],3)
  self.assertIn('Existing supplier commitments are incomplete',result['blockers'])
 def test_no_covered_recommendations_does_not_create_margin(self):
  self.report['rows'][0]['unitPrice']=None
  c=buying.simulate(self.report)['covered']
  self.assertEqual(c['recommendationCount'],0);self.assertIsNone(c['marginRate'])
  self.assertEqual(c['supplierLines'],1);self.assertFalse(c['fullPlanComplete'])
 def test_price_assumptions_and_foreign_suppliers_excluded_from_covered_data(self):
  self.report['purchaseOrders'][0]['currency']='USD'
  c=buying.simulate(self.report,[dict(id=self.key,unitPrice=120,reason='test')])['covered']
  self.assertEqual(c['recommendationCount'],0);self.assertEqual(c['supplierLines'],0);self.assertEqual(c['commitments'],0)

if __name__=='__main__':unittest.main()
