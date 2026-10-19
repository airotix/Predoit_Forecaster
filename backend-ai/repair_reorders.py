"""Refresh local reorder KPIs, preserving published forecast quantities and ledger."""
import sqlite3
from pathlib import Path
from reorder_kpis import refresh_saved_rates

if __name__=='__main__':
 c=sqlite3.connect(Path('data/joolan_live.db'),timeout=60)
 def fingerprint():
  return c.execute('SELECT COUNT(*),SUM(forecast_base),SUM(forecast_conservative),SUM(forecast_optimistic),SUM(confirmed_orders) FROM recommendations').fetchone()
 before=fingerprint();ledger_count=c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0]
 rates=refresh_saved_rates(c)
 assert fingerprint()==before
 assert c.execute('SELECT COUNT(*) FROM order_lines').fetchone()[0]==ledger_count
 print('Product/colour groups:',len(rates))
 print('Nonzero season reorder rates:',sum(v['reorderRate'] is not None and v['reorderRate']>0 for v in rates.values()))
 print('Nonzero repeat-order rates:',sum(v['repeatOrderRate'] is not None and v['repeatOrderRate']>0 for v in rates.values()))
 print('Groups with unavailable rates:',sum(v['reorderRate'] is None for v in rates.values()))
 for key in [('101980','BISON'),('105099','KRAFT BEIGE')]:print(key,rates.get(key))
 print('Forecast quantities and ledger preserved:',before,ledger_count)
 c.close()
