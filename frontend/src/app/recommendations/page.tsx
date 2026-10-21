"use client";
// @refresh reset
import {useCallback,useEffect,useRef,useState} from 'react';
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
 const selected=rows.find(r=>r.skuId===selectedId);const filtered=rows.filter(r=>`${r.skuId} ${r.skuName}`.toLowerCase().includes(search.trim().toLowerCase())&&(!status||r.status===status)&&(!category||r.category===category));
 const changed=Object.keys(draft).length>0;const valid=Object.values(draft).every(v=>v.trim()!==''&&Number.isFinite(Number(v))&&Number(v)>=0&&Number.isInteger(Number(v)));
 const draftTotal=selected?.sizeBreakdown.every(s=>draft[s.size]!==undefined||s.finalQty!==null)?selected.sizeBreakdown.reduce((n,s)=>n+(draft[s.size]!==undefined?Number(draft[s.size]):s.finalQty||0),0):null;
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
  <Notice tone="info" role="note">Net purchase quantity = forecast demand less available inventory. Missing inventory leaves the quantity unresolved. Saved draft quantities are shared with Budget Tracker and Order Validation. A saved purchase draft starts from rounded forecast units; the net recommendation remains visible for comparison.</Notice>
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
     <span className="text-xs text-fg-3">{filtered.length} article / colour combinations</span>
    </div>
    <div className="flex max-h-[600px] flex-col gap-1 overflow-auto p-2.5">
     {loading?<p role="status" className="p-4 text-sm text-fg-3">Loading recommendations…</p>:filtered.slice(page*50,(page+1)*50).map(r=>{const active=selectedId===r.skuId;return <button key={r.skuId} type="button" disabled={busy||changed} aria-current={active||undefined}
      className={cn('flex w-full flex-col gap-2 rounded-2xl px-3.5 py-3 text-left text-fg-1 disabled:cursor-not-allowed disabled:opacity-60',active?'bg-brand-soft':'hover:bg-page')}
      onClick={()=>{setSelectedId(r.skuId);setDraft({});setReason('');setNotice('');}}>
      <span className="flex w-full justify-between gap-2"><span className={cn('font-mono text-[13px] font-bold',active&&'text-brand-800')}>{r.skuId.split('|')[0]}</span><span className={cn('flex items-center gap-1 text-[11px]',active?'font-bold text-brand-800':'text-fg-3')}>{r.locked&&<LockSimpleIcon weight="fill" aria-hidden className="h-[11px] w-[11px]"/>}{r.status}</span></span>
      <span className={cn('text-[13px]',active?'text-fg-2':'text-fg-3')}>{r.skuId.split('|')[1]}</span>
      <span className={cn('flex w-full justify-between font-mono text-xs',active?'text-fg-2':'text-fg-3')}><span>Forecast {qty(r.currentScenarioTotal)}</span><span>Buy {qty(r.purchaseTotals[activeScenario])}</span></span>
     </button>;})}
     {!loading&&!filtered.length&&<p className="p-5 text-sm text-fg-3">No recommendations match these filters.</p>}
    </div>
    <div className="flex items-center justify-between border-t border-line px-3.5 py-3"><BrandButton size="sm" variant="outline" disabled={!page||loading} onClick={()=>setPage(p=>p-1)}>Previous</BrandButton><span className="text-xs text-fg-3">{page+1}/{Math.max(1,Math.ceil(filtered.length/50))}</span><BrandButton size="sm" variant="outline" disabled={loading||(page+1)*50>=filtered.length} onClick={()=>setPage(p=>p+1)}>Next</BrandButton></div>
   </aside>
   {selected&&!loading?<div className="flex min-w-0 flex-col gap-5">
    <section className="flex flex-col gap-[22px] rounded-3xl border border-line bg-card p-5 shadow-card sm:p-7">
     <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1"><h2 className="break-words font-display text-[26px] font-extrabold tracking-[-0.02em]">{selected.skuId.split('|')[0]} · {selected.skuId.split('|')[1]}</h2><p className="text-sm text-fg-3">{selected.skuName} · {selected.category}</p><p className="text-xs text-fg-3">{activeSeason?.name} · {activeScenario} scenario</p></div>
      <div className="flex items-center gap-2.5"><ConfidenceBadge level={selected.confidence as 'high'|'medium'|'low'}/><BrandButton variant="outline" size="sm" disabled={busy||changed} onClick={()=>void action('lock')}>{selected.locked?<LockSimpleOpenIcon/>:<LockSimpleIcon/>}{selected.locked?'Unlock':'Lock editing'}</BrandButton></div>
     </div>
     <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">{[['Demand forecast',qty(selected.currentScenarioTotal)],['Suggested net purchase',qty(selected.sizeBreakdown.every(s=>s.recommended!==null)?selected.sizeBreakdown.reduce((n,s)=>n+(s.recommended||0),0):null)],['Current purchase plan',qty(changed&&valid?draftTotal:selected.purchaseTotals[activeScenario])]].map(([title,value],i)=>{const plan=i===2;return <div key={title} className={cn('flex flex-col gap-1.5 rounded-[18px] p-[18px]',plan?'bg-brand shadow-brand':'bg-soft')}><span className={cn('text-[13px]',plan?'text-white':'text-fg-3')}>{title}</span><span className={cn('font-display text-[30px] font-bold',plan&&'text-white')}>{value}</span></div>;})}</div>
     <p className="text-xs leading-[1.55] text-fg-3">Model confidence is a model signal, not an accuracy percentage. Reorder and customer-specific demand components are not separately forecast by this model.</p>
    </section>
    <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-card">
     <div className="flex flex-col gap-1 border-b border-line px-6 py-5"><h3 className="text-lg font-bold">Size quantities</h3><p className="text-[13px] text-fg-3">Real historical demand and the selected forecast. Edit individual purchase quantities below.</p></div>
     <div className="overflow-x-auto"><div role="table" aria-label="Size quantities" className="min-w-[640px]">
      <div role="row" className={cn(SIZE_GRID,'bg-page px-6 py-3 text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3')}>{['Size','Historical booked units','Forecast','Suggested purchase','Purchase quantity'].map((h,i)=><span role="columnheader" key={h} className={cn(i>0&&'text-right')}>{h}</span>)}</div>
      {selected.sizeBreakdown.map(s=>{const edited=draft[s.size]!==undefined;return <div role="row" key={s.size} className={cn(SIZE_GRID,'items-center border-t border-line px-6 py-2.5',edited&&'bg-brand-50')}>
       <span role="cell" className="font-mono font-bold">{s.size}</span>
       <span role="cell" className="text-right font-mono text-fg-2">{qty(selected.historicalSizes[s.size]??null)}</span>
       <span role="cell" className="text-right font-mono">{qty(s.forecast)}</span>
       <span role="cell" className={cn('text-right font-mono',s.recommended==null?'text-brand-800':'text-fg-2')}>{qty(s.recommended)}</span>
       <div role="cell" className="flex flex-col items-end gap-1">
        <input aria-label={`Purchase quantity size ${s.size}`} disabled={selected.locked||busy} type="number" min="0" step="1" placeholder="Unresolved" value={draft[s.size]??s.finalQty??''} onChange={e=>setDraft(v=>({...v,[s.size]:e.target.value}))}
         className={cn('h-10 w-[120px] rounded-xl border-[1.5px] bg-card px-3 text-right font-mono text-sm font-bold text-fg-1 outline-none [color-scheme:light_dark] placeholder:font-normal placeholder:text-fg-3 focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:cursor-not-allowed disabled:opacity-60',edited?'border-brand':'border-line')}/>
        {s.manualOverride!=null&&<span className="text-[10px] text-brand-800">Saved manual override</span>}
       </div>
      </div>;})}
     </div></div>
     <div className="flex flex-col gap-3 border-t border-line px-6 py-5">
      {changed&&<><TextField aria-label="Adjustment reason" placeholder="Why are you changing these quantities?" value={reason} onChange={e=>setReason(e.target.value)}/>{!valid&&<p className="text-xs text-danger">Enter nonnegative whole-unit quantities for every edited size.</p>}<p className="text-xs text-brand-800">Unsaved edits. Save or discard before selecting another SKU or locking it.</p></>}
      <div className="flex flex-wrap gap-2">
       <BrandButton disabled={!changed||!valid||!reason.trim()||selected.locked||busy} onClick={()=>void action('save')}><FloppyDiskIcon/>{busy?'Working…':'Save size quantities'}</BrandButton>
       {changed&&<BrandButton variant="outline" disabled={busy} onClick={()=>{setDraft({});setReason('');}}>Discard edits</BrandButton>}
       <BrandButton variant="outline" disabled={selected.locked||busy||changed||!selected.sizeBreakdown.some(s=>s.manualOverride!=null)} onClick={()=>void action('reset')}><ArrowCounterClockwiseIcon/>Reset saved overrides</BrandButton>
      </div>
     </div>
    </section>
    <section className="flex flex-col gap-3.5 rounded-3xl border border-line bg-card p-6 shadow-card">
     <h3 className="text-lg font-bold">Financial impact</h3>
     {selected.financialImpact.complete===false?<p className="rounded-[14px] bg-brand-50 px-4 py-3.5 text-sm leading-[1.55] text-fg-1">Financial impact is unresolved: actual inventory, purchase costs or selling prices are missing. A quantity override does not resolve those inputs. <Link href="/budget" className="font-bold text-brand-700 underline hover:text-brand-800">Review budget inputs</Link>.</p>
     :<div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">{[['Purchase cost',money(selected.financialImpact.purchaseCost)],['Expected turnover',money(selected.financialImpact.expectedTurnover)],['Gross margin',money(selected.financialImpact.grossMargin)],['Margin / target',`${selected.financialImpact.marginPercent.toFixed(1)}% / ${activeSeason?.targetMargin??0}%`]].map(([title,value],i)=>{const tone=i===3&&targetMargin!=null?(selected.financialImpact.marginPercent<targetMargin?'text-brand-800':'text-success-600'):'';return <div key={title} className="flex flex-col gap-1.5 rounded-2xl bg-soft p-4"><span className="text-xs text-fg-3">{title}</span><span className={cn('font-display text-xl font-bold',tone)}>{value}</span></div>;})}</div>}
     <p className="text-xs leading-[1.55] text-fg-3">Saved draft turnover uses its quantity, selling price and sell-through assumptions. Before a draft is saved, turnover uses forecast demand. Recalculate in Budget Tracker after prices change. Locking does not validate financial readiness.</p>
    </section>
   </div>:<div className="rounded-3xl border border-line bg-card p-8 text-sm text-fg-3 shadow-card">{loading?'Preparing forecasts and purchase inputs…':'Select an article / colour combination to review its quantities.'}</div>}
  </div>
 </AppShell>;
}
