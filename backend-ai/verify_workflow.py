"""Run the actual combined dataset in isolation; never replace published results."""
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
import zlib

import pandas as pd
import database
import history_store
import joolan
import main
import planning


def verify():
    base = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='workflow-check-', dir=base/'data') as temporary:
        root = Path(temporary)
        history = root/'history.db'
        original = sqlite3.connect('file:'+history_store.DEFAULT_PATH.as_posix()+'?mode=ro', uri=True)
        replica = sqlite3.connect(history)
        try:
            original.backup(replica)
        finally:
            original.close(); replica.close()
        source = sqlite3.connect(root/'forecast.db')
        database._create_persistent_tables(source)
        history_conn = history_store.connection(history)
        meta = history_store.metadata(history_conn)
        cutoff = meta['csvCutoff']
        imported = meta['rawSnapshotImportedAt']
        end = dt.datetime.fromisoformat(imported).date()
        start = dt.date.fromisoformat(cutoff)+dt.timedelta(days=1)
        def rows():
            for (payload,) in history_conn.execute("SELECT payload FROM joolan_history_raw WHERE document_type='COMMANDE' AND usable=1 AND order_date BETWEEN ? AND ?", (start.isoformat(),end.isoformat())):
                yield json.loads(zlib.decompress(payload))
        print('[CHECK] Preparing isolated COMMANDE candidate; live selection stays unchanged.', flush=True)
        joolan.replace_snapshot(source, rows(), 'query-api', dict(documentType='COMMANDE',startDate=start.isoformat(),endDate=end.isoformat(),enseigne='legend73'))
        history_conn.close()
        joolan.confirm_order_type(source,'COMMANDE')
        period = pd.Period(end, freq='M')
        forecast_start = period if end != period.end_time.date() else period+1
        planning.save_season(source, dict(name='Isolated workflow verification',startDate=forecast_start.start_time.date().isoformat(),
            endDate=(forecast_start+5).end_time.date().isoformat(),currency='EUR',budget=0,targetMargin=0))
        with patch.object(history_store,'DEFAULT_PATH',history):
            joolan.select_forecast_source(source,'combined')
            source.close()
            serving = root/'forecast.db'
            with patch.object(database,'DB_FILE',serving),patch.object(database,'get_connection',lambda:sqlite3.connect(serving)),patch.object(main,'__file__',str(root/'main.py')):
                results=main.run_phase1()
            # Exercise the actual routes and serving schema after publication.
            import api_server
            from fastapi.testclient import TestClient
            statuses={}
            with patch.object(api_server,'get_connection',lambda:sqlite3.connect(serving)),TestClient(api_server.app) as client:
                for url in ('/api/dashboard','/api/products','/api/projections','/api/recommendations','/api/budget','/api/customers','/api/validation','/api/forecast/readiness','/api/pipeline/lineage','/api/export?purpose=draft'):
                    response=client.get(url)
                    statuses[url]=response.status_code
                    if response.status_code!=200:
                        raise RuntimeError(url+': '+response.text[:300])
                statuses['approvedExport']=client.get('/api/export?purpose=approved').status_code
                if statuses['approvedExport'] != 409:
                    raise RuntimeError('Approved export unexpectedly succeeded without required actual inputs.')
            rec=results['recommendations']['recommendations']
            detail=results['recommendations']['monthly_detail']
            report=dict(checkedAt=dt.datetime.now(dt.timezone.utc).isoformat(),candidateType='COMMANDE',
                history=results['lineage']['combinedHistory'],trainingCutoff=results['lineage']['cutoff'],
                forecastStart=results['lineage']['forecastStart'],forecastEnd=results['lineage']['forecastEnd'],
                recommendationRows=len(rec),monthlyRows=len(detail),baseForecastUnits=float(rec.forecast_base.sum()),
                models=rec.model_type.value_counts().to_dict(),apiStatuses=statuses,
                note='Full actual dataset in temporary databases. Candidate type was not activated in live data. No actual inventory/costs were supplied; approved purchase export should remain blocked.')
    output=base/'output'/'workflow-check.json'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    verify()
