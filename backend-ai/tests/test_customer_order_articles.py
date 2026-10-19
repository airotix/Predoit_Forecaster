import json,sqlite3,unittest
from customer_order_articles import articles

class OrderArticleTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.execute('CREATE TABLE order_lines(payload TEXT)')
 def tearDown(self):self.c.close()
 def add(self,reference,size,qty,color='BLACK',order='1',customer='A'):
  r=dict(Client=customer,Reference_CDE=order,Date_Commande='2026-10-01',Reference=reference,Designation='Jacket',Couleur=color,Taille=size,CDE_qte=qty,LIV_qte=qty)
  self.c.execute('INSERT INTO order_lines VALUES(?)',(json.dumps(r),))
 def test_article_contains_all_sizes_and_colors(self):
  self.add('P','S',2);self.add('P','M',3);self.add('P','S',4,color='RED');self.add('P','S',1)
  result=articles(self.c,'A');self.assertEqual(result['total'],1)
  article=result['articles'][0];self.assertEqual(article['ordered'],10);self.assertEqual(article['delivered'],10)
  self.assertEqual(article['lineCount'],4);self.assertEqual(len(article['variants']),3)
  self.assertEqual(next(v['ordered'] for v in article['variants'] if v['color']=='BLACK' and v['size']=='S'),3)
 def test_pagination_never_splits_large_article(self):
  for size in range(60):self.add('P',str(size),1)
  self.add('Q','S',5)
  first=articles(self.c,'A',0,1);second=articles(self.c,'A',1,1)
  self.assertEqual(first['total'],2);self.assertEqual(first['articles'][0]['ordered'],60)
  self.assertEqual(len(first['articles'][0]['variants']),60);self.assertEqual(second['articles'][0]['reference'],'Q')
 def test_orders_and_customers_stay_separate(self):
  self.add('P','S',2);self.add('P','S',3,order='2');self.add('P','S',100,customer='B')
  result=articles(self.c,'A');self.assertEqual(result['total'],2)
  self.assertEqual(sum(r['ordered'] for r in result['articles']),5)
 def test_empty_customer(self):
  result=articles(self.c,'missing');self.assertEqual(result['articles'],[]);self.assertEqual(result['total'],0)
 def forecasts(self,rows):
  self.c.execute('CREATE TABLE pipeline_metadata(key TEXT,value TEXT)')
  lineage=dict(runId='published',seasonId='season',forecastStart='2026-10',forecastEnd='2027-03',plan=dict(name='Winter',startDate='2026-10-01',endDate='2027-03-31'))
  self.c.execute('INSERT INTO pipeline_metadata VALUES(?,?)',('lineage',json.dumps(lineage)))
  self.c.execute('CREATE TABLE recommendations(reference TEXT,couleur TEXT,taille TEXT,forecast_base REAL)')
  self.c.executemany('INSERT INTO recommendations VALUES(?,?,?,?)',rows)
 def test_forecast_matches_whole_article_and_retains_actuals(self):
  self.add('P','S',2);self.add('P','S',5,order='2')
  self.forecasts([('P','BLACK','S',10),('P','RED','M',4),('Q','BLACK','S',999)])
  result=articles(self.c,'A');self.assertTrue(result['forecastContext']['available'])
  first,second=result['articles'];self.assertEqual(first['forecast'],14);self.assertEqual(second['forecast'],14)
  self.assertEqual(first['ordered'],2);self.assertEqual(second['ordered'],5)
  added=next(v for v in first['variants'] if v['color']=='RED')
  self.assertEqual(added['forecast'],4);self.assertIsNone(added['ordered']);self.assertEqual(added['lineCount'],0)
 def test_zero_forecast_is_distinct_from_missing_forecast(self):
  self.add('P','S',2);self.add('Q','S',3)
  self.forecasts([('P','BLACK','S',0)])
  rows={r['reference']:r for r in articles(self.c,'A')['articles']}
  self.assertEqual(rows['P']['forecast'],0);self.assertIsNone(rows['Q']['forecast'])
 def test_unpredicted_order_size_makes_total_unavailable(self):
  self.add('P','S',2);self.add('P','M',3)
  self.forecasts([('P','BLACK','S',10)])
  self.assertIsNone(articles(self.c,'A')['articles'][0]['forecast'])
 def test_selected_season_mismatch_hides_stale_predictions(self):
  self.add('P','S',2);self.forecasts([('P','BLACK','S',10)])
  self.c.execute('CREATE TABLE planning_state(key TEXT,value TEXT)');self.c.execute('CREATE TABLE planning_seasons(id TEXT,payload TEXT)')
  self.c.execute("INSERT INTO planning_state VALUES('active_season','other')")
  self.c.execute('INSERT INTO planning_seasons VALUES(?,?)',('other',json.dumps(dict(id='other',startDate='2027-04-01',endDate='2027-09-30'))))
  result=articles(self.c,'A');self.assertFalse(result['forecastContext']['available']);self.assertIsNone(result['articles'][0]['forecast'])

if __name__=='__main__':unittest.main()
