import asyncio
import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from read_cache import ReadCache, CachedReadRoute, Entry


class ReadCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'serving.db';self.source=Path(self.temp.name)/'raw.db'
        for path in (self.path,self.source):
            c=sqlite3.connect(path);c.execute('PRAGMA journal_mode=WAL');c.execute('CREATE TABLE data(value INTEGER)');c.execute('INSERT INTO data VALUES(1)');c.commit();c.close()
        self.cache=ReadCache([self.path,self.source]);self.app=FastAPI();self.app.router.route_class=CachedReadRoute;self.app.state.read_cache=self.cache;self.calls=0

    def tearDown(self):
        self.cache.close();self.temp.cleanup()

    def write(self,path,value):
        c=sqlite3.connect(path)
        with c:c.execute('UPDATE data SET value=?',(value,))
        c.close()

    def endpoint(self):
        @self.app.get('/api/dashboard')
        def dashboard(request:Request):
            self.calls+=1;c=sqlite3.connect(self.path)
            try:return dict(value=c.execute('SELECT value FROM data').fetchone()[0],large='x'*2000,who=request.headers.get('authorization'))
            finally:c.close()

    def test_serialized_hit_invalidates_on_serving_and_raw_source_commits(self):
        self.endpoint()
        with TestClient(self.app) as client:
            first=client.get('/api/dashboard');second=client.get('/api/dashboard')
            self.assertEqual(first.json(),second.json());self.assertEqual(second.headers['x-read-cache'],'hit');self.assertEqual(self.calls,1)
            self.write(self.path,2)
            self.assertEqual(client.get('/api/dashboard').json()['value'],2);self.assertEqual(self.calls,2)
            self.write(self.source,3)
            client.get('/api/dashboard');self.assertEqual(self.calls,3)

    def test_identity_parameters_gzip_and_authentication_remain_separate(self):
        self.endpoint()
        @self.app.middleware('http')
        async def auth(request,call_next):
            if request.headers.get('authorization')!='Bearer permitted':return JSONResponse({'detail':'Denied'},401)
            return await call_next(request)
        with TestClient(self.app) as client:
            permitted={'Authorization':'Bearer permitted','Accept-Encoding':'gzip'}
            response=client.get('/api/dashboard',headers=permitted)
            self.assertEqual(response.headers.get('content-encoding'),'gzip');self.assertEqual(response.json()['value'],1)
            self.assertEqual(client.get('/api/dashboard',headers={'Accept-Encoding':'gzip'}).status_code,401)
            plain=client.get('/api/dashboard',headers={**permitted,'Accept-Encoding':'gzip;q=0'})
            self.assertNotIn('content-encoding',plain.headers);self.assertEqual(plain.json(),response.json())
            client.get('/api/dashboard?scenario=optimistic',headers=permitted);self.assertEqual(self.calls,2)

    def test_live_jobs_errors_and_writes_are_never_cached(self):
        @self.app.get('/api/automatic')
        def jobs():self.calls+=1;return dict(calls=self.calls)
        @self.app.get('/api/dashboard')
        def failure():self.calls+=1;return JSONResponse({'detail':'not ready'},409)
        @self.app.post('/api/dashboard')
        def mutation():self.calls+=1;return dict(calls=self.calls)
        with TestClient(self.app) as client:
            for _ in range(2):client.get('/api/automatic');client.get('/api/dashboard');client.post('/api/dashboard')
            self.assertEqual(self.calls,6);self.assertFalse(self.cache.entries)

    def test_in_flight_reads_coalesce_and_writes_during_calculation_are_not_cached(self):
        @self.app.get('/api/dashboard')
        async def report():
            self.calls+=1;await asyncio.sleep(.03);return dict(value=1)
        async def check():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://testserver') as client:
                responses=await asyncio.gather(*[client.get('/api/dashboard') for _ in range(5)])
                self.assertEqual(self.calls,1);self.assertEqual(len({r.content for r in responses}),1)
        asyncio.run(check())
        self.cache.entries.clear();self.cache.bytes=0
        @self.app.get('/api/products')
        def changed():self.write(self.path,2);return dict(value=2)
        with TestClient(self.app) as client:client.get('/api/products')
        self.assertFalse(self.cache.entries)

    def test_cache_memory_is_bounded_and_expired_entries_are_not_served(self):
        cache=ReadCache([],max_bytes=15,max_age=.01,max_entries=2)
        try:
            for key in range(3):cache.put(key,Entry(b'12345',{},b'12',time.monotonic()+1))
            self.assertLessEqual(cache.bytes,15);self.assertLessEqual(len(cache.entries),2)
            cache.put('expired',Entry(b'abc',{},None,time.monotonic()-1));self.assertIsNone(cache.lookup('expired'))
        finally:cache.close()
