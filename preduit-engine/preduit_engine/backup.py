"""
SQLite backup / restore utilities.

Uses SQLite's online backup API so a consistent snapshot can be taken while the app is
running (no need to stop the server). Backups are timestamped and retained by count.

CLI:
    python -m preduit_engine.backup create          # take a backup
    python -m preduit_engine.backup list            # list backups
    python -m preduit_engine.backup restore <file>  # restore (app should be stopped)
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import DB_PATH as DB_FILE

DEFAULT_BACKUP_DIR = Path(os.environ.get("FORECASTER_BACKUP_DIR", str(DB_FILE.parent / "backups")))
DEFAULT_KEEP = int(os.environ.get("FORECASTER_BACKUP_KEEP", "14"))
_PREFIX = "forecast-"
_SUFFIX = ".db"


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_backup(
    db_path: Optional[Path] = None,
    dest_dir: Optional[Path] = None,
    keep: int = DEFAULT_KEEP,
) -> dict:
    """Take a consistent online backup of the database and prune old ones.

    Returns {path, sizeBytes, createdAt, integrityOk}.
    """
    src = Path(db_path or DB_FILE)
    if not src.exists():
        raise FileNotFoundError(f"Database not found: {src}")

    dest_dir = Path(dest_dir or DEFAULT_BACKUP_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{_PREFIX}{_now_stamp()}{_SUFFIX}"

    source = sqlite3.connect(str(src))
    target = sqlite3.connect(str(dest))
    try:
        with target:
            source.backup(target)  # consistent snapshot via the online backup API
        integrity_ok = target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        target.close()
        source.close()

    prune_backups(dest_dir, keep)
    return {
        "path": str(dest),
        "sizeBytes": dest.stat().st_size,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "integrityOk": integrity_ok,
    }


def list_backups(dest_dir: Optional[Path] = None) -> list:
    """Return backups (newest first) as [{path, sizeBytes, createdAt}]."""
    dest_dir = Path(dest_dir or DEFAULT_BACKUP_DIR)
    if not dest_dir.exists():
        return []
    items = []
    for f in sorted(dest_dir.glob(f"{_PREFIX}*{_SUFFIX}"), reverse=True):
        stat = f.stat()
        items.append({
            "path": str(f),
            "name": f.name,
            "sizeBytes": stat.st_size,
            "createdAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        })
    return items


def prune_backups(dest_dir: Optional[Path] = None, keep: int = DEFAULT_KEEP) -> int:
    """Delete all but the newest `keep` backups. Returns the number removed."""
    dest_dir = Path(dest_dir or DEFAULT_BACKUP_DIR)
    if keep <= 0 or not dest_dir.exists():
        return 0
    backups = sorted(dest_dir.glob(f"{_PREFIX}*{_SUFFIX}"), reverse=True)
    removed = 0
    for old in backups[keep:]:
        old.unlink(missing_ok=True)
        removed += 1
    return removed


def restore_backup(backup_file: Path, db_path: Optional[Path] = None) -> dict:
    """Restore a backup over the live DB. The app should be stopped first.

    The current DB is copied aside to <db>.pre-restore before overwriting.
    """
    src = Path(backup_file)
    if not src.exists():
        raise FileNotFoundError(f"Backup not found: {src}")
    dest = Path(db_path or DB_FILE)

    # Validate the backup before touching the live DB.
    check = sqlite3.connect(str(src))
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup failed integrity check — refusing to restore.")
    finally:
        check.close()

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        aside = dest.with_suffix(dest.suffix + ".pre-restore")
        target = sqlite3.connect(str(aside))
        source = sqlite3.connect(str(dest))
        try:
            with target:
                source.backup(target)
        finally:
            target.close()
            source.close()

    # Copy the backup into place via the backup API (handles WAL cleanly).
    source = sqlite3.connect(str(src))
    target = sqlite3.connect(str(dest))
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()
    return {"restoredFrom": str(src), "dbPath": str(dest)}


def _main(argv: list) -> int:
    cmd = argv[1] if len(argv) > 1 else "create"
    if cmd == "create":
        info = create_backup()
        print(f"Backup created: {info['path']} ({info['sizeBytes']} bytes, "
              f"integrity={'ok' if info['integrityOk'] else 'FAILED'})")
    elif cmd == "list":
        for b in list_backups():
            print(f"{b['createdAt']}  {b['sizeBytes']:>12} B  {b['path']}")
    elif cmd == "restore":
        if len(argv) < 3:
            print("usage: python -m preduit_engine.backup restore <file>")
            return 2
        info = restore_backup(Path(argv[2]))
        print(f"Restored {info['dbPath']} from {info['restoredFrom']}")
    else:
        print(f"unknown command: {cmd}")
        return 2
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv))
