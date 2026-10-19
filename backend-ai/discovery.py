"""Read-only source discovery before mapping historical and operational facts."""
from functools import lru_cache
from pathlib import Path
import datetime as dt

import pandas as pd
from joolan_client import Client, ExportError
from m1_data_preparation import parse_order_dates


def discover_schema(key, enseigne):
    client = Client('https://go.joolan.com', enseigne, key)
    try:
        rows = client.query("""SELECT TABLE_NAME AS table_name,
            COLUMN_NAME AS column_name, DATA_TYPE AS data_type,
            COLUMN_KEY AS column_key, IS_NULLABLE AS is_nullable,
            ORDINAL_POSITION AS ordinal_position
            FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME, ORDINAL_POSITION""")
        tables = {}
        for source in rows:
            row = {str(k).lower(): v for k, v in source.items()}
            if not row.get('table_name') or not row.get('column_name'):
                raise ValueError('Joolan returned incomplete schema metadata.')
            tables.setdefault(str(row['table_name']), []).append(dict(
                name=str(row['column_name']), dataType=str(row.get('data_type') or ''),
                key=str(row.get('column_key') or ''),
                nullable=str(row.get('is_nullable') or '').upper() == 'YES'))
        if not tables:
            raise ValueError('No schema metadata was accessible. Ask Joolan for a table/column dictionary or metadata query permission.')
        return dict(enseigne=enseigne, discoveredAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                    tables=[dict(name=name, columns=columns) for name, columns in tables.items()],
                    notice='Column names are discovered, but their stock/order meanings and joins still require verification.')
    except ExportError as error:
        raise ValueError(str(error).replace(key, '[hidden]')) from None
    finally:
        client.close()


def historical_profile():
    from config import DATA_FILE_PATH
    path = Path(DATA_FILE_PATH)
    if not path.is_file():
        raise ValueError('The configured historical CSV is missing.')
    stat = path.stat()
    # File changes invalidate the cached scan; return fresh objects to callers.
    import copy
    return copy.deepcopy(_profile(str(path.resolve()), stat.st_size, stat.st_mtime_ns))


@lru_cache(maxsize=2)
def _profile(path, size, modified):
    # Match the legacy loader's supported encodings without loading the entire CSV.
    for encoding in ('utf-8', 'cp1252', 'latin-1'):
        try:
            header = pd.read_csv(path, nrows=0, encoding=encoding)
            if 'Date_Commande' not in header:
                raise ValueError('The historical CSV needs a Date_Commande column.')
            rows = invalid = 0
            first = last = None
            months = {}
            for chunk in pd.read_csv(path, usecols=['Date_Commande'], dtype=str,
                                     encoding=encoding, chunksize=50000):
                dates = parse_order_dates(chunk['Date_Commande'])
                rows += len(chunk)
                invalid += int(dates.isna().sum())
                valid = dates.dropna()
                if not valid.empty:
                    first = valid.min() if first is None else min(first, valid.min())
                    last = valid.max() if last is None else max(last, valid.max())
                    for month, count in valid.dt.strftime('%Y-%m').value_counts().items():
                        months[month] = months.get(month, 0) + int(count)
            if last is None:
                raise ValueError('No valid historical order dates were found.')
            return dict(fileName=Path(path).name, bytes=size, rows=rows, invalidDateRows=invalid,
                        firstOrderDate=first.date().isoformat(), lastOrderDate=last.date().isoformat(),
                        columns=list(header.columns), months=[dict(month=m, rows=months[m]) for m in sorted(months)],
                        notice='Historical demand uses delivered plus remaining units. Joolan uses ordered minus cancellations. Confirm equivalent scope and line identity before combining them.')
        except UnicodeDecodeError:
            continue
    raise ValueError('Could not decode the historical CSV.')
