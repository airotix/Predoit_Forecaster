"""Operator routes: database health and backups (admin role when authentication is active)."""
from fastapi import HTTPException

import access_settings as settings
import db_backup


def install(app, connection):
    @app.get('/api/admin/db/health')
    def db_health():
        report = {}
        for label, path in db_backup.databases().items():
            exists = path.exists()
            report[label] = {'path': str(path), 'exists': exists,
                             'sizeBytes': path.stat().st_size if exists else None,
                             'integrityOk': db_backup.check_integrity(path) if exists else None}
        return {'databases': report, 'backupDir': str(db_backup.backup_dir()), 'keep': settings.BACKUP_KEEP}

    @app.get('/api/admin/db/backups')
    def db_backups():
        return {'backups': db_backup.list_backups(db_backup.backup_dir())}

    @app.post('/api/admin/db/backup')
    def db_backup_now():
        """Back up every database that exists; failures are reported per database."""
        destination = db_backup.backup_dir()
        created, skipped = [], []
        for label, path in db_backup.databases().items():
            if not path.exists():
                skipped.append({'database': label, 'reason': 'Database file does not exist yet.'})
                continue
            try:
                created.append(db_backup.create_backup(label, path, destination, settings.BACKUP_KEEP))
            except Exception as error:
                raise HTTPException(400, f'Backup of {label} failed: {type(error).__name__}') from None
        return {'backups': created, 'skipped': skipped, 'backupDir': str(destination)}
