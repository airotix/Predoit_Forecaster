"""Unit tests for the SQLite backup / restore utilities."""

import sqlite3
import tempfile
from pathlib import Path

from preduit_engine import backup


def _make_db(path: Path, value: str):
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE t (v TEXT)")
    c.execute("INSERT INTO t VALUES (?)", (value,))
    c.commit()
    c.close()


def test_create_list_prune(tmp_path):
    dbf = tmp_path / "forecast.db"
    dest = tmp_path / "backups"
    _make_db(dbf, "hello")

    info = backup.create_backup(db_path=dbf, dest_dir=dest, keep=2)
    assert info["integrityOk"] is True
    assert Path(info["path"]).exists()
    assert len(backup.list_backups(dest)) == 1

    # Creating several with keep=2 prunes to the newest 2.
    for _ in range(3):
        backup.create_backup(db_path=dbf, dest_dir=dest, keep=2)
    assert len(backup.list_backups(dest)) == 2


def test_restore_roundtrip(tmp_path):
    dbf = tmp_path / "forecast.db"
    dest = tmp_path / "backups"
    _make_db(dbf, "original")
    info = backup.create_backup(db_path=dbf, dest_dir=dest, keep=5)

    target = tmp_path / "restored.db"
    backup.restore_backup(Path(info["path"]), db_path=target)

    c = sqlite3.connect(str(target))
    got = c.execute("SELECT v FROM t").fetchone()[0]
    c.close()
    assert got == "original"
