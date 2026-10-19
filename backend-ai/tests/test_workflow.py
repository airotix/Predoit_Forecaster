import asyncio
import sqlite3
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

import database
import workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        import joolan, history_store
        self.tmp=tempfile.TemporaryDirectory()
        self.history_patch=patch.object(history_store,'DEFAULT_PATH',Path(self.tmp.name)/'history.db')
        self.history_patch.start()
        self.conn=sqlite3.connect(':memory:')
        database._create_persistent_tables(self.conn)
        joolan.ensure_joolan_schema(self.conn)

    def tearDown(self):
        self.conn.close();self.history_patch.stop();self.tmp.cleanup()

    def test_no_plan_reports_actionable_blocker(self):
        with patch('discovery.historical_profile',return_value={'lastOrderDate':'2026-02-26'}):
            result=workflow.readiness(self.conn)
        self.assertFalse(result['ready'])
        self.assertIn('Save a planning season',result['blockers'][0])

    def test_direct_approved_export_cannot_bypass_disabled_fresh_approval(self):
        import api_server
        from fastapi import HTTPException
        self.conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('source_policy','fresh_only')")
        class ReadConnection:
            def execute(inner,*args):return self.conn.execute(*args)
            def close(inner):pass
        with patch.object(api_server,'get_connection',return_value=ReadConnection()),self.assertRaises(HTTPException) as result:
            api_server.export_recommendations(format='json',scenario='base',season_id=None,purpose='approved')
        self.assertEqual(result.exception.status_code,409)
        self.assertIn('not enabled',result.exception.detail)

    def test_matching_future_season_can_run_demand_without_financial_inputs(self):
        from planning import save_season
        save_season(self.conn,dict(name='Plan',startDate='2026-10-01',endDate='2027-03-31',currency='EUR',budget=0,targetMargin=0))
        with patch('discovery.historical_profile',return_value={'lastOrderDate':'2026-02-26'}):
            result=workflow.readiness(self.conn)
        self.assertTrue(result['ready'])

    def test_overlapping_plan_is_rejected_before_training(self):
        from planning import save_season
        save_season(self.conn,dict(name='Plan',startDate='2026-02-01',endDate='2026-06-30',currency='EUR',budget=0,targetMargin=0))
        with patch('discovery.historical_profile',return_value={'lastOrderDate':'2026-02-26'}):
            self.assertFalse(workflow.readiness(self.conn)['ready'])

    def test_each_sse_subscriber_receives_the_same_publication(self):
        import api_server
        database.ensure_pipeline_schema(self.conn)
        self.conn.execute("INSERT INTO pipeline_metadata VALUES('last_run','run1','now')")
        self.conn.commit()
        class ReadConnection:
            def execute(inner,*args):return self.conn.execute(*args)
            def close(inner):pass
        async def check():
            a=(await api_server.sse_events()).body_iterator
            b=(await api_server.sse_events()).body_iterator
            await anext(a);await anext(b)
            with patch.object(api_server,'get_connection',return_value=ReadConnection()),patch.object(api_server.asyncio,'sleep',new=AsyncMock()):
                self.assertIn('event: data-refreshed',await anext(a))
                self.assertIn('event: data-refreshed',await anext(b))
                self.conn.execute("UPDATE pipeline_metadata SET value='run2' WHERE key='last_run'")
                self.assertIn('run2',await anext(a))
                self.assertIn('run2',await anext(b))
            await a.aclose();await b.aclose()
        asyncio.run(check())

    def test_validation_preserves_unknowns_and_exposes_disabled_approval(self):
        import api_server
        database.ensure_pipeline_schema(self.conn)
        self.conn.execute("INSERT INTO recommendations(reference,couleur,taille,forecast_base,forecast_conservative,forecast_optimistic,financial_note,confidence) VALUES('P','B','M',10,5,15,'INVENTORY_UNKNOWN;COST_UNKNOWN;PRICE_UNKNOWN','LOW')")
        self.conn.execute("INSERT OR REPLACE INTO joolan_state VALUES('source_policy','fresh_only')")
        class ReadConnection:
            def execute(inner,*args):return self.conn.execute(*args)
            def close(inner):pass
        with patch.object(api_server,'get_connection',return_value=ReadConnection()):
            result=api_server.get_validation('base')
        self.assertEqual(result['skuCount'],1)
        self.assertFalse(result['approvalAvailable'])
        self.assertIn('not enabled',result['approvalNotice'])
        for metrics in result['scenarioMetrics'].values():
            self.assertIsNone(metrics['totalUnits']);self.assertIsNone(metrics['purchaseCost'])
            self.assertIsNone(metrics['grossMargin']);self.assertIsNone(metrics['budgetUsage'])
