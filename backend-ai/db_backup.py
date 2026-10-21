"""Consistent online backups of the SQLite databases that hold the application's data.

Uses SQLite's backup API, so the server can keep running. Three databases matter:
the serving database (forecasts, plans, users), the Joolan source export and the history store.
Backups are named <database>-<UTC stamp>.db and the newest N per database are kept.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_KEEP = 14


def databases():
    """{label: path} for the databases that exist or are expected."""
    import database
    import fresh_joolan
    import history_store
    return {'serving': Path(database.DB_FILE), 'source': Path(fresh_joolan.SOURCE_DB),
            'history': Path(history_store.DEFAULT_PATH)}


def backup_dir(serving=None):
    override = (os.environ.get('FORECASTER_BACKUP_DIR') or '').strip()
    return Path(override).expanduser() if override else Path(serving or databases()['serving']).parent / 'backups'


def _stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def check_integrity(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        conn.close()


def create_backup(label, source, destination, keep=DEFAULT_KEEP):
    source, destination = Path(source), Path(destination)
    if not source.exists():
        raise FileNotFoundError(f'Database not found: {source}')
    destination.mkdir(parents=True, exist_ok=True)
    target_path = destination / f'{label}-{_stamp()}.db'
    reader, writer = sqlite3.connect(str(source)), sqlite3.connect(str(target_path))
    try:
        with writer:
            reader.backup(writer)
        ok = writer.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        writer.close()
        reader.close()
    prune(label, destination, keep)
    return {'database': label, 'path': str(target_path), 'sizeBytes': target_path.stat().st_size,
            'createdAt': datetime.now(timezone.utc).isoformat(), 'integrityOk': ok}


def list_backups(destination):
    destination = Path(destination)
    if not destination.exists():
        return []
    items = []
    for file in sorted(destination.glob('*-*.db'), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = file.stat()
        items.append({'database': file.name.split('-')[0], 'name': file.name, 'path': str(file),
                      'sizeBytes': stat.st_size, 'createdAt': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
    return items


def prune(label, destination, keep=DEFAULT_KEEP):
    if keep <= 0:
        return 0
    files = sorted(Path(destination).glob(f'{label}-*.db'), key=lambda f: f.name, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)
    return max(0, len(files) - keep)
