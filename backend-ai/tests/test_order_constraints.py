import unittest
from order_constraints import validate_rules,propose,violations,article_violations,applicable

class ConstraintTests(unittest.TestCase):
 def test_default_proposal_rounds_purchase_units_not_forecast(self):
  self.assertEqual(propose(7.2,dict(minUnits=10,packSize=6)),12)
  self.assertIsNone(propose(None,{}));self.assertEqual(propose(0,dict(minUnits=10)),0)
 def test_manual_edits_are_retained_but_invalid_packs_and_limits_are_flagged(self):
  self.assertTrue(violations(7,dict(packSize=6)))
  self.assertTrue(violations(5,dict(minUnits=10)));self.assertTrue(violations(20,dict(maxUnits=10)))
  self.assertTrue(violations(1,dict(blocked=True)))
 def test_missing_pack_is_not_treated_as_verified(self):
  self.assertNotIn('packSize',applicable({},'P','variant',6))
  self.assertEqual(applicable(dict(packRulesVerified=True),'P','variant',6)['packSize'],6)
 def test_article_minimum_applies_to_selected_total(self):
  rows=[dict(reference='P',quantity=6,orderingRules=dict(minArticleUnits=10))]
  self.assertIn('P',article_violations(rows))
  self.assertFalse(article_violations(rows+rows))
 def test_invalid_business_rules_fail(self):
  for rule in [dict(packSize=0),dict(leadTimeDays=-1),dict(minUnits=10,maxUnits=2),dict(blocked='yes')]:
   with self.subTest(rule=rule),self.assertRaises(ValueError):validate_rules({'P':rule})

if __name__=='__main__':unittest.main()
