"""Refresh derived customer totals only; preserve orders and forecasts."""
import sqlite3
from customer_coverage import repair_totals,report

if __name__=='__main__':
 c=sqlite3.connect('data/joolan_live.db',timeout=60)
 before=c.execute('SELECT COUNT(*),SUM(forecast_base) FROM recommendations').fetchone()
 print('Customer totals repaired:',repair_totals(c),flush=True)
 assert c.execute('SELECT COUNT(*),SUM(forecast_base) FROM recommendations').fetchone()==before
 result=report(c)
 print('Coverage:',result['coverage'],flush=True)
 print('Top customer:',result['customers'][0],flush=True)
 c.close()
