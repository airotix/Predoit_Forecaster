"""API + financial-helper tests.

Routes the DB to a temp file and skips gracefully if the ML stack (pulled in transitively
by api_server) isn't installed, so unit CI can still run the rest of the suite.
"""

import os
import tempfile

import pytest

# Point the serving DB at a throwaway file BEFORE importing config/app.
os.environ["FORECASTER_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["FORECASTER_OUTPUT_DIR"] = tempfile.mkdtemp()
os.environ.setdefault("FORECASTER_AUTH_ENABLED", "false")

pytest.importorskip("fastapi")
pytest.importorskip("pandas")
pytest.importorskip("pmdarima")  # api_server -> backtest -> m4_sarima -> pmdarima

from fastapi.testclient import TestClient  # noqa: E402
from preduit_app.api_server import (  # noqa: E402
    app,
    _clamp_cost_ratio,
    _scenario_budget,
    _all_scenario_budgets,
    _season_cost_ratio,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── API ───────────────────────────────────────────────────────────────────

def test_health(client):
    assert client.get("/health").status_code == 200


def test_auth_config(client):
    r = client.get("/api/auth/config")
    assert r.status_code == 200
    body = r.json()
    assert "worker" in body["roles"]
    assert body["passwordEnabled"] is True


def test_signup_then_login(client):
    signup = client.post("/api/auth/signup", json={
        "email": "owner@preduit.test", "password": "supersecret1", "name": "Owner",
    })
    assert signup.status_code == 200, signup.text
    data = signup.json()
    assert data["user"]["role"] == "owner"  # first account bootstraps as owner
    assert data["token"]

    ok = client.post("/api/auth/login", json={
        "email": "owner@preduit.test", "password": "supersecret1",
    })
    assert ok.status_code == 200

    bad = client.post("/api/auth/login", json={
        "email": "owner@preduit.test", "password": "wrong",
    })
    assert bad.status_code == 401


def test_duplicate_signup_conflicts(client):
    payload = {"email": "dup@preduit.test", "password": "supersecret1", "name": "Dup"}
    assert client.post("/api/auth/signup", json=payload).status_code == 200
    assert client.post("/api/auth/signup", json=payload).status_code == 409


# ── Financial helpers (Phase 2 logic) ───────────────────────────────────────

def test_clamp_cost_ratio():
    assert _clamp_cost_ratio(0.4) == 0.4
    assert _clamp_cost_ratio(2) == 0.99   # clamped high
    assert _clamp_cost_ratio(-1) == 0.0   # clamped low
    assert _clamp_cost_ratio("nope") == 0.50  # default fallback


def test_scenario_budget_band():
    cfg = {"budget": 1000.0, "budgetBandPct": 10}
    assert _scenario_budget(cfg, "base") == 1000
    assert _scenario_budget(cfg, "conservative") == 900
    assert _scenario_budget(cfg, "optimistic") == 1100
    budgets = _all_scenario_budgets(cfg)
    assert set(budgets) == {"conservative", "base", "optimistic"}


def test_scenario_budget_fallback_when_no_budget():
    # No configured budget → falls back to a multiple of projected cost.
    assert _scenario_budget({}, "base", fallback_cost=100) >= 1


def test_season_cost_ratio_override():
    assert _season_cost_ratio({"costRatio": 0.3}) == 0.3
    assert _season_cost_ratio(None) == 0.50  # default
