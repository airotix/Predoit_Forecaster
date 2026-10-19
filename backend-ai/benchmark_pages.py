"""Read-only local page/API timings. Does not export from Joolan or run models."""
import argparse
import hashlib
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

PAGES=['dashboard','setup','setup/manual','catalogue','scope','settings','customers','products','projection','allocation','recommendations','budget','validation','purchase-orders','login']

def measure(url):
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(url,timeout=180) as response:
            data=response.read();status=response.status
    except urllib.error.HTTPError as error:
        data=error.read();status=error.code
    return dict(seconds=round(time.perf_counter()-start,4),status=status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def run(output, rounds=2):
    with urllib.request.urlopen('http://127.0.0.1:4000/api/seasons/active') as response:season=json.load(response)
    endpoints=['dashboard','pipeline/lineage','joolan/summary','seasons','seasons/active','customers','products','projections',
               'recommendations?scenario=base','budget/draft?scenario=base','budget/options','budget/reviews',
               'catalogue?currency=EUR&grouped=true&limit=20','operating-scope','seasonal-allocation?scenario=base',
               'automatic','joolan/fresh','audit?limit=20',f"purchase-orders?season_id={season['id']}&scenario=base",
               'orders/articles?customer=68&offset=0&limit=20','projections/101126/detail?scenario=base','catalogue/sku/85410']
    results=dict(api={},pages={})
    for route in endpoints:
        results['api'][route]=[]
        for _ in range(rounds):
            result=measure('http://127.0.0.1:4000/api/'+route);results['api'][route].append(result)
            print(route,result['status'],result['seconds'],'seconds',result['bytes'],'bytes',flush=True)
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(results,indent=2),encoding='utf-8')
    for route in PAGES:
        results['pages'][route]=measure('http://127.0.0.1:3000/'+route)
        print('PAGE',route,results['pages'][route]['seconds'],'seconds',flush=True)
        output.write_text(json.dumps(results,indent=2),encoding='utf-8')
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('output/performance/timings.json'));parser.add_argument('--rounds',type=int,default=2)
    args=parser.parse_args();run(args.output,args.rounds)
