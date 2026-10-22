"use client";
import ActivityBadge,{type ArticleActivity} from '@/components/shared/ArticleActivity';
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowRightIcon,ArrowsClockwiseIcon,CaretDownIcon,CheckCircleIcon,CircleIcon,DropIcon,FloppyDiskIcon,MagnifyingGlassIcon,SlidersHorizontalIcon,WarningIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,TextField} from '@/components/ui/brand';
import {ScenarioSwitcher} from '@/components/shared';
import {apiClient} from '@/lib/api/client';
import {cn} from '@/lib/utils';
import {useSeasonStore} from '@/store/seasonStore';
import {useDataRefresh} from '@/hooks/useDataRefresh';

interface Filters{startMonth:string;endMonth:string;codes:string[];}
interface Variant{color:string;size:string;skus:string[];forecast:number|null;booked:number|null;}
interface Article{activity?:ArticleActivity|null;reference:string;name:string;brand:string;code:string;forecast:number|null;knownForecast:number;forecastedVariants:number;missingVariants:number;colors:number;rows:Variant[];}
interface Allocation{allocation:Filters;saved:boolean;scenario:string;options:{code:string;articles:number;variants:number}[];published:{runId:string|null;startMonth:string|null;endMonth:string|null;matching:boolean};rows:Article[];total:number;summary:{articles:number;variants:number;forecastedVariants:number;missingVariants:number;knownForecastUnits:number;totalForecastUnits:number|null};notices:string[];}
const currentCodes=['H26','FW27','P27','CORE','RECONDUIT'];
const qty=(value:number|null)=>value==null?'—':value.toLocaleString(undefined,{maximumFractionDigits:2});
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XL2','XXXL','XL3','XL4','XL5','XL6','XL7'];
const sizeCompare=(a:Variant,b:Variant)=>{const ai=sizeOrder.indexOf(a.size),bi=sizeOrder.indexOf(b.size);return ai>=0&&bi>=0?ai-bi:a.size.localeCompare(b.size,undefined,{numeric:true});};
const SIZE_GRID='grid grid-cols-[44px_minmax(0,1fr)_76px_92px_112px] items-center gap-2';
const MONTH_INPUT='h-12 w-full rounded-[14px] text-[15px] font-semibold';

function ArticleAllocation({article}:{article:Article}){
 const colors=Array.from(new Set(article.rows.map(r=>r.color))).sort();
 return <details className="group overflow-hidden rounded-[20px] border border-line bg-card shadow-card open:border-brand-200">
  <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-4 px-[22px] py-[18px] hover:bg-page [&::-webkit-details-marker]:hidden">
   <div className="flex min-w-0 flex-col gap-1">
    <p className="flex items-center gap-2 text-xs text-fg-3">{article.brand} <span className="rounded-md bg-soft px-2 py-0.5 font-mono text-fg-2">{article.code}</span></p>
    <h3 className="text-base font-bold"><span className="font-mono text-brand-700">{article.reference}</span> <span className="ml-1 font-semibold">{article.name}</span></h3><ActivityBadge activity={article.activity}/>
    <p className="text-[13px] text-fg-3">{colors.length} colours · {article.rows.length} size variants</p>
   </div>
   <div className="flex items-center gap-[18px]">
    {article.missingVariants>0&&<span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-bold text-brand-800">{article.missingVariants} need estimation</span>}
    <div className="flex flex-col items-end"><p className="font-display text-[22px] font-bold tabular-nums">{qty(article.forecast)}</p><p className="text-xs text-fg-3">{article.forecast!=null?'Forecast units':article.forecastedVariants?`${qty(article.knownForecast)} known units · incomplete`:'Not forecasted'}</p></div>
    <span className="flex h-8 w-8 items-center justify-center rounded-full border border-line"><CaretDownIcon weight="bold" className="h-[13px] w-[13px] transition-transform group-open:rotate-180"/></span>
   </div>
  </summary>
  <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,380px),1fr))] items-start gap-3 border-t border-line bg-page px-[22px] pb-[22px] pt-4">
   {colors.map(color=>{const variants=article.rows.filter(r=>r.color===color).sort(sizeCompare);const complete=variants.every(v=>v.forecast!=null);
    return <details key={color} className="group/color overflow-hidden rounded-2xl border border-line bg-card">
     <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm hover:bg-page [&::-webkit-details-marker]:hidden">
      <span className="flex items-center gap-2 font-bold"><DropIcon weight="fill" className="h-[13px] w-[13px] shrink-0 text-brand"/>{color} <span className="font-normal text-fg-3">{variants.length} sizes</span></span>
      <span className="flex items-center gap-2.5"><span className={cn('font-bold tabular-nums',complete?'font-mono text-fg-1':'text-brand-800')}>{complete?qty(variants.reduce((sum,r)=>sum+(r.forecast||0),0)):'Incomplete forecast'}{complete?' units':''}</span><CaretDownIcon weight="bold" className="h-3 w-3 text-fg-3 transition-transform group-open/color:rotate-180"/></span>
     </summary>
     <div className="overflow-x-auto border-t border-line"><div role="table" aria-label={`${article.reference} ${color} sizes`} className="min-w-[420px]">
      <div role="row" className={cn(SIZE_GRID,'bg-page px-4 py-2 text-[10px] font-bold uppercase tracking-[0.08em] text-fg-3')}><span role="columnheader">Size</span><span role="columnheader">SKU</span><span role="columnheader" className="text-right">Forecast units</span><span role="columnheader" className="text-right">Booked units in interval</span><span role="columnheader">Coverage</span></div>
      {variants.map(r=><div role="row" key={r.size} className={cn(SIZE_GRID,'border-t border-line px-4 py-2 text-[13px]')}>
       <span role="cell" className="font-mono font-bold">{r.size}</span>
       <span role="cell" title={r.skus.join(', ')} className="truncate font-mono text-[11px] text-fg-3">{r.skus.join(', ')}</span>
       <span role="cell" className="text-right font-mono font-bold tabular-nums">{qty(r.forecast)}</span>
       <span role="cell" className="text-right font-mono tabular-nums text-fg-2">{qty(r.booked)}</span>
       <span role="cell" className={cn('flex items-center gap-1.5 text-xs font-semibold',r.forecast==null?'text-brand-800':'text-success-600')}><span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-current"/>{r.forecast==null?'Needs estimation':'Available'}</span>
      </div>)}
     </div></div>
    </details>;})}
  </div>
 </details>;
}

