"use client";
import {useCallback,useEffect,useState} from "react";
import Link from "next/link";
import {ArrowRightIcon,ArrowsClockwiseIcon,CalendarCheckIcon,CaretDownIcon,ChartLineUpIcon,CheckIcon,DatabaseIcon,FloppyDiskIcon,InfoIcon,PlayIcon,PlugsConnectedIcon,SealCheckIcon} from "@phosphor-icons/react";
import {useAuth} from '@/components/auth/AuthProvider';
import AppShell from "@/components/layout/AppShell";
import {BrandButton} from "@/components/ui/brand-button";
import {Notice,PageHeader,Pill,TextField} from "@/components/ui/brand";
import {apiClient} from "@/lib/api/client";
import {useSeasonStore} from "@/store/seasonStore";
import {getForecastJobStatus,triggerForecastRefresh,type ForecastJobStatus} from "@/lib/api/ingest";
import {cn} from "@/lib/utils";

type Report={readyForForecast:boolean;readyForPurchasing:boolean;blockers:string[];warnings:string[];catalogueVariants:number;stockRows:number;orderLines:number;missingStockVariants:number};
type Status={activeRun:string|null;discovery?:Schema|null;run:null|{id:string;status:string;phase:string;error:string|null;report:Report|null;datasets:{name:string;expected?:number;exported?:number;count?:number;complete:boolean}[]}};
type Schema={enseigne:string;warehouses:string[];warehouseDetails?:Record<string,unknown>[];warehouseBalances?:{Magasin:string;variants:number;physical:number;available:number}[];brands?:{Marque:string;products:number}[];tables:Record<string,{name:string;type:string;key:string}[]>;notice:string};
type Ready={ready:boolean;blockers:string[];warnings:string[];trainingCutoff:string|null};
const today=()=>new Date().toLocaleDateString("en-CA");
const fieldLabel="flex flex-col gap-2 text-sm font-bold text-fg-1";
const fieldInput="h-[52px] w-full rounded-[14px] text-[15px] font-semibold";

function Step({n,icon:StepIcon,title,children}:{n:number;icon:typeof PlugsConnectedIcon;title:string;children:React.ReactNode}){
 return <section className="flex flex-col gap-6 rounded-[32px] border border-line bg-card p-6 shadow-card sm:p-8">
  <div className="flex items-center gap-3.5">
   <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-700"><StepIcon weight="fill" className="h-[22px] w-[22px]"/></span>
   <h2 className="min-w-0 text-[22px] font-extrabold leading-tight tracking-[-0.02em]">{n}. {title}</h2>
  </div>
  {children}
 </section>;
}

