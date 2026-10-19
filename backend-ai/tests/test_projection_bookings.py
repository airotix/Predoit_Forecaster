import sqlite3
import unittest
from unittest.mock import patch
import api_server
import database
import projection_detail


class ProjectionBookingTests(unittest.TestCase):
 def test_projection_uses_season_bookings_and_conservative_confidence(self):
  conn=sqlite3.connect(':memory:');database._create_schema(conn)
  for size,booked,confidence in [('S',5,'LOW'),('M',7,'MEDIUM')]:
   conn.execute('INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,season_booked,confirmed_orders,probable_additional_base,confidence) VALUES(?,?,?,?,?,?,?,?,?,?)',('P','BLACK',size,10,booked,15,booked,100,10-booked,confidence))
  class BorrowedConnection:
   def execute(self,*args):return conn.execute(*args)
   def close(self):pass
  with patch.object(api_server,'get_connection',return_value=BorrowedConnection()):
   result=api_server.get_projections(season=None,search=None)[0]
  self.assertEqual(result['scenarios']['base']['confirmed'],12)
  self.assertEqual(result['scenarios']['base']['probableReorders'],8)
  self.assertEqual(result['confidence'],'low');self.assertEqual(result['projectionBasis'],'season_bookings')
  detail=projection_detail.detail(conn,'P')
  self.assertEqual(detail['colorVariants'][0]['totalDeProduit'],dict(S=5,M=7));conn.close()


if __name__=='__main__':unittest.main()
