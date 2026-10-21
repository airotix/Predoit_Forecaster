"""Phase 0 golden master: forecast numbers and API payloads must not change in the migration.

Runs the real pipeline (m1 -> forecasting -> m7 -> database publish) on a deterministic
synthetic order history and snapshots what the API serves. Regenerate only when a change
is intentional:
    UPDATE_PHASE0_SNAPSHOTS=1 python -B -m unittest discover -s tests -p "test_phase0_golden.py"
and explain the numeric difference in the PR.
"""
import json
import os
import platform
import tempfile
import unittest

import numpy as np
import pandas as pd

import phase0_support as support

UPDATE = os.environ.get('UPDATE_PHASE0_SNAPSHOTS') == '1'
VOLATILE = {'lastRun', 'lastPipelineRun'}
API_FIXTURE = 'phase0_golden_api.json'
CATBOOST_FIXTURE = 'phase0_golden_catboost.json'


def jsonable(value):
    return json.loads(json.dumps(value, default=str))


def monthly_history():
    """Monthly demand per variant, derived from the same synthetic orders."""
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, 'orders.csv')
        support.synthetic_orders(path)
        raw = pd.read_csv(path, dtype=str)
    raw['true_demand'] = raw.CDE_qte.astype(float)
    raw['year_month'] = pd.PeriodIndex(raw.Date_Commande.str[:7], freq='M')
    return raw.groupby(['Reference', 'Couleur', 'Taille', 'year_month'], as_index=False).true_demand.sum()


class GoldenApiTests(unittest.TestCase):
    def test_pipeline_and_api_payloads_match_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            actual = support.scrub(jsonable(support.run_golden_pipeline(directory)), VOLATILE)
        path = support.FIXTURES / API_FIXTURE
        if UPDATE:
            path.write_text(json.dumps(actual, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        expected = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(sorted(expected), sorted(actual))
        for endpoint in expected:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(expected[endpoint], actual[endpoint],
                                 f'{endpoint} changed. Intentional? Regenerate and justify in the PR.')

    def test_every_golden_endpoint_is_served(self):
        expected = json.loads((support.FIXTURES / API_FIXTURE).read_text(encoding='utf-8'))
        self.assertEqual([], [e for e, (status, _) in expected.items() if status != 200])


class GoldenCatBoostTests(unittest.TestCase):
    """CatBoost output can differ across platforms/versions, so it is pinned per environment."""

    def environment(self):
        import catboost
        return dict(platform=platform.system(), catboost=catboost.__version__, numpy=np.__version__)

    def test_catboost_forecast_matches_snapshot_on_the_recorded_platform(self):
        import forecasting
        os.environ.pop('FORECASTER_DISABLE_CATBOOST', None)
        forecast, selection = forecasting.forecast(monthly_history(), horizon=6, iterations=60)
        rows = jsonable(forecast.sort_values(forecasting.KEYS + ['forecast_month']).round(3).to_dict('records'))
        models = sorted(selection.selected_model.value_counts().to_dict().items())
        path = support.FIXTURES / CATBOOST_FIXTURE
        if UPDATE:
            path.write_text(json.dumps(dict(environment=self.environment(), rows=rows, models=models), indent=1) + '\n', encoding='utf-8')
        expected = json.loads(path.read_text(encoding='utf-8'))
        if expected['environment'] != self.environment():
            self.skipTest(f"snapshot recorded on {expected['environment']}; regenerate for {self.environment()} to enforce")
        self.assertEqual(len(expected['rows']), len(rows))
        for want, got in zip(expected['rows'], rows):
            self.assertEqual({k: want[k] for k in ('Reference', 'Couleur', 'Taille', 'forecast_month', 'model_type')},
                             {k: got[k] for k in ('Reference', 'Couleur', 'Taille', 'forecast_month', 'model_type')})
            for column in ('forecast_base', 'forecast_conservative', 'forecast_optimistic'):
                self.assertAlmostEqual(want[column], got[column], delta=0.01, msg=f'{want["Reference"]} {column}')
        self.assertEqual(expected['models'], [list(m) for m in models])


if __name__ == '__main__':
    unittest.main()
