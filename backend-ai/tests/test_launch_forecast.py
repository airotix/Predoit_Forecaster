import unittest
import pandas as pd
from launch_forecast import extend_launches
from season_projection import reconcile_bookings

class LaunchForecastTests(unittest.TestCase):
 def frames(self):
  predictions=[];raw=[]
  for reference,quantity in [('A',10.),('B',20.),('C',30.)]:
   predictions.append(dict(Reference=reference,Couleur='BLACK',Taille='M',forecast_month=pd.Period('2026-10'),forecast_conservative=quantity/2,forecast_base=quantity,forecast_optimistic=quantity*2,model_type='RECENT_MEAN'))
   raw.append(dict(Reference=reference,Couleur='BLACK',Taille='M',Date_Commande=pd.Timestamp('2026-09-01'),year_month=pd.Period('2026-09'),true_demand=10.,Famille='JACKETS',Catalog_Brand='DAYTONA73',Matiere='LEATHER'))
  raw += [dict(Reference='NEW',Couleur=color,Taille=size,Date_Commande=pd.Timestamp('2026-10-08'),year_month=pd.Period('2026-10'),true_demand=3.,Famille='JACKETS',Catalog_Brand='DAYTONA73',Matiere='LEATHER') for color,size in [('BLACK','M'),('RED','S')]]
  return pd.DataFrame(predictions),pd.DataFrame(raw)
 def test_new_article_uses_explicit_low_evidence_analogue_and_coherent_sizes(self):
  model,raw=self.frames();result,selection,report=extend_launches(model,pd.DataFrame(),raw,pd.Period('2026-09'),'2026-10-14')
  new=result[result.Reference=='NEW'];self.assertEqual(len(new),2)
  self.assertEqual(new.forecast_base.sum(),20)
  self.assertTrue(selection.confidence.eq('LOW').all());self.assertTrue(selection.needs_assortment_review.all())
  self.assertEqual(report['analogueVariants'],2)
 def test_no_analogue_keeps_bookings_as_minimum_and_requires_review(self):
  model,raw=self.frames();raw.loc[raw.Reference=='NEW','Famille']='UNMATCHED'
  result,selection,report=extend_launches(model,pd.DataFrame(),raw,pd.Period('2026-09'),'2026-10-14')
  self.assertEqual(report['bookedOnlyVariants'],2)
  projected=reconcile_bookings(result,raw,'2026-10-14')
  self.assertEqual(projected[projected.Reference=='NEW'].forecast_base.sum(),6)
 def test_future_order_identity_is_not_exposed_early(self):
  model,raw=self.frames();result,selection,report=extend_launches(model,pd.DataFrame(),raw,pd.Period('2026-09'),'2026-10-01')
  self.assertEqual(report['newVariants'],0);self.assertFalse(result.Reference.eq('NEW').any())

if __name__=='__main__':unittest.main()
