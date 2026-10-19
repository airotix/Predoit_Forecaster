import json,time,urllib.request,urllib.error
start=time.perf_counter()
with urllib.request.urlopen('http://127.0.0.1:4000/api/validation?scenario=base',timeout=120) as response:result=json.load(response)
assert result['skuCount']==54158 and not result['approvalAvailable']
assert result['scenarioMetrics']['base']['purchaseCost'] is None
assert result['scenarioMetrics']['base']['totalUnits'] is None
print('Validation live fix:',result,'seconds',round(time.perf_counter()-start,2),flush=True)
for path,expected in [('validation?scenario=invalid',400),('export?scenario=base&purpose=approved',409)]:
 try:urllib.request.urlopen('http://127.0.0.1:4000/api/'+path,timeout=120)
 except urllib.error.HTTPError as e:assert e.code==expected;print(path,e.code,flush=True)
 else:raise AssertionError(path+' was not blocked')
with urllib.request.urlopen('http://127.0.0.1:4000/api/export?scenario=base&purpose=draft',timeout=120) as response:
 raw=response.read();assert raw
 print('Draft export',response.status,len(raw),'bytes',response.headers.get('Content-Type'),flush=True)
