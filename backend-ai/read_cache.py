"""Bounded, database-versioned caching of serialized read responses.

Runs inside routing, after authentication middleware. Writes and live job/event
endpoints never enter this cache. SQLite data_version observes commits from any
connection/process; serving and raw-source changes both invalidate cached reads.
"""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import datetime as dt
import gzip
import hashlib
from pathlib import Path
import sqlite3
import threading
import time

from fastapi.routing import APIRoute
from starlette.responses import Response

READ_PATHS={
    '/api/dashboard','/api/pipeline/lineage','/api/joolan/summary','/api/seasons','/api/seasons/active',
    '/api/customers','/api/customer-detail','/api/products','/api/products/size-history','/api/projections','/api/recommendations',
    '/api/budget','/api/budget/draft','/api/budget/options','/api/budget/reviews','/api/budget/reconciliation','/api/catalogue',
    '/api/operating-scope','/api/seasonal-allocation','/api/filter-options','/api/orders/articles',
    '/api/orders','/api/articles','/api/purchase-orders',
}


class DatabaseProbe:
    def __init__(self,path):
        self.path=Path(path).resolve();self.conn=None;self.identity=None;self.lock=threading.Lock()

    def version(self):
        with self.lock:
            stat=self.path.stat();identity=(stat.st_dev,stat.st_ino,stat.st_ctime_ns)
            # Creation time may change during ordinary Windows writes, so only
            # inode/device identify replacement when an inode is available.
            identity=identity[:2] if stat.st_ino else identity
            if self.conn is None or self.identity!=identity:
                if self.conn is not None:self.conn.close()
                self.conn=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,check_same_thread=False,timeout=0.2)
                self.identity=identity
            return (identity,self.conn.execute('PRAGMA data_version').fetchone()[0])

    def close(self):
        with self.lock:
            if self.conn is not None:self.conn.close();self.conn=None


@dataclass
class Entry:
    body:bytes
    headers:dict
    compressed:bytes|None
    expires:float

    @property
    def size(self):return len(self.body)+len(self.compressed or b'')


class ReadCache:
    def __init__(self,paths,max_bytes=64*1024*1024,max_age=600,max_entries=64):
        self.probes=[DatabaseProbe(path) for path in paths]
        self.max_bytes=max_bytes;self.max_age=max_age;self.max_entries=max_entries
        self.entries=OrderedDict();self.bytes=0;self.pending={}

    def fingerprint(self):
        try:return (dt.datetime.now(dt.timezone.utc).date().isoformat(),*(probe.version() for probe in self.probes))
        except (OSError,sqlite3.Error):return None

    def lookup(self,key):
        entry=self.entries.get(key)
        if entry and entry.expires>time.monotonic():self.entries.move_to_end(key);return entry
        if entry:self.bytes-=self.entries.pop(key).size
        return None

    def put(self,key,entry):
        if entry.size>self.max_bytes:return
        if key in self.entries:self.bytes-=self.entries.pop(key).size
        self.entries[key]=entry;self.bytes+=entry.size
        while self.bytes>self.max_bytes or len(self.entries)>self.max_entries:
            _,old=self.entries.popitem(last=False);self.bytes-=old.size

    def close(self):
        for probe in self.probes:probe.close()
        self.entries.clear();self.bytes=0


def accepts_gzip(header):
    for part in header.lower().split(','):
        name,*parameters=part.strip().split(';')
        if name!='gzip':continue
        try:quality=next((float(p.strip()[2:]) for p in parameters if p.strip().startswith('q=')),1.)
        except ValueError:quality=0
        if quality>0:return True
    return False


def respond(entry,request,state):
    use_gzip=entry.compressed is not None and accepts_gzip(request.headers.get('accept-encoding',''))
    headers={k:v for k,v in entry.headers.items() if k.lower() not in ('content-length','content-encoding')}
    headers.update({'Cache-Control':'no-store','X-Read-Cache':state,'Vary':'Accept-Encoding'})
    if use_gzip:headers['Content-Encoding']='gzip'
    return Response(entry.compressed if use_gzip else entry.body,status_code=200,headers=headers)


class CachedReadRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()

        async def handler(request):
            cache=getattr(request.app.state,'read_cache',None)
            path=request.url.path
            if request.method!='GET' or path not in READ_PATHS or cache is None:
                return await original(request)
            fingerprint=cache.fingerprint()
            if fingerprint is None:return await original(request)
            # Isolate identities without storing credentials in diagnostic keys.
            identity=hashlib.sha256((request.headers.get('authorization','')+'\0'+request.headers.get('cookie','')).encode()).digest()
            key=(path,request.url.query,identity,fingerprint)
            entry=cache.lookup(key)
            if entry is not None:return respond(entry,request,'hit')

            async def build():
                response=await original(request)
                if response.status_code!=200 or 'application/json' not in response.headers.get('content-type','') or not isinstance(getattr(response,'body',None),bytes):
                    return response
                body=response.body
                compressed=await asyncio.to_thread(gzip.compress,body,compresslevel=3,mtime=0) if len(body)>=1000 else None
                result=Entry(body,dict(response.headers),compressed,time.monotonic()+cache.max_age)
                if fingerprint==cache.fingerprint():cache.put(key,result)
                return result

            task=cache.pending.get(key);shared=task is not None
            if task is None:
                task=asyncio.create_task(build());cache.pending[key]=task
                def complete(done):
                    if cache.pending.get(key) is done:cache.pending.pop(key,None)
                    if not done.cancelled():done.exception() # consume an abandoned request's failure
                task.add_done_callback(complete)
            result=await asyncio.shield(task)
            return respond(result,request,'shared' if shared else 'miss') if isinstance(result,Entry) else result

        return handler
