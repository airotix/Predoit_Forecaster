"""Unit tests for the SQLite serving-layer helpers (no ML deps needed)."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from preduit_engine import database as db


@pytest.fixture()
def conn():
    path = Path(tempfile.mkdtemp()) / "test.db"
    c = db.get_connection(path)
    db._create_persistent_tables(c)
    yield c
    c.close()


def test_schema_version_and_integrity(conn):
    assert db.get_schema_version(conn) == db.SCHEMA_VERSION
    assert db.check_integrity(conn) is True


def test_user_crud(conn):
    assert db.count_users(conn) == 0
    user = db.create_user(
        conn, email="A@Example.com", name="Alice",
        password_hash="x", role="owner", status="active", now="2026-01-01T00:00:00Z",
    )
    assert user["email"] == "a@example.com"  # normalised lower-case
    assert db.count_users(conn) == 1
    # case-insensitive lookup
    assert db.get_user_by_email(conn, "a@EXAMPLE.com")["name"] == "Alice"
    # role change
    db.update_user_role(conn, "a@example.com", "worker", now="2026-01-02T00:00:00Z")
    assert db.get_user_by_email(conn, "a@example.com")["role"] == "worker"
    # list excludes password hash
    listed = db.list_users(conn)
    assert len(listed) == 1 and "password_hash" not in listed[0]


def test_season_config_band_and_cost(conn):
    db.create_season_config(
        conn, "s1", "SS26", "EUR", budget=500000, target_margin=45,
        budget_band_pct=20, cost_ratio=0.4,
    )
    active = db.get_active_season_config(conn)
    assert active["budget"] == 500000
    assert active["budgetBandPct"] == 20
    assert active["costRatio"] == 0.4
    assert active["isActive"] is True

    db.update_season_config(conn, "s1", cost_ratio=0.55)
    assert db.get_active_season_config(conn)["costRatio"] == 0.55


def test_add_missing_columns_migration(conn):
    conn.execute("CREATE TABLE t_old (id INTEGER PRIMARY KEY, a TEXT)")
    db._add_missing_columns(conn, "t_old", {"a": "TEXT", "b": "REAL NOT NULL DEFAULT 1.5"})
    cols = {row[1] for row in conn.execute("PRAGMA table_info(t_old)").fetchall()}
    assert "b" in cols  # added
    # idempotent — running again is a no-op
    db._add_missing_columns(conn, "t_old", {"b": "REAL NOT NULL DEFAULT 1.5"})
