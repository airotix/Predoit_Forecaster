import unittest
from copy import deepcopy
from purchase_prices import match

class SupplierPriceTests(unittest.TestCase):
 def source(self):
  header=dict(Date='2026-10-01',Statut='Validée',Devise='01',Fournisseur='SUPPLIER',Numero_Commande='PO1',**{'Remise'+str(i):0 for i in range(1,6)})
  return dict(products={'P':dict(Fournisseur='SUPPLIER')},headers={'1':header},poPrices={('1','P','BLACK','M'):dict(Prix_Achat_Devise=100,Remise_Achat=20)},currencies=[dict(Devise='01',Code='EUR'),dict(Devise='02',Code='USD')])
 def test_exact_variant_net_price_keeps_order_and_currency_provenance(self):
  matches,_=match(self.source(),dict(poCostsVerified=True),'2026-10-14','EUR')
  price=matches[('P','BLACK','M')]
  self.assertEqual(price['unitCost'],80);self.assertEqual(price['currency'],'EUR');self.assertEqual(price['orderId'],'1');self.assertEqual(price['supplier'],'SUPPLIER')
 def test_foreign_currency_and_unverified_cost_basis_are_not_guessed(self):
  source=self.source();source['headers']['1']['Devise']='02'
  self.assertFalse(match(source,dict(poCostsVerified=True),'2026-10-14','EUR')[0])
  self.assertFalse(match(self.source(),dict(poCostsVerified=False),'2026-10-14','EUR')[0])
 def test_conflicting_latest_prices_require_review(self):
  source=self.source();source['headers']['2']=deepcopy(source['headers']['1'])
  source['poPrices'][('2','P','BLACK','M')]=dict(Prix_Achat_Devise=200,Remise_Achat=20)
  matches,excluded=match(source,dict(poCostsVerified=True),'2026-10-14','EUR')
  self.assertFalse(matches);self.assertEqual(excluded['conflicting_latest_prices'],1)

if __name__=='__main__':unittest.main()
