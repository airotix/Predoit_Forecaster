"""Read Joolan's stock measures from the forecast's own immutable export.

These are warehouse balances, not date-filtered receipt/delivery forecasts.
Never infer zero for a missing record or rebuild Theorique from a forecast.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import sqlite3

import paths

FIELDS = dict(stock='En_Stock', toReceive='Reliquat_Fournisseur',
              clients='En_Commande', allocated='Attribue', theoretical='Theorique',
              available='Disponible')


def number(value):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def complete_total(values):
    values = list(values)
    return round(sum(values), 4) if values and all(v is not None for v in values) else None


def read(conn, reference, forecast_keys, source_path=None):
    row = conn.execute("SELECT value FROM pipeline_metadata WHERE key='lineage'").fetchone()
    lineage = json.loads(row[0]) if row else {}
    rid = lineage.get('freshRun')
    path = Path(source_path or paths.SOURCE_DB)
    if not rid or not path.is_file():
        return None
    source = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        run = source.execute('SELECT status,config FROM runs WHERE id=?', (rid,)).fetchone()
        if not run or run[0] != 'validated':
            return None
        config = json.loads(run[1])
        meta_row = source.execute("SELECT metadata FROM datasets WHERE run_id=? AND dataset='inventory'", (rid,)).fetchone()
        metadata = json.loads(meta_row[0]) if meta_row else {}
        if not metadata.get('complete'):
            return None
        scope = lineage.get('operatingScope')
        from operating_scope import CONFIRMED
        warehouses = sorted(w for w, role in scope['warehouseRoles'].items() if role == 'primary') if scope else sorted(
            w for w in config.get('warehouses', []) if CONFIRMED.get(w.upper()) == 'primary')
        if not warehouses:
            return None
        by_warehouse = defaultdict(dict)
        duplicate = set()
        # Bounded to one exported dataset and article. No live API call or writes.
        for (payload,) in source.execute("SELECT payload FROM records WHERE run_id=? AND dataset='inventory' AND CAST(json_extract(payload,'$.Produit') AS TEXT)=?", (rid, reference)):
            record = json.loads(payload)
            store = str(record.get('Magasin') or '').strip()
            store = next((w for w in warehouses if w.casefold() == store.casefold()), None)
            if store is None:
                continue
            key = (str(record.get('Couleur') or 'Unknown'), str(record.get('Taille') or 'Unknown'))
            if store in by_warehouse[key]:
                duplicate.add(key)
            by_warehouse[key][store] = record
    finally:
        source.close()

    keys = set(forecast_keys) | set(by_warehouse)
    # Keep catalogue-only sizes visible as unknown, without inventing a forecast.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='catalogue_skus'").fetchone():
        keys.update((str(color or 'Unknown'), str(size or 'Unknown')) for color, size in conn.execute(
            'SELECT color,size FROM catalogue_skus WHERE reference=? AND current=1 AND source_run=?', (reference, rid)))
    colors = defaultdict(lambda: {name: {} for name in FIELDS})
    records_complete = 0
    for color, size in sorted(keys):
        records = by_warehouse.get((color, size), {})
        covered = (color, size) not in duplicate and set(records) == set(warehouses)
        measures = {name: complete_total(number(r.get(field)) for r in records.values()) if covered else None
                    for name, field in FIELDS.items()}
        records_complete += int(all(value is not None for value in measures.values()))
        for name, value in measures.items():
            colors[color][name][size] = value
    variants = [dict(color=color, **measures) for color, measures in colors.items()]
    values = {name: [value for color in variants for value in color[name].values()] for name in FIELDS}
    return dict(sourceRun=rid, source=metadata.get('source', 'Joolan inventory'),
                snapshotAt=metadata.get('fetchedAt') or metadata.get('completedAt'),
                warehouses=warehouses, colors=variants, totalVariants=len(keys),
                completeVariants=records_complete, missingVariants=len(keys)-records_complete,
                summary={name: complete_total(items) for name, items in values.items()},
                recordedSummary={name: round(sum(v for v in items if v is not None), 4) if any(v is not None for v in items) else None for name, items in values.items()})
