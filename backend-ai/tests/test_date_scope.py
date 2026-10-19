import re
import sqlite3
import unittest
from joolan_client import Client


class DateClient(Client):
    def __init__(self):
        super().__init__('https://go.joolan.com', 'account', 'test')
        self.db=sqlite3.connect(':memory:')
        self.db.executescript('''
          CREATE TABLE negoce_entetes(Entete INTEGER PRIMARY KEY,Magasin TEXT,Client TEXT,Nature TEXT,Date TEXT);
          CREATE TABLE negoce_lignes(Ligne INTEGER PRIMARY KEY,Entete INTEGER,Magasin TEXT,Client TEXT,Nature TEXT);
          INSERT INTO negoce_entetes VALUES(1,'A','007','ORDER','2026-02-26 23:59:59'),
            (2,'A','007','ORDER','2026-02-27 00:00:00'),(3,'A','007','ORDER','2026-10-05 23:59:59'),
            (4,'A','007','ORDER','2026-10-06 00:00:00'),(5,'B','008','ORDER','2026-03-03');
          INSERT INTO negoce_lignes VALUES(11,1,'A','007','ORDER'),(12,2,'A','007','ORDER'),
            (13,3,'A','007','ORDER'),(14,4,'A','007','ORDER'),(15,5,'A','007','ORDER');
        ''')

    def query(self,sql):
        sql=re.sub(r'CONVERT\(0x([0-9a-f]+) USING utf8mb4\)', lambda m:"'"+bytes.fromhex(m[1]).decode().replace("'","''")+"'",sql)
        if 'information_schema' in sql:
            return [{'COLUMN_NAME':'Ligne' if "'negoce_lignes'" in sql else 'Entete'}]
        sql=re.sub(r'CONVERT\(0x([0-9a-f]+) USING utf8mb4\)', lambda m:"'"+bytes.fromhex(m[1]).decode().replace("'","''")+"'",sql)
        cursor=self.db.execute(sql)
        return [dict(zip([c[0] for c in cursor.description],r)) for r in cursor]


class DateScopeTests(unittest.TestCase):
    def test_brand_and_date_filter_apply_before_downloading_lines(self):
        from fresh_joolan import brand_scope
        client=DateClient()
        try:
            client.db.executescript("CREATE TABLE produits(Produit TEXT,Marque TEXT); INSERT INTO produits VALUES('P','DAYTONA73'),('Q','OTHER'); ALTER TABLE negoce_lignes ADD COLUMN Produit TEXT; UPDATE negoce_lignes SET Produit=CASE WHEN Ligne=12 THEN 'P' ELSE 'Q' END;")
            meta=client.table_snapshot('negoce_lignes',lambda m:None,document_type='ORDER',end_date='2026-10-05',extra_where=brand_scope('negoce_lignes',['DAYTONA73']))
            self.assertEqual(meta['expected'],1)
            self.assertEqual([r['Ligne'] for r in client.table_rows('negoce_lignes',2,lambda m:None,meta)],[12])
        finally:client.db.close()

    def test_date_scope_filters_headers_and_only_compatible_lines_inclusive_of_last_day(self):
        client=DateClient()
        try:
            results={}
            for table in ('negoce_entetes','negoce_lignes'):
                meta=client.table_snapshot(table,lambda m:None,document_type='ORDER',start_date='2026-02-27',end_date='2026-10-05')
                results[table]=list(client.table_rows(table,2,lambda m:None,meta))
            self.assertEqual([r['Entete'] for r in results['negoce_entetes']],[2,3,5])
            self.assertEqual([r['Ligne'] for r in results['negoce_lignes']],[12,13])
        finally: client.db.close()


if __name__=='__main__':unittest.main()
