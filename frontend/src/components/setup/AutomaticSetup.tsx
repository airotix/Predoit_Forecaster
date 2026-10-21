"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowRightIcon,ArrowsClockwiseIcon,CalendarBlankIcon,CaretDownIcon,CaretUpIcon,CheckCircleIcon,CheckIcon,CircleNotchIcon,LockSimpleIcon,PauseCircleIcon,PlugIcon,PlugsConnectedIcon,WarningCircleIcon} from '@phosphor-icons/react';
import {useAuth} from '@/components/auth/AuthProvider';
import AppShell from '@/components/layout/AppShell';
import {BrandButton} from '@/components/ui/brand-button';
import SeasonSwitcher from '@/components/setup/SeasonSwitcher';
import {apiClient} from '@/lib/api/client';
import {seasonsApi} from '@/lib/api/seasons';
import {useSeasonStore} from '@/store/seasonStore';
import {roleMeetsRequired} from '@/lib/auth/msalConfig';
import {cn} from '@/lib/utils';

interface Job{id:string;status:string;phase:string;startDate:string;endDate:string;throughDate:string;runId:string|null;seasonId:string|null;forecastRun:string|null;error?:string|null;retryAt?:string|null;warnings?:string[];}
interface Data{configured:boolean;enseigne:string;job:Job|null;export:null|{status:string;phase:string;error:string|null;datasets:{name:string;complete:boolean;exported?:number;count?:number;expected?:number}[];report:null|{orderLines:number;catalogueVariants:number;stockRows:number;blockers:string[];warnings:string[];exportAudit?:{allComplete:boolean;tables:{table:string;stored:number;expected:number;complete:boolean}[];unavailableTables:string[];fieldAudit?:Record<string,{available:string[];unavailable:string[]}>;notice:string}}};}
const month=()=>new Date().toLocaleDateString('en-CA').slice(0,7);
const endOfMonth=(value:string)=>{const [y,m]=value.split('-').map(Number);return `${value}-${new Date(y,m,0).getDate()}`;};
const STEPS=['Download & reconcile','Validate & prepare','Forecast & publish'];
/** Which of the three workflow steps a server phase belongs to. */
const stepOf=(phase:string)=>/training|forecasting/i.test(phase)&&!/published/i.test(phase)?2:/selecting|preparing|validat/i.test(phase)?1:0;
const inputClass='h-[52px] rounded-[14px] border-[1.5px] border-border-strong bg-card px-4 text-[15px] font-semibold text-fg-1 outline-none [color-scheme:light_dark] focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:cursor-not-allowed disabled:opacity-60';

function Disclosure({title,children}:{title:string;children:React.ReactNode}){
 const [open,setOpen]=useState(false);
 return <div className="border-t border-line">
  <button type="button" aria-expanded={open} onClick={()=>setOpen(v=>!v)} className="flex w-full items-center justify-between py-[18px] text-left text-[15px] font-bold text-fg-1">{title}{open?<CaretUpIcon weight="bold" className="h-3.5 w-3.5 text-fg-3"/>:<CaretDownIcon weight="bold" className="h-3.5 w-3.5 text-fg-3"/>}</button>
  {open&&<div className="pb-3">{children}</div>}
 </div>;
}

