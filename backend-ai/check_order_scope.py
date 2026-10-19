"""Read-only evidence check: compare recent CSV demand with Joolan document types.

Matching dates, customers, variants and quantities is evidence, not a unique
order-line identity. Do not use this diagnostic to deduplicate production data.
"""
import collections
import json
import sqlite3
from pathlib import Path
import pandas as pd
from config import DATA_FILE_PATH
from database import DB_FILE
from m1_data_preparation import _standardize_columns, parse_order_dates


def check():
    header = pd.read_csv(DATA_FILE_PATH, nrows=0)
    mapping = dict(zip(header.columns, _standardize_columns(header.copy()).columns))
    fields = {'Date_Commande', 'Client', 'Reference', 'Couleur', 'Taille', 'CDE_qte', 'Reference_CDE'}
    frame = pd.read_csv(DATA_FILE_PATH, dtype=str, keep_default_na=False,
                        usecols=[k for k,v in mapping.items() if v in fields]).rename(columns=mapping)
    frame['Date_Commande'] = parse_order_dates(frame.Date_Commande).dt.strftime('%Y-%m-%d')
    end = frame.Date_Commande.max()
    start = str(pd.Period(end, freq='M') - 1) + '-01'
    frame = frame[frame.Date_Commande.ge(start)]
    normalize = lambda value: str(value).strip().lstrip('. ')
    keys = {(r.Date_Commande, normalize(r.Client), normalize(r.Reference), normalize(r.Couleur),
             normalize(r.Taille), round(float(r.CDE_qte or 0),4)) for r in frame.itertuples()}
    counts = collections.Counter()
    checked = 0
    conn = sqlite3.connect('file:' + Path(DB_FILE).resolve().as_posix() + '?mode=ro', uri=True)
    try:
        query = """SELECT payload FROM joolan_order_lines WHERE usable=1
            AND json_extract(payload,'$.Order_Date') BETWEEN ? AND ?"""
        for (payload,) in conn.execute(query, (start, end)):
            row = json.loads(payload)
            key = (row['Order_Date'], normalize(row['Customer']), normalize(row['Product']),
                   normalize(row['Colour']), normalize(row['Size']), round(float(row['Ordered_Quantity']),4))
            checked += 1
            if key in keys:
                counts[row['Document_Type']] += 1
    finally:
        conn.close()
    return dict(start=start, end=end, csvRecentRows=len(frame),
                nonemptyCsvOrderReferences=int(frame.Reference_CDE.str.strip().ne('').sum()),
                joolanRecentLinesChecked=checked, matchingLinesByType=dict(counts),
                notice='Matches are not unique order-line identities; confirm document semantics before activation.')


if __name__ == '__main__':
    print(json.dumps(check()))