export default function SeasonalAllocationPage(){
 const {activeSeason,activeScenario}=useSeasonStore();
 const [data,setData]=useState<Allocation|null>(null);const [draft,setDraft]=useState<Filters|null>(null);const [applied,setApplied]=useState<Filters|null>(null);const [search,setSearch]=useState('');const [query,setQuery]=useState('');const [page,setPage]=useState(0);const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const [resetVersion,setResetVersion]=useState(0);const request=useRef({version:0});const initialised=useRef<string|null>(null);
 const load=useCallback(async()=>{const version=++request.current.version;setLoading(true);setError('');try{const result=await apiClient.get<Allocation>('/seasonal-allocation',{scenario:activeScenario,search:query,offset:page*20,limit:20,...(applied?{startMonth:applied.startMonth,endMonth:applied.endMonth,codes:JSON.stringify(applied.codes)}:{})});if(version!==request.current.version)return;setData(result);const key=activeSeason?.id||'current';if(initialised.current!==key){initialised.current=key;setDraft(result.allocation);}}catch(e){if(version===request.current.version){setData(null);setError(e instanceof Error?e.message:'Could not load seasonal allocation.');}}finally{if(version===request.current.version)setLoading(false);}},[activeScenario,activeSeason?.id,applied,page,query]);
 useEffect(()=>{setApplied(null);setPage(0);setQuery('');setSearch('');initialised.current=null;setDraft(null);},[activeSeason?.id]);
 useEffect(()=>{const token=request.current;void load();return()=>{token.version++;};},[load,resetVersion]);useDataRefresh(load);
 function reset(){request.current.version++;initialised.current=null;setApplied(null);setDraft(null);setPage(0);setQuery('');setSearch('');setNotice('');setResetVersion(v=>v+1);}
 function update(value:Partial<Filters>){setDraft(old=>old?{...old,...value}:old);setNotice('');}
 const valid=!!draft&&!!draft.startMonth&&!!draft.endMonth&&draft.endMonth>=draft.startMonth&&draft.codes.length>0;
 const signature=(f:Filters|null)=>f?`${f.startMonth}|${f.endMonth}|${[...f.codes].sort().join('|')}`:'';
 const dirty=!!draft&&!!data&&(signature(draft)!==signature(data.allocation)||search!==query);
 function apply(){if(!draft)return;setApplied({...draft,codes:[...draft.codes]});setQuery(search);setPage(0);setNotice('');}
 async function save(){if(!draft)return;setBusy(true);setError('');try{const result=await apiClient.put<{notice:string}>('/seasonal-allocation',draft);setApplied({...draft,codes:[...draft.codes]});setQuery(search);setPage(0);setNotice(result.notice);}catch(e){setError(e instanceof Error?e.message:'Could not save allocation.');}finally{setBusy(false);}}
 const codeOption=(option:Allocation['options'][number])=>{const on=!!draft?.codes.includes(option.code);return <label key={option.code} className={cn('flex cursor-pointer items-center gap-3 rounded-[18px] border-2 p-4 text-fg-1 transition-colors hover:border-brand has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60 has-[:focus-visible]:shadow-[0_0_0_3px_rgba(245,130,32,0.35)]',on?'border-brand bg-brand-soft':'border-line bg-card')}>
  <input type="checkbox" className="sr-only" disabled={busy} checked={on} onChange={e=>update({codes:e.target.checked?[...(draft?.codes||[]),option.code]:(draft?.codes||[]).filter(c=>c!==option.code)})}/>
  {on?<CheckCircleIcon weight="fill" aria-hidden className="h-[22px] w-[22px] shrink-0 text-brand"/>:<CircleIcon aria-hidden className="h-[22px] w-[22px] shrink-0 text-fg-4"/>}
  <span className="flex flex-col gap-0.5"><span className="font-mono text-[15px] font-bold">{option.code}</span><span className="text-xs text-fg-3">{option.articles.toLocaleString()} articles</span></span>
 </label>;};
 const tiles=data?[
  {label:'Matching articles',value:data.summary.articles.toLocaleString(),sub:`${data.summary.variants.toLocaleString()} colour / size variants`},
  {label:'Forecast units · covered variants',value:data.summary.forecastedVariants?qty(data.summary.knownForecastUnits):'—',sub:`${data.summary.forecastedVariants.toLocaleString()} of ${data.summary.variants.toLocaleString()} variants have forecasts`,hero:true},
  {label:'Need estimation',value:data.summary.missingVariants.toLocaleString(),sub:'Missing forecasts stay unknown',accent:true},
  {label:'Published forecast',value:`${data.published.startMonth||'—'} → ${data.published.endMonth||'—'}`,sub:`${activeScenario} scenario`,small:true},
 ]:[];
 return <AppShell>
  <PageHeader eyebrow="Plan by article season" title="Seasonal allocation" description="Choose article season codes and forecast months. Review the available quantities by article, colour and size." actions={<ScenarioSwitcher/>}/>

  <section className="flex flex-col gap-[22px] rounded-[32px] border border-line bg-card p-6 shadow-card sm:px-8 sm:py-7">
   <h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-0.02em]"><SlidersHorizontalIcon className="h-[22px] w-[22px] text-brand"/>Allocation selection</h2>
   <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
    <label className="flex flex-col gap-2 text-[13px] font-semibold text-fg-2">From forecast month<TextField aria-label="Allocation start month" className={MONTH_INPUT} type="month" value={draft?.startMonth||''} disabled={!draft||busy} onChange={e=>update({startMonth:e.target.value})}/></label>
    <label className="flex flex-col gap-2 text-[13px] font-semibold text-fg-2">To forecast month<TextField aria-label="Allocation end month" className={MONTH_INPUT} type="month" value={draft?.endMonth||''} disabled={!draft||busy} onChange={e=>update({endMonth:e.target.value})}/></label>
    <label className="flex flex-col gap-2 text-[13px] font-semibold text-fg-2">Find an article<span className="relative flex items-center"><MagnifyingGlassIcon aria-hidden className="pointer-events-none absolute left-3.5 h-4 w-4 text-fg-3"/><TextField aria-label="Search seasonal articles" className="h-12 w-full rounded-[14px] pl-10 text-[15px] font-normal" placeholder="Article, name or brand" value={search} onChange={e=>setSearch(e.target.value)}/></span></label>
   </div>
   <div className="flex flex-col gap-2.5">
    <p className="text-[13px] font-semibold text-fg-2">Article season codes · select one or more</p>
    <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">{data?.options.filter(o=>currentCodes.includes(o.code)||draft?.codes.includes(o.code)).map(codeOption)}</div>
    {data&&data.options.some(o=>!currentCodes.includes(o.code)&&!draft?.codes.includes(o.code))&&<details className="group/other">
     <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 py-1 text-[13px] font-bold text-brand-700 hover:text-brand-800 [&::-webkit-details-marker]:hidden">Other catalogue season codes<CaretDownIcon weight="bold" className="h-3 w-3 transition-transform group-open/other:rotate-180"/></summary>
     <div className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">{data.options.filter(o=>!currentCodes.includes(o.code)&&!draft?.codes.includes(o.code)).map(codeOption)}</div>
    </details>}
   </div>
   <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line pt-5">
    <p className="max-w-[640px] flex-[1_1_360px] text-pretty text-[13px] leading-relaxed text-fg-2">Season codes are article attributes. Forecast months follow the published planning interval; recorded orders retain their actual dates. Save this selection for the current planning season.</p>
    <div className="flex flex-wrap gap-2.5"><BrandButton variant="outline" disabled={!valid||loading||busy} onClick={apply}>Apply selection</BrandButton><BrandButton disabled={!valid||loading||busy} onClick={()=>void save()}><FloppyDiskIcon/>{busy?'Saving…':'Save allocation'}</BrandButton></div>
   </div>
  </section>

  {error&&<Notice tone="danger">{error} <button type="button" className="ml-2 font-bold text-danger underline underline-offset-2" onClick={reset}>Reset selection and retry</button> · <Link href="/setup" className="font-bold text-brand-700 underline underline-offset-2">Open Setup</Link></Notice>}
  {notice&&<Notice tone="success">{notice}</Notice>}
  {dirty&&!loading&&<p role="status" className="flex items-center gap-2.5 text-sm font-semibold text-brand-800"><ArrowsClockwiseIcon weight="fill" aria-hidden className="h-4 w-4 shrink-0"/>Selection changed. Apply it to update the quantities below.</p>}

  {data&&<>
   <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
    {tiles.map(t=><div key={t.label} className={cn('relative flex flex-col gap-1.5 overflow-hidden rounded-3xl p-[22px]',t.hero?'bg-champagne':'border border-line bg-card shadow-card')}>
     {t.hero&&<span aria-hidden className="absolute -right-[50px] -top-[60px] h-[170px] w-[170px] rounded-full bg-[radial-gradient(circle,var(--glow),rgba(245,130,32,0)_70%)]"/>}
     <p className={cn('relative text-[13px] font-semibold',t.hero?'text-brand-800':'text-fg-2')}>{t.label}</p>
     <p className={cn('relative font-display font-bold tabular-nums',t.small?'text-2xl':'text-[32px]',t.accent&&'text-brand-700')}>{t.value}</p>
     <p className={cn('relative text-[13px]',t.hero?'text-fg-2':'text-fg-3')}>{t.sub}</p>
    </div>)}
   </div>
   {data.notices.length>0&&<div role="status" className="flex items-start gap-3 rounded-2xl border border-brand-200 bg-brand-50 px-[18px] py-4 text-sm leading-[1.55]">
    <WarningIcon weight="fill" aria-hidden className="mt-0.5 h-[18px] w-[18px] shrink-0 text-brand-700"/>
    <div className="flex flex-col gap-2"><ul className="list-disc space-y-1 pl-5">{data.notices.map(n=><li key={n}>{n}</li>)}</ul><Link href="/setup" className="flex w-fit items-center gap-1.5 font-bold text-brand-700 hover:text-brand-800">Open forecasting setup<ArrowRightIcon className="h-4 w-4"/></Link></div>
   </div>}
   <div className="flex flex-col gap-1"><h2 className="text-[22px] font-extrabold tracking-[-0.02em]">Articles in this allocation</h2><p className="text-[13px] text-fg-3">{data.allocation.codes.join(' · ')} · {data.allocation.startMonth} to {data.allocation.endMonth}. Quantities cover all customers. Open an article, then a colour to see its sizes.</p></div>
   {loading?<p role="status" className="rounded-[20px] border border-line bg-card p-8 text-sm text-fg-3">Loading the selected forecast interval…</p>:<div className="flex flex-col gap-3">{data.rows.map(a=><ArticleAllocation key={a.reference} article={a}/>)}{!data.rows.length&&<p className="rounded-[20px] border border-line bg-card p-8 text-sm text-fg-3">No articles match this selection.</p>}</div>}
   <footer className="flex flex-wrap items-center justify-between gap-3 text-[13px] text-fg-3"><span>{data.total.toLocaleString()} articles · page {page+1} of {Math.max(1,Math.ceil(data.total/20))}</span><div className="flex gap-2"><BrandButton size="sm" variant="outline" disabled={loading||page===0} onClick={()=>setPage(p=>p-1)}>Previous</BrandButton><BrandButton size="sm" variant="outline" disabled={loading||(page+1)*20>=data.total} onClick={()=>setPage(p=>p+1)}>Next</BrandButton></div></footer>
   <p className="max-w-[900px] text-pretty text-[13px] leading-relaxed text-fg-3">These are saved monthly demand forecasts, with fractional expected units retained. A zero is a recorded zero forecast; “—” means no complete forecast is available. Generate another date interval in Setup. <Link href="/budget" className="font-bold text-brand-700 hover:text-brand-800">Review purchase quantities and financial limits in Budget Tracker.</Link></p>
  </>}
  {loading&&!data&&<p role="status" className="p-6 text-sm text-fg-3">Loading article seasons and published quantities…</p>}
 </AppShell>;
}
