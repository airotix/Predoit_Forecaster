"""Regenerable JSON caches beside a database; never a source of new data."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile

KINDS={'budget-source','reorders'}
MAX_DECODED=256*1024*1024


def location(database,kind,signature):
    if kind not in KINDS:raise ValueError('Unknown derived cache kind.')
    folder=Path(database).resolve().parent/'.read-cache'
    digest=hashlib.sha256(signature.encode()).hexdigest()
    return folder/(kind+'-'+digest+'.json.gz')


def load(database,kind,signature):
    path=location(database,kind,signature)
    try:
        from joolan_client import unspool_value
        with gzip.open(path,'rb') as stream:raw=stream.read(MAX_DECODED+1)
        if len(raw)>MAX_DECODED:return None
        result=json.loads(raw,object_hook=unspool_value)
        return result['data'] if result.get('signature')==signature else None
    except (OSError,EOFError,ValueError,KeyError,TypeError,AttributeError):return None


def store(database,kind,signature,data):
    path=location(database,kind,signature);temporary=None
    try:
        from joolan_client import spool_value
        path.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(dict(signature=signature,data=data),ensure_ascii=False,default=spool_value,allow_nan=False).encode()
        if len(raw)>MAX_DECODED:return
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix=kind+'-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(gzip.compress(raw,compresslevel=3,mtime=0))
        os.replace(temporary,path);temporary=None
        # Only our generated cache files are pruned; raw databases are untouched.
        siblings=sorted(path.parent.glob(kind+'-'+'[0-9a-f]'*64+'.json.gz'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
        for old in siblings[3:]:
            if old.resolve().parent==path.parent.resolve():old.unlink(missing_ok=True)
    except (OSError,ValueError,TypeError):pass # a cache failure must not block the application
    finally:
        if temporary is not None:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
