import json
import sqlite3
import unittest
import pandas as pd
from reorder_kpis import buying_season,compute_reorders,frame_reorders,refresh_saved_rates

def row(order,date,client='A',color='BLACK',qty=1):
 return dict(Reference='P',Couleur=color,Client=client,Reference_CDE=order,Date_Commande=date,true_demand=qty,season_type='CORE',season_year=0)

class ReorderTests(unittest.TestCase):
 def test_period_boundaries_and_winter_crossing_calendar_year(self):
  self.assertEqual(buying_season('2025-10-01'),buying_season('2026-03-31'))
  self.assertNotEqual(buying_season('2026-03-31'),buying_season('2026-04-01'))
  self.assertNotEqual(buying_season('2026-09-30'),buying_season('2026-10-01'))
 def test_multiple_sizes_same_order_do_not_create_repeat(self):
  value=compute_reorders([row('1','2026-01-01')]*5)[('P','BLACK')]
  self.assertEqual(value['reorderRate'],0);self.assertEqual(value['repeatOrderRate'],0)
 def test_repeat_within_season_is_separate(self):
  value=compute_reorders([row('1','2025-12-01'),row('2','2026-02-01')])[('P','BLACK')]
  self.assertEqual(value['reorderRate'],0);self.assertEqual(value['repeatOrderRate'],1)
 def test_catalogue_year_zero_does_not_hide_repeat(self):
  rows=[row('1','2025-11-01'),row('2','2026-05-01'),row('3','2026-05-02',client='B')]
  value=compute_reorders(rows)[('P','BLACK')]
  self.assertEqual(value['reorderRate'],.5);self.assertEqual(value['reorderCustomers'],1)
  self.assertEqual(frame_reorders(pd.DataFrame(rows)),compute_reorders(rows))
 def test_zero_cancelled_and_other_colour_do_not_count(self):
  value=compute_reorders([row('1','2025-11-01'),row('2','2026-05-01',qty=0),row('3','2026-05-01',color='RED')])[('P','BLACK')]
  self.assertEqual(value['reorderRate'],0)
 def test_missing_order_date_or_client_is_unknown(self):
  for missing in (row(None,'2026-05-01'),row('2',None),row('2','bad'),row('2','2026-05-01',client=None)):
   value=compute_reorders([row('1','2025-11-01'),missing])[('P','BLACK')]
   self.assertIsNone(value['reorderRate']);self.assertEqual(value['reorderMissingLines'],1)
 def test_conflicting_dates_on_same_order_do_not_fake_season_repeat(self):
  value=compute_reorders([row('1','2025-11-01'),row('1','2026-05-01')])[('P','BLACK')]
  self.assertIsNone(value['reorderRate']);self.assertEqual(value['reorderCustomers'],0)
 def test_saved_repair_changes_rates_only(self):
  c=sqlite3.connect(':memory:')
  c.executescript('CREATE TABLE recommendations(reference TEXT,couleur TEXT,reorder_rate REAL,forecast_base REAL); CREATE TABLE order_lines(payload TEXT); CREATE TABLE pipeline_metadata(key TEXT PRIMARY KEY,value TEXT,updated_at TEXT);')
  c.execute('INSERT INTO recommendations VALUES(?,?,?,?)',('P','BLACK',0,100))
  c.executemany('INSERT INTO order_lines VALUES(?)',[(json.dumps(r),) for r in [row('1','2025-11-01'),row('2','2026-05-01')]])
  refresh_saved_rates(c)
  self.assertEqual(c.execute('SELECT reorder_rate,forecast_base FROM recommendations').fetchone(),(1,100))
  self.assertEqual(c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0],2)
  c.close()

if __name__=='__main__':unittest.main()