function CheckPill({checked,disabled,onChange,children}:{checked:boolean;disabled:boolean;onChange:(checked:boolean)=>void;children:React.ReactNode}){
 return <label className={cn('flex h-10 cursor-pointer items-center gap-2.5 rounded-full border-[1.5px] pl-2.5 pr-3.5 text-[13px] font-semibold text-fg-1 transition-colors has-[:focus-visible]:shadow-[0_0_0_3px_rgba(245,130,32,0.35)]',checked?'border-brand bg-brand-soft':'border-line bg-card hover:border-border-strong',disabled&&'cursor-not-allowed opacity-60')}>
  <input type="checkbox" className="sr-only" checked={checked} disabled={disabled} onChange={e=>onChange(e.target.checked)}/>
  <span aria-hidden className={cn('flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-[1.5px]',checked?'border-brand bg-brand':'border-border-strong')}>{checked&&<CheckIcon weight="bold" className="h-3 w-3 text-white"/>}</span>
  {children}
 </label>;
}

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
 return <AppShell><div className="mx-auto flex w-full max-w-[1040px] flex-col gap-6 pb-12">
 <PageHeader eyebrow="Administrator connection tools" title="Fresh Joolan setup" description={<>New API exports supply the catalogue, customer orders and warehouse stock. Previous CSVs and imports are excluded.</>}/>
 <div className="flex items-start gap-3.5 rounded-[20px] bg-soft px-[22px] py-4">
  <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-plum-600"/>
  <p className="text-pretty text-sm leading-relaxed text-fg-2"><Link className="font-bold text-brand-700 hover:text-brand-800 hover:underline" href="/scope">Review business brands and warehouse roles</Link> before running the next forecast. Export warehouse selection controls downloaded inventory; Business Scope controls which stock supplies standard orders.</p>
 </div>
 {error&&<Notice tone="danger">{error}</Notice>}
 {message&&<Notice tone="success">{message}</Notice>}

 <Step n={1} icon={PlugsConnectedIcon} title="Connect and inspect available fields">
  <div className="grid gap-4 md:grid-cols-2">
   <label className={fieldLabel}>Enseigne<TextField className={fieldInput} value={enseigne} onChange={e=>{setEnseigne(e.target.value);setSchema(null);setWarehouses([]);}} disabled={!isAdmin||busy||exporting}/></label>
   <label className={fieldLabel}>Joolan API key<TextField className={fieldInput} type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} disabled={!isAdmin||busy||exporting}/></label>
  </div>
  <p className="text-pretty text-[13px] leading-relaxed text-fg-2">Required permissions: api_query and api_stock. The key is sent to the local backend and stays in memory. It is cleared after starting an export.</p>
  <div><BrandButton disabled={!isAdmin||!key.trim()||busy||exporting} onClick={()=>void action(async()=>{const s=await apiClient.post<Schema>('/joolan/fresh/preflight',{apiKey:key},{enseigne});setSchema(s);setMessage(s.notice);})}><PlugsConnectedIcon/>Check connection and discover fields</BrandButton></div>
  {schema&&<details className="group border-t border-line">
   <summary className="flex cursor-pointer list-none items-center justify-between py-[18px] text-[15px] font-bold text-fg-1 [&::-webkit-details-marker]:hidden">Live table and column dictionary ({Object.keys(schema.tables).length} tables)<CaretDownIcon weight="bold" className="h-3.5 w-3.5 text-fg-3 transition-transform group-open:rotate-180"/></summary>
   <div className="max-h-72 overflow-auto rounded-[18px] bg-page p-4 text-[13px] leading-relaxed">{Object.entries(schema.tables).map(([table,columns])=><div className="mb-3 last:mb-0" key={table}><strong className="font-mono text-fg-1">{table}</strong><p className="font-mono text-xs text-fg-2">{columns.map(c=>`${c.name} (${c.type}${c.key?`, ${c.key}`:''})`).join(' · ')}</p></div>)}</div>
  </details>}
 </Step>

 <Step n={2} icon={DatabaseIcon} title="Start a new full export">
  <p className="text-pretty text-sm leading-relaxed text-fg-2">Customer-order type: <strong className="font-mono text-fg-1">COMMANDE</strong>. All available order history through the selected date is downloaded anew. Each export gets its own database version.</p>
  <div className="flex flex-wrap items-end gap-3">
   <label className={cn(fieldLabel,'flex-[1_1_260px] sm:max-w-sm')}>History end date (all earlier years included)<TextField className={fieldInput} type="date" value={through} max={today()} onChange={e=>setThrough(e.target.value)} disabled={!isAdmin||busy||exporting}/></label>
   <BrandButton variant="outline" size="lg" disabled={!isAdmin||busy||exporting} onClick={()=>setThrough(today())}><CalendarCheckIcon/>Use today as end date</BrandButton>
  </div>
  <fieldset className="flex flex-col gap-3">
   <legend className="mb-3 text-sm font-bold text-fg-1">Product brands for this forecast</legend>
   <div className="flex flex-wrap gap-2.5">{(schema?.brands||[{Marque:'DAYTONA73',products:0}]).filter(b=>b.Marque).map(b=><CheckPill key={b.Marque} checked={brands.includes(b.Marque)} disabled={!isAdmin||busy||exporting} onChange={checked=>setBrands(v=>checked?[...v,b.Marque]:v.filter(x=>x!==b.Marque))}><span className="font-mono">{b.Marque}</span>{b.products?<span className="font-normal text-fg-3">({b.products})</span>:null}</CheckPill>)}</div>
   <p className="text-[13px] leading-relaxed text-fg-3">Other brands are excluded. Select D73 only if it is part of the same business scope.</p>
  </fieldset>
  {schema?.warehouseDetails&&<div className="overflow-x-auto rounded-[20px] border border-line"><table className="w-full min-w-[640px] text-left text-sm">
   <thead className="border-b border-line bg-page text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3"><tr><th className="px-4 py-3">Warehouse</th><th className="px-4 py-3">Name / company</th><th className="px-4 py-3">Depot flag</th><th className="px-4 py-3">Closed flag</th><th className="px-4 py-3 text-right">Available units (all brands)</th></tr></thead>
   <tbody className="divide-y divide-line">{schema.warehouseDetails.map(d=><tr key={String(d.Magasin)}><td className="px-4 py-3 font-mono font-bold">{String(d.Magasin)}</td><td className="px-4 py-3 text-fg-2">{String(d.Nom||'')} / {String(d.Societe||'')}</td><td className="px-4 py-3 font-mono text-[13px] text-fg-2">{String(d.Depot??'unknown')}</td><td className="px-4 py-3 font-mono text-[13px] text-fg-2">{String(d.magasin_ferme??'unknown')}</td><td className="px-4 py-3 text-right font-mono font-bold">{schema.warehouseBalances?.find(b=>b.Magasin===d.Magasin)?.available?.toLocaleString()??'unknown'}</td></tr>)}</tbody>
  </table></div>}
  <fieldset className="flex flex-col">
   <legend className="mb-3 text-sm font-bold text-fg-1">Warehouses available to supply these customers</legend>
   {schema?.warehouses.length?<div className="flex flex-wrap gap-2.5">{schema.warehouses.map(w=><CheckPill key={w} checked={warehouses.includes(w)} disabled={!isAdmin||busy||exporting} onChange={checked=>setWarehouses(v=>checked?[...v,w]:v.filter(x=>x!==w))}><span className="font-mono">{w}</span></CheckPill>)}</div>:<p className="text-[13px] leading-relaxed text-fg-3">Check the connection to retrieve warehouse codes, then select the supplying warehouses.</p>}
  </fieldset>
  <div className="flex flex-wrap items-center justify-between gap-5 rounded-3xl bg-page px-5 py-5 sm:px-6">
   <p className="flex-[1_1_360px] text-pretty text-[13px] leading-relaxed text-fg-2">New export: <strong className="text-fg-1">{brands.join(', ')||'select a brand'}</strong>, all history through <strong className="text-fg-1">{through}</strong>, stock from <strong className="text-fg-1">{warehouses.join(', ')||'select warehouses'}</strong>.</p>
   <BrandButton size="lg" disabled={!isAdmin||!key.trim()||!warehouses.length||!brands.length||busy||exporting} onClick={()=>void action(async()=>{await apiClient.post('/joolan/fresh',{apiKey:key,enseigne,documentType:'COMMANDE',throughDate:through,warehouses,brands});setKey("");setMessage('Fresh export started. Saved pages belong only to this new export.');})}><PlayIcon/>Start fresh Joolan export</BrandButton>
  </div>
  {run&&<div className="flex flex-col gap-4 rounded-3xl border border-line p-5 sm:p-6">
   <div className="flex flex-col gap-1">
    <span className={cn('text-xs font-bold uppercase tracking-[0.12em]',run.status==='complete'?'text-success-600':run.status==='needs_credentials'||run.status==='failed'?'text-brand-800':'text-brand')}>{run.status.replaceAll('_',' ')}</span>
    <p className="text-lg font-extrabold tracking-[-0.01em]">{run.phase}</p>
    <p className="font-mono text-xs text-fg-3">Export {run.id}</p>
   </div>
   {run.error&&<Notice tone="danger">{run.error}</Notice>}
   {!!run.datasets.filter(d=>d.name!=='schema').length&&<div className="flex flex-col">{run.datasets.filter(d=>d.name!=='schema').map(d=><div key={d.name} className="flex flex-wrap items-center justify-between gap-3 border-b border-line py-2.5 text-[13px] last:border-b-0">
    <span className="font-mono font-semibold">{d.name}</span>
    <span className="flex items-center gap-2.5 text-fg-2"><Pill tone={d.complete?'success':'brand'}>{d.complete?'complete':'downloading'}</Pill><span className="font-mono">{(d.exported??d.count??0).toLocaleString()} / {(d.expected??d.count??0).toLocaleString()} rows</span></span>
   </div>)}</div>}
   {run.status==='needs_credentials'&&<div className="flex flex-col gap-3 rounded-[18px] bg-brand-50 p-4">
    <p className="text-pretty text-sm leading-relaxed text-fg-1">{sourceDownloadsComplete?'Your completed table downloads are saved. Resume retries current inventory, using the Query API if the stock endpoint is unavailable, then runs validation.':'Completed pages are saved. Re-enter the key to resume this export.'}</p>
    <div><BrandButton disabled={!isAdmin||!key.trim()||busy} onClick={()=>void action(async()=>{await apiClient.post(`/joolan/fresh/${run.id}/resume`,{apiKey:key});setKey("");setMessage(sourceDownloadsComplete?'Resuming inventory and validation; completed tables are retained.':'Resuming this fresh export.');})}><ArrowsClockwiseIcon/>{sourceDownloadsComplete?'Resume inventory and validation':'Resume this export with the key above'}</BrandButton></div>
   </div>}
  </div>}
 </Step>

 <Step n={3} icon={SealCheckIcon} title="Review data validation">
  {run?.report?<div className="flex flex-col gap-4">
   <div className="grid gap-3 sm:grid-cols-3">
    {[[run.report.catalogueVariants,'catalogue variants'],[run.report.orderLines,'valid order lines'],[run.report.stockRows,'stock rows']].map(([value,label])=><div key={String(label)} className="flex flex-col gap-1 rounded-[20px] bg-page p-4"><span className="font-display text-[26px] font-bold tracking-[-0.02em]">{Number(value).toLocaleString()}</span><span className="text-[13px] text-fg-3">{label}</span></div>)}
   </div>
   {run.report.blockers.map(b=><p className="text-sm leading-relaxed text-danger" key={b}>{b}</p>)}
   {run.report.warnings.map(w=><p className="text-sm leading-relaxed text-brand-800" key={w}>{w}</p>)}
   <div><BrandButton disabled={!isAdmin||!run.report.readyForForecast||busy||exporting} onClick={()=>void action(async()=>{await apiClient.post(`/joolan/fresh/${run.id}/activate`);setMessage('Fresh Joolan data activated. Save a season and run the forecast.');})}><CheckIcon/>Use this validated fresh export</BrandButton></div>
  </div>:<p className="text-pretty text-sm leading-relaxed text-fg-2">Validation checks source counts, order joins, quantities, cancellation fields, catalogue matches and warehouse stock coverage after download.</p>}
  <Notice tone="brand">Purchase approval stays unavailable until costs, price/currency definitions, supplier receipt dates and lead times have verified mappings.</Notice>
 </Step>

 <Step n={4} icon={ChartLineUpIcon} title="Save a season and forecast">
  <label className={fieldLabel}>Season name<TextField className={fieldInput} value={name} onChange={e=>setName(e.target.value)}/></label>
  <div className="grid gap-4 md:grid-cols-2"><label className={fieldLabel}>Start<TextField className={fieldInput} type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label className={fieldLabel}>End<TextField className={fieldInput} type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
  <div><BrandButton variant="outline" disabled={!isAdmin||busy||!name||!start||end<start} onClick={()=>void action(async()=>{await createSeason({name,startDate:start,endDate:end,currency:'EUR',budget:0,targetMargin:0});setMessage('Season saved for demand forecasting.');})}><FloppyDiskIcon/>Save demand-planning season</BrandButton></div>
  {ready&&<div className="flex flex-col gap-1.5 rounded-[20px] bg-page px-5 py-4 text-sm leading-relaxed"><p className="text-fg-2">Last complete training month: <span className="font-mono font-bold text-fg-1">{ready.trainingCutoff||'awaiting fresh export'}</span></p>{ready.blockers.map(b=><p key={b} className="text-brand-800">{b}</p>)}</div>}
  <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-6">
   {job?.jobId?<p className="flex flex-wrap items-center gap-2 text-sm text-fg-2">Forecast: <Pill tone={job.status==='complete'?'success':job.status==='failed'?'danger':'brand'}>{job.status}</Pill>{job.errorMessage?<span className="text-danger">— {job.errorMessage}</span>:null}</p>:<span/>}
   <div className="flex flex-wrap gap-3">
    {job?.status==='complete'&&<BrandButton variant="outline" size="lg" asChild><Link href="/dashboard">Open forecast dashboard<ArrowRightIcon/></Link></BrandButton>}
    <BrandButton size="lg" disabled={!isAdmin||!ready?.ready||busy||exporting||job?.status==='running'} onClick={()=>void action(async()=>{await triggerForecastRefresh();setMessage('Forecast started using the activated fresh Joolan version.');})}><ChartLineUpIcon/>Run fresh-data forecast</BrandButton>
   </div>
  </div>
 </Step>
 </div></AppShell>;
}