export default function AutomaticSetup(){
 const {role}=useAuth();const isAdmin=role==='admin'||role==='owner';
 const active=useSeasonStore(s=>s.activeSeason);
 const [start,setStart]=useState(active?.startDate&&active.startDate.slice(0,7)>=month()?active.startDate.slice(0,7):month());
 const [end,setEnd]=useState(()=>{if(active?.endDate&&active.endDate.slice(0,7)>=start)return active.endDate.slice(0,7);const [y,m]=start.split('-').map(Number);return new Date(y,m-1+5,1).toLocaleDateString('en-CA').slice(0,7);});
 const [data,setData]=useState<Data|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[connectionError,setConnectionError]=useState('');
 const completed=useRef(''),request=useRef({version:0});
 const load=useCallback(async()=>{const version=++request.current.version;try{const result=await apiClient.get<Data>('/automatic');if(version!==request.current.version)return;setData(result);setConnectionError('');
  if(result.job?.status==='complete'&&completed.current!==result.job.id){completed.current=result.job.id;const selected=await seasonsApi.active();if(selected)useSeasonStore.getState().setActiveSeason(selected);useSeasonStore.getState().setSeasons(await seasonsApi.list());}
 }catch(e){if(version===request.current.version)setConnectionError(e instanceof Error?e.message:'Could not read workflow status.');}},[]);
 useEffect(()=>{void load();const timer=setInterval(()=>void load(),5000);const token=request.current;return()=>{clearInterval(timer);token.version++;};},[load]);
 const job=data?.job;const running=!!job&&['queued','running','waiting'].includes(job.status);const paused=job?.status==='paused';const complete=job?.status==='complete';
 async function action(path:string,body:unknown={}){if(!isAdmin){setError('An administrator is required to manage exports and forecasts.');return;}setBusy(true);setError('');try{await apiClient.post(path,body);await load();}catch(e){setError(e instanceof Error?e.message:'Could not start the forecast.');}finally{setBusy(false);}}
 const phaseIndex=job?stepOf(job.phase):0;
 const ConnIcon=data?.configured?PlugsConnectedIcon:PlugIcon;
 const JobIcon=complete?CheckCircleIcon:paused?PauseCircleIcon:CircleNotchIcon;
 return <AppShell><div className="mx-auto flex w-full max-w-[1040px] flex-col gap-6">
  <header className="flex flex-col gap-2">
   <span className="text-xs font-bold uppercase tracking-[0.12em] text-brand">Joolan connected planning</span>
   <h1 className="font-display text-[40px] font-extrabold leading-[1.08] tracking-[-0.02em]">Create a forecast</h1>
   <p className="max-w-[760px] text-pretty text-base leading-relaxed text-fg-2">Choose the months you want to plan. We retrieve current Joolan data, check the full export for missing records and fields, then calculate and publish your forecast.</p>
  </header>
  {!isAdmin&&<div role="status" className="flex items-center gap-3 rounded-2xl border border-brand-200 bg-brand-50 px-[18px] py-3.5"><LockSimpleIcon weight="fill" className="h-[18px] w-[18px] shrink-0 text-brand-700"/><p className="text-sm leading-[1.55]">Only an administrator can start or manage data exports and forecast runs.</p></div>}
  {(error||connectionError)&&<div role="alert" className="flex items-center gap-3 rounded-2xl bg-danger-soft px-[18px] py-3.5"><WarningCircleIcon weight="fill" className="h-[18px] w-[18px] shrink-0 text-danger"/><p className="text-sm leading-[1.55]">{error||connectionError}</p></div>}

  <section className="flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-line bg-card px-6 py-5 shadow-card">
   <div className="flex min-w-0 items-center gap-3.5">
    <span className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl',data?.configured?'bg-success-50 text-success-600':'bg-brand-50 text-brand-700')}><ConnIcon weight="fill" className="h-[22px] w-[22px]"/></span>
    <span className="flex min-w-0 flex-col gap-[3px]"><span className="text-base font-bold">{data?.configured?'Server connection configured':'Server connection needed'}</span><span className="text-[13px] leading-[1.45] text-fg-3">{data?.configured?`${data.enseigne} · key stays on the backend`:'Administrator: set JOOLAN_API_KEY in backend-ai/.env. The page detects it automatically.'}</span></span>
   </div>
   <Link href="/scope" className="flex items-center gap-1.5 text-sm font-bold text-brand-700 hover:text-brand-800">Business scope<ArrowRightIcon className="h-4 w-4"/></Link>
  </section>

  <SeasonSwitcher disabled={!roleMeetsRequired(role,'manager')||running}/>

  <section className="overflow-hidden rounded-[32px] border border-line bg-card shadow-card">
   <div className="flex flex-col gap-6 p-6 sm:p-8">
    <div className="flex flex-col gap-1.5">
     <h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-0.02em]"><CalendarBlankIcon className="h-[22px] w-[22px] text-brand"/>Forecast period</h2>
     <p className="text-sm leading-relaxed text-fg-2">Monthly forecasts for the current or future season. Complete historical months are used for training; current stock is refreshed for buying decisions.</p>
    </div>
    <div className="flex flex-wrap items-end gap-4">
     <label className="flex flex-[1_1_220px] flex-col gap-2 text-sm font-bold">From month<input className={inputClass} type="month" min={month()} value={start} disabled={!isAdmin||busy||running} onChange={e=>setStart(e.target.value)}/></label>
     <ArrowRightIcon aria-hidden className="mb-4 hidden h-5 w-5 text-fg-3 sm:block"/>
     <label className="flex flex-[1_1_220px] flex-col gap-2 text-sm font-bold">Through month<input className={inputClass} type="month" min={start||month()} value={end} disabled={!isAdmin||busy||running} onChange={e=>setEnd(e.target.value)}/></label>
    </div>
   </div>
   <div className="flex flex-wrap items-center justify-between gap-5 border-t border-line bg-page px-6 py-6 sm:px-8">
    <p className="max-w-[580px] flex-[1_1_360px] text-pretty text-[13px] leading-relaxed text-fg-2">Four approved Daytona 73 / Iron and Resin brand codes. CENTRAL supplies standard orders. Historical selling-price defaults and your manual catalogue updates are retained. New periods start without an assumed buying budget.</p>
    <BrandButton size="lg" disabled={!isAdmin||!data?.configured||busy||running||paused||!start||!end||end<start} onClick={()=>void action('/automatic',{startDate:start+'-01',endDate:endOfMonth(end)})}>
     {busy||running?<CircleNotchIcon className="animate-spin"/>:<ArrowRightIcon/>}Refresh data &amp; forecast
    </BrandButton>
   </div>
  </section>

  {job&&<section className="flex flex-col gap-6 rounded-[32px] border border-line bg-card p-6 shadow-card sm:p-8">
   <div className="flex flex-wrap items-start justify-between gap-4">
    <div className="flex min-w-0 flex-col gap-1.5">
     <span className={cn('text-xs font-bold uppercase tracking-[0.12em]',complete?'text-success-600':paused?'text-brand-800':'text-brand')}>{job.status.replaceAll('_',' ')}</span>
     <h2 className="text-2xl font-extrabold tracking-[-0.02em]">{job.phase}</h2>
     <span className="text-[13px] text-fg-3">Forecast {job.startDate} to {job.endDate} · Joolan history through {job.throughDate}</span>
    </div>
    <span className={cn('flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full',complete?'bg-success-50 text-success-600':'bg-brand-50 text-brand-700')}><JobIcon weight={complete||paused?'fill':'bold'} className={cn('h-[26px] w-[26px]',running&&'animate-spin')}/></span>
   </div>
   <ol className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
    {STEPS.map((label,i)=>{const done=complete||((running||paused)&&i<phaseIndex);const current=running&&i===phaseIndex;
     return <li key={label} className={cn('flex items-center gap-3 rounded-[18px] border p-4',current?'border-brand-200 bg-brand-50':'border-transparent bg-soft')}>
      <span className={cn('flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full text-[13px] font-bold',done?'bg-success-400 text-white':current?'bg-brand text-white':'bg-card text-fg-3')}>{done?<CheckIcon weight="bold" className="h-3.5 w-3.5"/>:i+1}</span>
      <span className="text-sm font-semibold">{label}</span>
     </li>;})}
   </ol>
   {running&&<p role="status" className="text-sm leading-relaxed text-fg-2">{job.phase==='Downloading and reconciling Joolan data'?(data?.export?.phase||job.phase):job.phase} Full-history reconciliation may take time. You may leave this page; the server continues the job.</p>}
   {job.retryAt&&<p className="rounded-2xl bg-brand-50 px-[18px] py-4 text-sm leading-relaxed">{job.phase.includes('quota')?'Joolan quota reached.':'Connection interrupted.'} Saved pages are retained and the next retry is scheduled for {new Date(job.retryAt).toLocaleString()}. No API-key re-entry is needed.</p>}
   {job.error&&<p role="alert" className="rounded-2xl border border-brand-200 bg-brand-50 px-[18px] py-4 text-sm leading-relaxed text-brand-800">{job.error}</p>}
   {paused&&<div className="flex flex-wrap gap-3">
    <BrandButton disabled={!isAdmin||busy||!data?.configured} onClick={()=>void action(`/automatic/${job.id}/resume`)}><ArrowsClockwiseIcon/>Retry with server connection</BrandButton>
    <BrandButton variant="outline" disabled={!isAdmin||busy} onClick={()=>void action(`/automatic/${job.id}/dismiss`)}>Dismiss job and choose another period</BrandButton>
   </div>}
   {complete&&<div><BrandButton asChild><Link href="/dashboard">Open forecast dashboard<ArrowRightIcon/></Link></BrandButton></div>}
   {(data?.export||data?.export?.report?.exportAudit?.fieldAudit)&&<div className="flex flex-col">
    {data?.export&&<Disclosure title="Data quality and export details"><div className="flex flex-col">
     {data.export.datasets.filter(d=>d.name!=='schema').map(d=><div key={d.name} className="flex items-center justify-between gap-3 border-b border-line py-2.5 text-[13px]">
      <span className="font-mono font-semibold">{d.name}</span>
      <span className="flex items-center gap-2.5 text-fg-2"><span className={cn('rounded-full px-2.5 py-[3px] text-xs font-bold',d.complete?'bg-success-50 text-success-600':'bg-brand-50 text-brand-800')}>{d.complete?'Complete':'In progress'}</span><span className="font-mono">{(d.exported??d.count??0).toLocaleString()} / {(d.expected??d.count??0).toLocaleString()} rows</span></span>
     </div>)}
     {data.export.report?.exportAudit&&<p className="mt-3 text-[13px] leading-relaxed text-fg-2">{data.export.report.exportAudit.allComplete?'All downloaded tables passed final count and boundary checks. ':''}{data.export.report.exportAudit.notice}</p>}
     {!!data.export.report?.exportAudit?.unavailableTables.length&&<p className="mt-1.5 text-[13px] leading-relaxed text-fg-2">Tables not exposed by Joolan: {data.export.report.exportAudit.unavailableTables.join(', ')}.</p>}
     {data.export.report?.blockers.map(text=><p key={text} className="mt-1.5 text-[13px] leading-relaxed text-danger">{text}</p>)}
     {data.export.report?.warnings.map(text=><p key={text} className="mt-1.5 text-[13px] leading-relaxed text-brand-800">{text}</p>)}
    </div></Disclosure>}
    {data?.export?.report?.exportAudit?.fieldAudit&&<Disclosure title="Fields unavailable in the source"><div className="flex flex-col gap-1.5 text-[13px] leading-relaxed text-brand-800">
     {Object.entries(data.export.report.exportAudit.fieldAudit).filter(([,group])=>group.unavailable.length).map(([name,group])=><p key={name}>{name}: {group.unavailable.join(', ')}.</p>)}
    </div></Disclosure>}
   </div>}
  </section>}

  <p className="max-w-[900px] text-pretty text-[13px] leading-relaxed text-fg-3">No CSV import or API-key entry is needed here. Missing source fields remain unknown and appear in the data-quality report. Forecasting can complete while financial approval waits for complete prices, supplier commitments and a saved buying budget. <Link href="/setup/manual" className="font-semibold text-brand-700 hover:text-brand-800">Administrator connection tools</Link></p>
 </div></AppShell>;
}
