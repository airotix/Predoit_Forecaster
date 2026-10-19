"use client";
import {useCallback,useEffect,useState} from "react";
import Link from "next/link";
import {useAuth} from '@/components/auth/AuthProvider';
import AppShell from "@/components/layout/AppShell";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Card,CardContent,CardHeader,CardTitle} from "@/components/ui/card";
import {apiClient} from "@/lib/api/client";
import {useSeasonStore} from "@/store/seasonStore";
import {getForecastJobStatus,triggerForecastRefresh,type ForecastJobStatus} from "@/lib/api/ingest";

type Report={readyForForecast:boolean;readyForPurchasing:boolean;blockers:string[];warnings:string[];catalogueVariants:number;stockRows:number;orderLines:number;missingStockVariants:number};
type Status={activeRun:string|null;discovery?:Schema|null;run:null|{id:string;status:string;phase:string;error:string|null;report:Report|null;datasets:{name:string;expected?:number;exported?:number;count?:number;complete:boolean}[]}};
type Schema={enseigne:string;warehouses:string[];warehouseDetails?:Record<string,unknown>[];warehouseBalances?:{Magasin:string;variants:number;physical:number;available:number}[];brands?:{Marque:string;products:number}[];tables:Record<string,{name:string;type:string;key:string}[]>;notice:string};
type Ready={ready:boolean;blockers:string[];warnings:string[];trainingCutoff:string|null};
const today=()=>new Date().toLocaleDateString("en-CA");
export default function FreshSetup(){
 const {role}=useAuth();const isAdmin=role==='admin'||role==='owner';
 const [key,setKey]=useState("");const [enseigne,setEnseigne]=useState("legend73");
 const [through,setThrough]=useState(today);const [warehouses,setWarehouses]=useState<string[]>([]);
 const [brands,setBrands]=useState<string[]>(['DAYTONA73','D73','IRON AND RESIN','IRON&RESIN']);
 const [schema,setSchema]=useState<Schema|null>(null);const [status,setStatus]=useState<Status|null>(null);
 const [ready,setReady]=useState<Ready|null>(null);const [job,setJob]=useState<ForecastJobStatus|null>(null);
 const [error,setError]=useState("");const [message,setMessage]=useState("");const [busy,setBusy]=useState(false);
 const [name,setName]=useState("October 2026 - March 2027");const [start,setStart]=useState("2026-10-01");const [end,setEnd]=useState("2027-03-31");
 const createSeason=useSeasonStore(s=>s.createSeason);
 useEffect(()=>{let live=true;apiClient.get<{scope:{brands:string[];warehouseRoles:Record<string,string>}}>('/operating-scope').then(v=>{if(live){setBrands(v.scope.brands);setWarehouses(Object.entries(v.scope.warehouseRoles).filter(([,role])=>role!=='unclassified').map(([w])=>w));}}).catch(()=>{});return()=>{live=false;};},[]);
 const load=useCallback(async()=>{const [s,r,j]=await Promise.all([apiClient.get<Status>('/joolan/fresh'),apiClient.get<Ready>('/forecast/readiness'),getForecastJobStatus()]);setStatus(s);setReady(r);setJob(j);if(s.discovery?.enseigne===enseigne)setSchema(s.discovery);},[enseigne]);
 useEffect(()=>{let live=true;const refresh=()=>load().catch(e=>{if(live)setError(String(e.message||e));});void refresh();const timer=setInterval(()=>void refresh(),5000);return()=>{live=false;clearInterval(timer);};},[load]);
 async function action(fn:()=>Promise<void>){if(!isAdmin){setError('An administrator is required to manage exports and forecasts.');return;}setBusy(true);setError("");setMessage("");try{await fn();await load();}catch(e){setError(e instanceof Error?e.message:"Operation failed");}finally{setBusy(false);}}
 const exporting=!!status?.run&&['queued','running'].includes(status.run.status);
 const run=status?.run;
 const sourceDownloadsComplete=!!run&&run.datasets.some(d=>d.name==='negoce_lignes')&&run.datasets.filter(d=>d.name!=='schema'&&d.name!=='inventory').every(d=>d.complete);
 return <AppShell><div className="mx-auto max-w-5xl space-y-6 pb-12">
 <div><h1 className="text-2xl font-semibold">Fresh Joolan setup</h1><p className="mt-2 text-slate-600">New API exports supply the catalogue, customer orders and warehouse stock. Previous CSVs and imports are excluded.</p><p className="mt-2 text-sm"><Link className="text-blue-600 underline" href="/scope">Review business brands and warehouse roles</Link> before running the next forecast. Export warehouse selection controls downloaded inventory; Business Scope controls which stock supplies standard orders.</p></div>
 {error&&<p role="alert" className="rounded border border-red-300 p-4 text-red-700">{error}</p>}
 {message&&<p role="status" className="rounded border p-4">{message}</p>}
 <Card><CardHeader><CardTitle>1. Connect and inspect available fields</CardTitle></CardHeader><CardContent className="space-y-4">
 <div className="grid gap-4 md:grid-cols-2"><label>Enseigne<Input value={enseigne} onChange={e=>{setEnseigne(e.target.value);setSchema(null);setWarehouses([]);}} disabled={!isAdmin||busy||exporting}/></label><label>Joolan API key<Input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} disabled={!isAdmin||busy||exporting}/></label></div>
 <p className="text-sm text-slate-600">Required permissions: api_query and api_stock. The key is sent to the local backend and stays in memory. It is cleared after starting an export.</p>
 <Button disabled={!isAdmin||!key.trim()||busy||exporting} onClick={()=>void action(async()=>{const s=await apiClient.post<Schema>('/joolan/fresh/preflight',{apiKey:key},{enseigne});setSchema(s);setMessage(s.notice);})}>Check connection and discover fields</Button>
 {schema&&<details><summary className="cursor-pointer">Live table and column dictionary ({Object.keys(schema.tables).length} tables)</summary><div className="mt-3 max-h-72 overflow-auto text-sm">{Object.entries(schema.tables).map(([table,columns])=><div className="mb-3" key={table}><strong>{table}</strong><p>{columns.map(c=>`${c.name} (${c.type}${c.key?`, ${c.key}`:''})`).join(' · ')}</p></div>)}</div></details>}
 </CardContent></Card>
 <Card><CardHeader><CardTitle>2. Start a new full export</CardTitle></CardHeader><CardContent className="space-y-4">
 <p>Customer-order type: <strong>COMMANDE</strong>. All available order history through the selected date is downloaded anew. Each export gets its own database version.</p>
 <label className="block max-w-sm">History end date (all earlier years included)<Input type="date" value={through} max={today()} onChange={e=>setThrough(e.target.value)} disabled={!isAdmin||busy||exporting}/></label><Button variant="outline" disabled={!isAdmin||busy||exporting} onClick={()=>setThrough(today())}>Use today as end date</Button>
 <fieldset><legend className="mb-2 font-medium">Product brands for this forecast</legend><div className="flex flex-wrap gap-3">{(schema?.brands||[{Marque:'DAYTONA73',products:0}]).filter(b=>b.Marque).map(b=><label key={b.Marque} className="flex gap-2"><input type="checkbox" checked={brands.includes(b.Marque)} disabled={!isAdmin||busy||exporting} onChange={e=>setBrands(v=>e.target.checked?[...v,b.Marque]:v.filter(x=>x!==b.Marque))}/>{b.Marque}{b.products?` (${b.products})`:''}</label>)}</div><p className="text-sm text-slate-600">Other brands are excluded. Select D73 only if it is part of the same business scope.</p></fieldset>
 {schema?.warehouseDetails&&<div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>Warehouse</th><th>Name / company</th><th>Depot flag</th><th>Closed flag</th><th>Available units (all brands)</th></tr></thead><tbody>{schema.warehouseDetails.map(d=><tr key={String(d.Magasin)} className="border-t"><td className="py-2">{String(d.Magasin)}</td><td>{String(d.Nom||'')} / {String(d.Societe||'')}</td><td>{String(d.Depot??'unknown')}</td><td>{String(d.magasin_ferme??'unknown')}</td><td>{schema.warehouseBalances?.find(b=>b.Magasin===d.Magasin)?.available?.toLocaleString()??'unknown'}</td></tr>)}</tbody></table></div>}
 <fieldset><legend className="mb-2 font-medium">Warehouses available to supply these customers</legend>{schema?.warehouses.length?<div className="flex flex-wrap gap-4">{schema.warehouses.map(w=><label key={w} className="flex gap-2"><input type="checkbox" checked={warehouses.includes(w)} disabled={!isAdmin||busy||exporting} onChange={e=>setWarehouses(v=>e.target.checked?[...v,w]:v.filter(x=>x!==w))}/>{w}</label>)}</div>:<p className="text-sm text-slate-600">Check the connection to retrieve warehouse codes, then select the supplying warehouses.</p>}</fieldset>
 <p className="text-sm">New export: <strong>{brands.join(', ')||'select a brand'}</strong>, all history through <strong>{through}</strong>, stock from <strong>{warehouses.join(', ')||'select warehouses'}</strong>.</p>
 <Button disabled={!isAdmin||!key.trim()||!warehouses.length||!brands.length||busy||exporting} onClick={()=>void action(async()=>{await apiClient.post('/joolan/fresh',{apiKey:key,enseigne,documentType:'COMMANDE',throughDate:through,warehouses,brands});setKey("");setMessage('Fresh export started. Saved pages belong only to this new export.');})}>Start fresh Joolan export</Button>
 {run&&<div className="space-y-2 rounded border p-4"><p><strong>{run.status.replaceAll('_',' ')}</strong> — {run.phase}</p><p className="text-xs text-slate-500">Export {run.id}</p>{run.error&&<p className="text-red-700">{run.error}</p>}
 {run.datasets.filter(d=>d.name!=='schema').map(d=><p key={d.name} className="text-sm">{d.name}: {d.complete?'complete':'downloading'} · {(d.exported??d.count??0).toLocaleString()} / {(d.expected??d.count??0).toLocaleString()} rows</p>)}
 {run.status==='needs_credentials'&&<><p className="text-sm text-slate-600">{sourceDownloadsComplete?'Your completed table downloads are saved. Resume retries current inventory, using the Query API if the stock endpoint is unavailable, then runs validation.':'Completed pages are saved. Re-enter the key to resume this export.'}</p><Button disabled={!isAdmin||!key.trim()||busy} onClick={()=>void action(async()=>{await apiClient.post(`/joolan/fresh/${run.id}/resume`,{apiKey:key});setKey("");setMessage(sourceDownloadsComplete?'Resuming inventory and validation; completed tables are retained.':'Resuming this fresh export.');})}>{sourceDownloadsComplete?'Resume inventory and validation':'Resume this export with the key above'}</Button></>}
 </div>}
 </CardContent></Card>
 <Card><CardHeader><CardTitle>3. Review data validation</CardTitle></CardHeader><CardContent className="space-y-3">
 {run?.report?<><p>{run.report.catalogueVariants.toLocaleString()} catalogue variants · {run.report.orderLines.toLocaleString()} valid order lines · {run.report.stockRows.toLocaleString()} stock rows</p>{run.report.blockers.map(b=><p className="text-red-700" key={b}>{b}</p>)}{run.report.warnings.map(w=><p className="text-sm text-amber-800" key={w}>{w}</p>)}
 <Button disabled={!isAdmin||!run.report.readyForForecast||busy||exporting} onClick={()=>void action(async()=>{await apiClient.post(`/joolan/fresh/${run.id}/activate`);setMessage('Fresh Joolan data activated. Save a season and run the forecast.');})}>Use this validated fresh export</Button></>:<p>Validation checks source counts, order joins, quantities, cancellation fields, catalogue matches and warehouse stock coverage after download.</p>}
 <p className="text-sm text-slate-600">Purchase approval stays unavailable until costs, price/currency definitions, supplier receipt dates and lead times have verified mappings.</p>
 </CardContent></Card>
 <Card><CardHeader><CardTitle>4. Save a season and forecast</CardTitle></CardHeader><CardContent className="space-y-4">
 <label className="block">Season name<Input value={name} onChange={e=>setName(e.target.value)}/></label><div className="grid gap-4 md:grid-cols-2"><label>Start<Input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>End<Input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
 <Button disabled={!isAdmin||busy||!name||!start||end<start} onClick={()=>void action(async()=>{await createSeason({name,startDate:start,endDate:end,currency:'EUR',budget:0,targetMargin:0});setMessage('Season saved for demand forecasting.');})}>Save demand-planning season</Button>
 {ready&&<div><p>Last complete training month: {ready.trainingCutoff||'awaiting fresh export'}</p>{ready.blockers.map(b=><p key={b} className="text-amber-800">{b}</p>)}</div>}
 <Button disabled={!isAdmin||!ready?.ready||busy||exporting||job?.status==='running'} onClick={()=>void action(async()=>{await triggerForecastRefresh();setMessage('Forecast started using the activated fresh Joolan version.');})}>Run fresh-data forecast</Button>
 {job?.jobId&&<p>Forecast: {job.status}{job.errorMessage?` — ${job.errorMessage}`:''}</p>}
 {job?.status==='complete'&&<Link className="block underline" href="/dashboard">Open forecast dashboard</Link>}
 </CardContent></Card></div></AppShell>;
}
