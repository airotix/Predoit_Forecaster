import json
import sqlite3
import unittest

import article_activity as activity
import catalogue
import database


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        database._create_schema(self.c)
        database._create_persistent_tables(self.c)
        self.c.execute("INSERT OR REPLACE INTO pipeline_metadata(key,value,updated_at) VALUES('lineage',?,'test')",
                       (json.dumps({'cutoff':'2026-09','freshReport':{'exportedThrough':'2026-10-19'}}),))

    def tearDown(self):
        self.c.close()

    def order(self, key, reference, date, quantity=1, status='closed'):
        self.c.execute('INSERT INTO order_lines VALUES(?,?)', (key,json.dumps(dict(Reference=reference,
            Date_Commande=date,true_demand=quantity,Order_Status=status))))

    def test_exact_two_year_boundary_and_leap_day(self):
        self.assertTrue(activity.classify('2024-10-19','2026-10-19')['dormant'])
        self.assertFalse(activity.classify('2024-10-20','2026-10-19')['dormant'])
        self.assertTrue(activity.classify('2022-02-28','2024-02-29')['dormant'])
        self.assertEqual(activity.classify(None,'2026-10-19')['status'],'no_history')
        self.assertFalse(activity.classify(None,None)['dormant'])

    def test_latest_positive_non_cancelled_date_across_variants_and_future_cutoff(self):
        self.order('old','A','2020-01-01')
        self.order('new','A','2026-10-10')
        self.order('dormant','B','2020-01-01')
        self.order('cancelled','B','2026-10-15',status='cancelled')
        self.order('zero','B','2026-10-16',quantity=0)
        self.order('negative','B','2026-10-16',quantity=-1)
        self.order('future','B','2026-11-01')
        self.order('invalid','B','2026-02-30')
        rows=[dict(reference='B',forecast=10),dict(reference='A',forecast=2),dict(reference='NEW',forecast=None)]
        before=self.c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0]
        result=activity.attach(self.c,rows)
        self.assertEqual([r['reference'] for r in result],['A','NEW','B'])
        self.assertEqual(result[-1]['activity']['lastCustomerOrder'],'2020-01-01')
        self.assertEqual(result[-1]['forecast'],10)
        self.assertEqual(result[1]['activity']['status'],'no_history')
        self.assertEqual(before,self.c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0])
        during_publication={}
        for payload, in self.c.execute('SELECT payload FROM order_lines'):
            activity.observe(during_publication,json.loads(payload),'2026-10-19')
        self.assertEqual(during_publication,activity.activity(self.c)[0])

    def test_month_cutoff_fallback_never_uses_machine_clock(self):
        self.c.execute("UPDATE pipeline_metadata SET value=? WHERE key='lineage'",(json.dumps({'cutoff':'2024-02'}),))
        self.assertEqual(activity.context(self.c)[1],'2024-02-29')

    def test_catalogue_global_order_before_pagination_preserves_all_sizes(self):
        catalogue.ensure(self.c)
        for sku,ref,size in [('1','A_OLD','S'),('2','A_OLD','M'),('3','Z_RECENT','S'),('4','Z_RECENT','M')]:
            self.c.execute('INSERT INTO catalogue_skus VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                           (sku,ref,'BLACK',size,'Jacket','DAYTONA73','Jackets','Supplier',1,'run','now','{}'))
        self.order('a','A_OLD','2010-01-01')
        self.order('z','Z_RECENT','2026-10-01')
        first=catalogue.listing(self.c,'EUR',grouped=True,limit=1)
        last=catalogue.listing(self.c,'EUR',grouped=True,limit=1,offset=1)
        self.assertEqual({r['reference'] for r in first['rows']},{'Z_RECENT'})
        self.assertEqual(len(first['rows']),2)
        self.assertTrue(all(r['activity']['dormant'] for r in last['rows']))
