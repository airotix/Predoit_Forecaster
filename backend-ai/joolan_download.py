"""Durable page spools; only complete pairs are handed to snapshot publication."""
import datetime as dt
import json
import os
from pathlib import Path

from joolan_client import SourceChangedError, spool_value, unspool_value

TABLES = ('negoce_entetes', 'negoce_lignes')


def download_pair(client, scratch, batch, document_type='', start_date='', end_date=''):
    root = Path(scratch)
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / 'checkpoint.json'
    state = None
    try:
        candidate = json.loads(state_path.read_text(encoding='utf-8'), object_hook=unspool_value)
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(candidate['createdAt'])
        snapshots = candidate['tables']
        if candidate.get('version') == 1 and candidate.get('documentType', '') == document_type and candidate.get('startDate', '') == start_date and candidate.get('endDate', '') == end_date and 0 <= age.total_seconds() < 86400 and all(
            snapshots[t]['paging'] == 'keyset' and
            (root / (t + '.jsonl')).exists() and
            (root / (t + '.jsonl')).stat().st_size >= snapshots[t].get('bytes', 0)
            for t in TABLES
        ):
            state = candidate
    except (OSError, ValueError, KeyError, TypeError):
        pass

    if state:
        # A retained cursor is valid only if the bounded population still matches.
        for table, metadata in state['tables'].items():
            if client.count(table, metadata['where']) != metadata['expected']:
                reset_download(root)
                raise SourceChangedError('Joolan bounded rows changed since the paused download.')
    else:
        reset_download(root)
        options = dict(document_type=document_type)
        if start_date or end_date:
            options.update(start_date=start_date, end_date=end_date)
        snapshots = {t: client.table_snapshot(t, lambda message: None, **options)
                     if document_type or start_date or end_date else client.table_snapshot(t, lambda message: None) for t in TABLES}
        state = dict(version=1, documentType=document_type, startDate=start_date, endDate=end_date,
                     createdAt=dt.datetime.now(dt.timezone.utc).isoformat(), tables=snapshots)
        for table, metadata in snapshots.items():
            metadata['bytes'] = 0
            (root / (table + '.jsonl')).touch()

    def save():
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, default=spool_value), encoding='utf-8')
        os.replace(temporary, state_path)

    save()
    spools = {}
    for table, metadata in state['tables'].items():
        path = root / (table + '.jsonl')
        # Discard an uncheckpointed partial page after interruption/crash.
        with path.open('r+b') as stream:
            stream.truncate(metadata.get('bytes', 0))
            stream.seek(metadata.get('bytes', 0))

            def checkpoint():
                stream.flush()
                os.fsync(stream.fileno())
                metadata['bytes'] = stream.tell()
                save()

            for row in client.table_rows(table, batch, lambda message: None, metadata, checkpoint=checkpoint):
                stream.write((json.dumps(row, ensure_ascii=False, default=spool_value) + '\n').encode('utf-8'))
            checkpoint()
        spools[table] = path
    for table, metadata in state['tables'].items():
        if client.count(table, metadata['where']) != metadata['expected']:
            raise SourceChangedError(f'{table}: bounded rows changed before export completed.')
    return spools


def reset_download(scratch):
    # Remove only files owned by this downloader, never the published database.
    root = Path(scratch)
    for name in ('checkpoint.json', 'checkpoint.tmp', *(t + '.jsonl' for t in TABLES)):
        (root / name).unlink(missing_ok=True)
