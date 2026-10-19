from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from derived_cache import load,store,location


class DerivedCacheTests(unittest.TestCase):
    def test_roundtrip_preserves_decimal_unknowns_and_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'source.db';data=dict(cost=Decimal('1.005'),price=None,zero=0)
            store(db,'budget-source','source1',data)
            self.assertEqual(load(db,'budget-source','source1'),data)
            self.assertIsInstance(load(db,'budget-source','source1')['cost'],Decimal)
            self.assertIsNone(load(db,'budget-source','source2'))
            location(db,'budget-source','source1').write_bytes(b'bad gzip')
            self.assertIsNone(load(db,'budget-source','source1'))

    def test_pruning_is_limited_to_generated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'source.db';db.write_text('preserve raw data')
            root=location(db,'reorders','one').parent;root.mkdir()
            unrelated=root/'notes.txt';unrelated.write_text('preserve user notes')
            for value in range(6):store(db,'reorders',str(value),dict(value=value))
            self.assertEqual(len(list(root.glob('reorders-*.json.gz'))),3)
            self.assertEqual(db.read_text(),'preserve raw data');self.assertTrue(unrelated.exists())

    def test_reorders_survive_restart_but_ledger_changes_invalidate_them(self):
        import json,sqlite3
        from unittest.mock import patch
        import product_kpis
        from planning import ensure_schema,order_ledger_revision
        with tempfile.TemporaryDirectory() as folder:
            c=sqlite3.connect(Path(folder)/'serving.db');ensure_schema(c)
            rows=[dict(Reference='A'+str(n),Couleur='BLACK',Client='buyer',Reference_CDE='1',Date_Commande='2026-05-01',true_demand=1) for n in range(100)]
            with c:c.executemany('INSERT INTO order_lines VALUES(?,?)',[(str(n),json.dumps(row)) for n,row in enumerate(rows)])
            metadata=dict(lineage='run1');result=product_kpis.ledger_reorders(c,metadata)
            product_kpis._repeat_cache.clear()
            with patch.object(product_kpis,'compute_reorders',side_effect=AssertionError('Should read the derived cache')):
                self.assertEqual(product_kpis.ledger_reorders(c,metadata),result)
            revision=order_ledger_revision(c);rows[0]['true_demand']=0
            with c:c.execute('UPDATE order_lines SET payload=? WHERE line_key=?',(json.dumps(rows[0]),'0'))
            self.assertGreater(order_ledger_revision(c),revision)
            changed=product_kpis.ledger_reorders(c,metadata);self.assertNotIn(('A0','BLACK'),changed)
            with c:c.execute("DELETE FROM order_lines WHERE line_key='1'")
            self.assertGreater(order_ledger_revision(c),revision+1)
            c.close();product_kpis._repeat_cache.clear()
