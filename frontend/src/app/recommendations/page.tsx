"use client";
import ActivityBadge from '@/components/shared/ArticleActivity';
// @refresh reset
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowCounterClockwiseIcon,FloppyDiskIcon,LockSimpleIcon,LockSimpleOpenIcon,MagnifyingGlassIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher,ConfidenceBadge} from '@/components/shared';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,SelectField,TextField} from '@/components/ui/brand';
import {cn} from '@/lib/utils';
import {useSeasonStore} from '@/store/seasonStore';
import {useDataRefresh} from '@/hooks/useDataRefresh';
import {fetchRecommendations,updateRecommendation,lockRecommendation,unlockRecommendation,resetRecommendation,type RecommendationRow} from '@/lib/api/forecast';
import {recommendationArticles,filterRecommendationArticles,completeQuantity} from '@/lib/recommendationArticles';
const qty=(n:number|null)=>n==null?'Unresolved':n.toLocaleString('en-GB',{maximumFractionDigits:1});
const SIZE_GRID='grid grid-cols-[80px_repeat(3,minmax(0,1fr))_170px] gap-3';
export default function Recommendations(){
 const {activeScenario,activeSeason}=useSeasonStore();const sequence=useRef({version:0});
 const [rows,setRows]=useState<RecommendationRow[]>([]);const [selectedId,setSelectedId]=useState<string|null>(null);
 const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
 const [search,setSearch]=useState('');const [status,setStatus]=useState('');const [category,setCategory]=useState('');const [page,setPage]=useState(0);
 const [draft,setDraft]=useState<Record<string,string>>({});const [reason,setReason]=useState('');
 const load=useCallback(async()=>{const version=++sequence.current.version;setLoading(true);setError('');try{const result=await fetchRecommendations({scenario:activeScenario});if(version!==sequence.current.version)return;setRows(result);setPage(0);const requested=new URLSearchParams(window.location.search).get('sku');setSelectedId(prev=>result.some(r=>r.skuId===prev)?prev:result.find(r=>r.skuId===requested)?.skuId||result.find(r=>r.currentScenarioTotal>0)?.skuId||result[0]?.skuId||null);}catch(e){if(version===sequence.current.version){setRows([]);setSelectedId(null);setError(e instanceof Error?e.message:'Could not load recommendations.');}}finally{if(version===sequence.current.version)setLoading(false);}},[activeScenario]);
 useEffect(()=>{const token=sequence.current;setDraft({});setReason('');setRows([]);setSelectedId(null);setNotice('');void load();return()=>{token.version++;};},[load,activeSeason?.id]);
 const refresh=useCallback(()=>{setDraft({});setReason('');setNotice('Published data changed. Unsaved quantity edits were reset.');void load();},[load]);useDataRefresh(refresh);
 useEffect(()=>setPage(0),[search,status,category]);
 const articles=useMemo(()=>recommendationArticles(rows),[rows]);
 const filtered=useMemo(()=>filterRecommendationArticles(articles,search,status,category),[articles,search,status,category]);
 const selected=rows.find(r=>r.skuId===selectedId);const article=articles.find(a=>a.reference===selected?.skuId.split('|')[0]);
 const changed=Object.keys(draft).length>0;const valid=Object.values(draft).every(v=>v.trim()!==''&&Number.isFinite(Number(v))&&Number(v)>=0&&Number.isInteger(Number(v)));
 const draftTotal=selected?.sizeBreakdown.every(s=>draft[s.size]!==undefined||s.finalQty!==null)?selected.sizeBreakdown.reduce((n,s)=>n+(draft[s.size]!==undefined?Number(draft[s.size]):s.finalQty||0),0):null;
 const articleForecast=article?.colors.reduce((n,c)=>n+c.currentScenarioTotal,0)??0;
 const articleNet=article?completeQuantity(article.colors.flatMap(c=>c.sizeBreakdown.map(s=>s.recommended))):null;
 const articlePurchase=article?completeQuantity(article.colors.map(c=>c.skuId===selectedId&&changed?(valid?draftTotal:null):c.purchaseTotals[activeScenario])):null;
 function chooseColor(id:string){setSelectedId(id);setDraft({});setReason('');setNotice('');}
 const money=(n:number)=>new Intl.NumberFormat('en-GB',{style:'currency',currency:activeSeason?.currency||'EUR'}).format(n);
 async function action(kind:'save'|'reset'|'lock'){
  if(!selected)return;const [reference,color]=selected.skuId.split('|');setBusy(true);setError('');setNotice('');
  try{if(kind==='save')await updateRecommendation(reference,color,{sizeBreakdown:Object.entries(draft).map(([size,value])=>({size,finalQty:Number(value)})),reason:reason.trim(),draftVersion:selected.draftVersion,forecastRun:selected.forecastRun});
   else if(kind==='reset')await resetRecommendation(reference,color,activeScenario,selected.draftVersion,selected.forecastRun);
   else if(selected.locked)await unlockRecommendation(reference,color);else await lockRecommendation(reference,color);
   setDraft({});setReason('');await load();setNotice(kind==='save'?'Size quantities saved to the shared purchase draft for this scenario.':kind==='reset'?'Draft quantities reset to the forecast for this scenario.':'Lock updated. A lock prevents editing; it does not approve a purchase order.');
  }catch(e){setError(e instanceof Error?e.message:'Could not save changes.');}finally{setBusy(false);}
 }
 const targetMargin=activeSeason?.targetMargin;
 return <AppShell>
  <PageHeader eyebrow="Forecasting" title="SKU recommendations" description="Review demand forecasts and net purchase quantities by article, colour and size." actions={<ScenarioSwitcher/>}/>
  <Notice tone="info" role="note">Net purchase quantity covers outstanding deliveries plus forecast demand not yet booked, less available stock (Disponible) and eligible receipts within the planning period. À recevoir in Demand Projection shows the separate Joolan supplier balance across receipt dates. Missing inputs leave net purchasing unresolved. Saved draft quantities are shared with Budget Tracker and Order Validation; a new draft starts from rounded forecast units.</Notice>
  {error&&<Notice tone="danger"><span className="flex flex-wrap items-center justify-between gap-3"><span className="flex-[1_1_320px]">{error}</span><BrandButton variant="outline" size="sm" disabled={busy} onClick={()=>void load()}>Retry loading</BrandButton></span></Notice>}
  {notice&&<Notice tone="success">{notice}</Notice>}
  <div className="grid items-start gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
   <aside className="flex min-w-0 flex-col overflow-hidden rounded-3xl border border-line bg-card shadow-card">
    <div className="flex flex-col gap-2.5 border-b border-line p-4">
     <div className="relative flex items-center"><MagnifyingGlassIcon className="pointer-events-none absolute left-3.5 h-4 w-4 text-fg-3"/><TextField aria-label="Search recommendations" className="w-full pl-10" placeholder="Article, colour or name" value={search} onChange={e=>setSearch(e.target.value)}/></div>
     <div className="flex gap-2">
      <SelectField aria-label="Recommendation status" wrapperClassName="min-w-0 flex-1" className="h-[38px] rounded-[10px] pl-3 pr-[30px] text-xs" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All status</option>{['pending','adjusted','locked'].map(s=><option key={s}>{s}</option>)}</SelectField>
      <SelectField aria-label="Recommendation category" wrapperClassName="min-w-0 flex-1" className="h-[38px] rounded-[10px] pl-3 pr-[30px] text-xs" value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option>{Array.from(new Set(rows.map(r=>r.category))).sort().map(c=><option key={c}>{c}</option>)}</SelectField>
     </div>
     <span className="text-xs text-fg-3">{filtered.length} articles · {filtered.reduce((n,a)=>n+a.colors.length,0)} colours</span>
    </div>
    <div className="flex max-h-[600px] flex-col gap-1 overflow-auto p-2.5">
     {loading?<p role="status" className="p-4 text-sm text-fg-3">Loading recommendations…</p>:filtered.slice(page*50,(page+1)*50).map(a=>{const active=article?.reference===a.reference;return <button key={a.reference} type="button" disabled={busy||changed} aria-current={active||undefined}
      className={cn('flex w-full flex-col gap-2 rounded-2xl px-3.5 py-3 text-left text-fg-1 disabled:cursor-not-allowed disabled:opacity-60',active?'bg-brand-soft':'hover:bg-page')}
      onClick={()=>{if(!active)chooseColor((a.colors.find(c=>search.trim()&&c.skuId.toLowerCase().includes(search.trim().toLowerCase()))||a.colors[0]).skuId);}}>
      <span className="flex w-full justify-between gap-2"><span className={cn('font-mono text-[13px] font-bold',active&&'text-brand-800')}>{a.reference}</span><span className="text-[11px] text-fg-3">{a.colors.length} colours</span></span>
      <span className="text-[13px] font-semibold">{a.name}</span><span className="text-xs text-fg-3">{a.colors.map(c=>c.skuId.split('|')[1]).join(' · ')}</span><ActivityBadge activity={a.colors[0].activity}/>
      <span className={cn('flex w-full justify-between font-mono text-xs',active?'text-fg-2':'text-fg-3')}><span>Forecast {qty(a.colors.reduce((n,c)=>n+c.currentScenarioTotal,0))}</span><span>Buy {qty(active?articlePurchase:completeQuantity(a.colors.map(c=>c.purchaseTotals[activeScenario])))}</span></span>
     </button>;})}
     {!loading&&!filtered.length&&<p className="p-5 text-sm text-fg-3">No recommendations match these filters.</p>}
    </div>
    <div className="flex items-center justify-between border-t border-line px-3.5 py-3"><BrandButton size="sm" variant="outline" disabled={!page||loading||busy||changed} onClick={()=>setPage(p=>p-1)}>Previous</BrandButton><span className="text-xs text-fg-3">{page+1}/{Math.max(1,Math.ceil(filtered.length/50))}</span><BrandButton size="sm" variant="outline" disabled={loading||busy||changed||(page+1)*50>=filtered.length} onClick={()=>setPage(p=>p+1)}>Next</BrandButton></div>
   </aside>
   {selected&&article&&!loading?<div className="flex min-w-0 flex-col gap-5">
    <section className="flex flex-col gap-[22px] rounded-3xl border border-line bg-card p-5 shadow-card sm:p-7">
     <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1"><h2 className="break-words font-display text-[26px] font-extrabold tracking-[-0.02em]">{article.reference} · {article.name}</h2><p className="text-sm text-fg-3">{selected.category} · {article.colors.length} colours · {article.colors.reduce((n,c)=>n+c.sizeBreakdown.length,0)} size variants</p><p className="text-xs text-fg-3">{activeSeason?.name} · {activeScenario} scenario · all colours combined</p><ActivityBadge activity={selected.activity}/></div>
     </div>
     <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">{[['Article demand forecast',qty(articleForecast)],['Article net purchase',qty(articleNet)],['Article purchase plan',qty(articlePurchase)]].map(([title,value],i)=>{const plan=i===2;return <div key={title} className={cn('flex flex-col gap-1.5 rounded-[18px] p-[18px]',plan?'bg-brand shadow-brand':'bg-soft')}><span className={cn('text-[13px]',plan?'text-white':'text-fg-3')}>{title}</span><span className={cn('font-display text-[30px] font-bold',plan&&'text-white')}>{value}</span></div>;})}</div>
     <p className="text-xs leading-[1.55] text-fg-3">Model confidence is a model signal, not an accuracy percentage. Reorder and customer-specific demand components are not separately forecast by this model.</p>
    </section>
    <section className="flex flex-col gap-4 rounded-3xl border border-line bg-card p-5 shadow-card">
     <div><h3 className="text-lg font-bold">Colours in this article</h3><p className="text-[13px] text-fg-3">Select a colour to review its sizes. Save or discard edits before switching colours.</p></div>
     <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{article.colors.map(c=>{const active=c.skuId===selectedId;return <button key={c.skuId} type="button" aria-pressed={active} disabled={busy||changed} onClick={()=>chooseColor(c.skuId)} className={cn('flex flex-col gap-2 rounded-2xl border p-4 text-left disabled:cursor-not-allowed disabled:opacity-60',active?'border-brand bg-brand-soft':'border-line hover:bg-page')}><span className="flex items-center justify-between gap-2"><span className="text-sm font-bold">{c.skuId.split('|')[1]}</span>{c.locked&&<LockSimpleIcon aria-label="Locked colour"/>}</span><span className="text-xs text-fg-3">{c.sizeBreakdown.length} sizes · {c.status}</span><span className="flex justify-between gap-2 text-xs"><span>Forecast {qty(c.currentScenarioTotal)}</span><span>Buy {qty(active&&changed?(valid?draftTotal:null):c.purchaseTotals[activeScenario])}</span></span></button>;})}</div>
    </section>
    <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-card">
     <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-6 py-5"><div className="flex flex-col gap-1"><h3 className="text-lg font-bold">{selected.skuId.split('|')[1]} · Size quantities</h3><p className="text-[13px] text-fg-3">Forecast {qty(selected.currentScenarioTotal)} · purchase plan {qty(changed?(valid?draftTotal:null):selected.purchaseTotals[activeScenario])}. Edits apply only to this colour.</p></div><div className="flex items-center gap-2.5"><ConfidenceBadge level={selected.confidence as 'high'|'medium'|'low'}/><BrandButton variant="outline" size="sm" disabled={busy||changed} onClick={()=>void action('lock')}>{selected.locked?<LockSimpleOpenIcon/>:<LockSimpleIcon/>}{selected.locked?'Unlock colour':'Lock colour editing'}</BrandButton></div></div>
     <div className="overflow-x-auto"><div role="table" aria-label="Size quantities" className="min-w-[640px]">
      <div role="row" className={cn(SIZE_GRID,'bg-page px-6 py-3 text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3')}>{['Size','Historical booked units','Forecast','Suggested purchase','Purchase quantity'].map((h,i)=><span role="columnheader" key={h} className={cn(i>0&&'text-right')}>{h}</span>)}</div>
      {selected.sizeBreakdown.map(s=>{const edited=draft[s.size]!==undefined;return <div role="row" key={s.size} className={cn(SIZE_GRID,'items-center border-t border-line px-6 py-2.5',edited&&'bg-brand-50')}>
       <span role="cell" className="font-mono font-bold">{s.size}</span>
       <span role="cell" className="text-right font-mono text-fg-2">{qty(selected.historicalSizes[s.size]??null)}</span>
       <span role="cell" className="text-right font-mono">{qty(s.forecast)}</span>
       <span role="cell" className={cn('text-right font-mono',s.recommended==null?'text-brand-800':'text-fg-2')}>{qty(s.recommended)}</span>
       <div role="cell" className="flex flex-col items-end gap-1">
        <input aria-label={`${selected.skuId.split('|')[1]} purchase quantity size ${s.size}`} disabled={selected.locked||busy} type="number" min="0" step="1" placeholder="Unresolved" value={draft[s.size]??s.finalQty??''} onChange={e=>setDraft(v=>({...v,[s.size]:e.target.value}))}
         className={cn('h-10 w-[120px] rounded-xl border-[1.5px] bg-card px-3 text-right font-mono text-sm font-bold text-fg-1 outline-none [color-scheme:light_dark] placeholder:font-normal placeholder:text-fg-3 focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:cursor-not-allowed disabled:opacity-60',edited?'border-brand':'border-line')}/>
        {s.manualOverride!=null&&<span className="text-[10px] text-brand-800">Saved manual override</span>}
       </div>
      </div>;})}
     </div></div>
     <div className="flex flex-col gap-3 border-t border-line px-6 py-5">
      {changed&&<><TextField aria-label="Adjustment reason" placeholder="Why are you changing these quantities?" value={reason} onChange={e=>setReason(e.target.value)}/>{!valid&&<p className="text-xs text-danger">Enter nonnegative whole-unit quantities for every edited size.</p>}<p className="text-xs text-brand-800">Unsaved edits. Save or discard before selecting another article or colour, or locking this colour.</p></>}
      <div className="flex flex-wrap gap-2">
       <BrandButton disabled={!changed||!valid||!reason.trim()||selected.locked||busy} onClick={()=>void action('save')}><FloppyDiskIcon/>{busy?'Working…':'Save size quantities'}</BrandButton>
       {changed&&<BrandButton variant="outline" disabled={busy} onClick={()=>{setDraft({});setReason('');}}>Discard edits</BrandButton>}
       <BrandButton variant="outline" disabled={selected.locked||busy||changed||!selected.sizeBreakdown.some(s=>s.manualOverride!=null)} onClick={()=>void action('reset')}><ArrowCounterClockwiseIcon/>Reset saved overrides</BrandButton>
      </div>
     </div>
    </section>
    <section className="flex flex-col gap-3.5 rounded-3xl border border-line bg-card p-6 shadow-card">
     <h3 className="text-lg font-bold">{selected.skuId.split('|')[1]} · Financial impact</h3>
     {changed&&<p className="text-xs text-brand-800">Financial figures reflect saved quantities. Save your quantity changes to refresh them.</p>}
     {selected.financialImpact.complete===false?<p className="rounded-[14px] bg-brand-50 px-4 py-3.5 text-sm leading-[1.55] text-fg-1">Financial impact is unresolved: actual inventory, purchase costs or selling prices are missing. A quantity override does not resolve those inputs. <Link href="/budget" className="font-bold text-brand-700 underline hover:text-brand-800">Review budget inputs</Link>.</p>
     :<div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">{[['Purchase cost',money(selected.financialImpact.purchaseCost)],['Expected turnover',money(selected.financialImpact.expectedTurnover)],['Gross margin',money(selected.financialImpact.grossMargin)],['Margin / target',`${selected.financialImpact.marginPercent.toFixed(1)}% / ${activeSeason?.targetMargin??0}%`]].map(([title,value],i)=>{const tone=i===3&&targetMargin!=null?(selected.financialImpact.marginPercent<targetMargin?'text-brand-800':'text-success-600'):'';return <div key={title} className="flex flex-col gap-1.5 rounded-2xl bg-soft p-4"><span className="text-xs text-fg-3">{title}</span><span className={cn('font-display text-xl font-bold',tone)}>{value}</span></div>;})}</div>}
     <p className="text-xs leading-[1.55] text-fg-3">Saved draft turnover uses its quantity, selling price and sell-through assumptions. Before a draft is saved, turnover uses forecast demand. Recalculate in Budget Tracker after prices change. Locking does not validate financial readiness.</p>
    </section>
   </div>:<div className="rounded-3xl border border-line bg-card p-8 text-sm text-fg-3 shadow-card">{loading?'Preparing forecasts and purchase inputs…':'Select an article, then a colour to review its quantities.'}</div>}
  </div>
 </AppShell>;
}
