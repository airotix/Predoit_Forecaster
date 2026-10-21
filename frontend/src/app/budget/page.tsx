"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowUpRightIcon,ArrowsClockwiseIcon,CaretDownIcon,FloppyDiskIcon,InfoIcon,PencilSimpleIcon,SlidersHorizontalIcon,StorefrontIcon,WarningIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher} from '@/components/shared';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader} from '@/components/ui/brand';
import FinancialSettings from '@/components/budget/FinancialSettings';
import ArticlePlanner from '@/components/budget/ArticlePlanner';
import {useRouter} from 'next/navigation';
import {purchaseOrdersApi} from '@/lib/api/purchaseOrders';
import {updateBuyingEdit} from '@/lib/budgetEdits';
import {useSeasonStore} from '@/store/seasonStore';
import {useDataRefresh} from '@/hooks/useDataRefresh';
import {budgetApi,type BuyingSimulation,type BuyingEdit,type BuyingRow} from '@/lib/api/budget';

/** Share of the buying budget, clamped to 0-100 for the allowance bar. */
const share=(value:number,budget:number)=>budget>0&&Number.isFinite(value)?Math.min(100,Math.max(0,value/budget*100)):0;
export default function BuyingPlan(){
 const {activeScenario,activeSeason}=useSeasonStore();const router=useRouter();
 const [simulation,setSimulation]=useState<BuyingSimulation|null>(null);const [edits,setEdits]=useState<Record<string,BuyingEdit>>({});
 const [selected,setSelected]=useState<string[]>([]);const [saving,setSaving]=useState(false);
 const [loading,setLoading]=useState(true);const busy=false;const [dirty,setDirty]=useState(false);
 const [error,setError]=useState('');const [notice,setNotice]=useState('');const [settingsOpen,setSettingsOpen]=useState(false);
 const sequence=useRef({version:0});
 const load=useCallback(async()=>{const version=++sequence.current.version;setLoading(true);setError('');
  try{const v=await budgetApi.draft(activeScenario);if(version!==sequence.current.version)return;setSimulation(v);setSelected(v.draft?.selected||[]);setEdits(Object.fromEntries((v.draft?.edits||[]).map(e=>[e.id,e])));setDirty(false);}
  catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Could not calculate the buying plan.');}
  finally{if(version===sequence.current.version){setLoading(false);setNotice('');}}
 },[activeScenario]);
 useEffect(()=>{const token=sequence.current;setSaving(false);setEdits({});setSelected([]);setNotice('');setSimulation(null);void load();return()=>{token.version++;};},[load,activeSeason?.id]);
 const refresh=useCallback(()=>{if(dirty){setNotice('Published data changed while you were editing. Reload the saved draft before saving; your unsaved changes are still shown.');return;}setNotice('Loading the saved draft for the published forecast. Earlier drafts stay in the database.');void load();},[load,dirty]);useDataRefresh(refresh,true);
 useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
 async function saveDraft(refreshPrices=false){if(!simulation)return;const version=sequence.current.version;setSaving(true);setError('');try{const result=await budgetApi.saveDraft(simulation,Object.values(edits),selected,refreshPrices);if(version!==sequence.current.version)return;setSimulation(result);setEdits(Object.fromEntries((result.draft?.edits||[]).map(e=>[e.id,e])));setDirty(false);setNotice(`Draft version ${result.draft?.version} saved. Recommendations and Order Validation now use this plan.`);}catch(e){setError(e instanceof Error?e.message:'Could not save draft.');}finally{if(version===sequence.current.version)setSaving(false);}}
 const money=(v:number|null|undefined)=>v==null?'—':new Intl.NumberFormat('en-GB',{style:'currency',currency:simulation?.currency||'EUR'}).format(v);
 const percent=(v:number|null|undefined)=>v==null?'—':`${v.toFixed(1)}%`;
 const report=simulation?.context;const summary=simulation?.summary;const covered=simulation?.covered;
 function edit(row:BuyingRow,name:keyof BuyingEdit,value:string){if(name==='sellThrough'&&value.trim()==='')return;setEdits(prev=>({...prev,[row.id]:updateBuyingEdit(prev[row.id],row,name,value)}));setDirty(true);}
 const reviewRows=simulation?.rows.filter(r=>selected.includes(r.id))||[];
 const reviewArticles=new Set(reviewRows.map(r=>r.reference)).size;
 const reviewChecks=Array.from(new Set(reviewRows.flatMap(r=>r.blockers).filter(check=>check!=='Select a Joolan supplier price'&&check!=='Price assumptions are simulation only')));
 const reviewTotal=(key:'orderCost'|'orderTurnover'|'orderGrossMargin')=>reviewRows.length&&reviewRows.every(r=>r[key]!=null)?reviewRows.reduce((n,r)=>n+(r[key]||0),0):null;
 async function createPOs(){
  if(!simulation||!selected.length)return;const version=sequence.current.version;setSaving(true);setError('');
  try{
   const saved=await budgetApi.saveDraft(simulation,Object.values(edits),selected);
   if(version!==sequence.current.version)return;
   setSimulation(saved);setDirty(false);setEdits(Object.fromEntries((saved.draft?.edits||[]).map(e=>[e.id,e])));
   const result=await purchaseOrdersApi.create(saved,'selected');
   if(version!==sequence.current.version)return;
   const id=result.created[0]||result.existing[0];
   if(id)router.push(`/purchase-orders?po=${encodeURIComponent(id)}`);
   else setNotice(result.notice);
  }catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Could not create PO drafts.');}
  finally{if(version===sequence.current.version)setSaving(false);}
 }
 const commitW=summary&&covered?share(covered.commitments,summary.budget):0;
 const allocW=summary&&simulation?Math.min(100-commitW,share(simulation.articlePlan.purchaseCost,summary.budget)):0;
 return <AppShell>
 <Link href="/budget/reconciliation" className="flex items-center gap-1.5 self-start text-sm font-bold text-brand-700 hover:text-brand-800">Resolve missing purchasing inputs<ArrowUpRightIcon className="h-4 w-4"/></Link>
 <PageHeader eyebrow="Seasonal purchasing" title="Budget tracker" description="Plan forecast orders by article, compare margins and understand what fits your buying budget."
  actions={<BrandButton variant="outline" onClick={()=>setSettingsOpen(v=>!v)}><SlidersHorizontalIcon/>{settingsOpen?'Close settings':'Budget & price settings'}</BrandButton>}/>
 <div className="flex flex-wrap items-center justify-between gap-3.5 rounded-[20px] border border-line bg-card py-3.5 pl-5 pr-4">
  <div className="flex min-w-0 items-center gap-3.5"><span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] bg-champagne"><StorefrontIcon className="h-[21px] w-[21px] text-brand-700"/></span><div className="flex min-w-0 flex-col gap-0.5"><p className="text-[15px] font-bold">{report?.settings.brands.join(', ')||activeSeason?.name||'Loading season'}</p><p className="text-[13px] text-fg-3">{report?`${report.settings.warehouses.join(', ')} · ${report.season.startDate} to ${report.season.endDate} · ${simulation?.currency}`:'Preparing Joolan data'}</p></div></div>
  <ScenarioSwitcher/>
 </div>
 {error&&<Notice tone="danger"><span className="flex flex-wrap items-center justify-between gap-3"><span className="flex-[1_1_320px]">{error}</span><BrandButton size="sm" variant="outline" onClick={()=>void load()}>Reload saved draft</BrandButton></span></Notice>}
 {notice&&<Notice tone="success">{notice}</Notice>}
 {settingsOpen&&<section className="flex flex-col gap-5 rounded-[32px] border border-line bg-card p-6 shadow-card sm:px-8 sm:py-7"><FinancialSettings/><div><BrandButton variant="outline" onClick={()=>{setSettingsOpen(false);setEdits({});void load();}}><ArrowsClockwiseIcon/>Return to buying plan and refresh</BrandButton></div></section>}
 {loading&&<p role="status" className="flex items-center gap-2.5 text-sm text-fg-3"><ArrowsClockwiseIcon className="h-4 w-4 shrink-0 animate-spin text-brand"/>Loading saved prices and calculating the buying plan. The first load after starting the backend takes longer.</p>}
 {simulation&&report&&summary&&covered&&<>
 <div className="flex flex-wrap items-start gap-3 rounded-2xl border border-line bg-card px-[18px] py-3.5">
  <FloppyDiskIcon weight="fill" className="mt-0.5 h-[18px] w-[18px] shrink-0 text-plum-600"/>
  <div className="flex min-w-0 flex-1 flex-col gap-0.5 text-sm"><p className="font-bold">{simulation.draft?.version?`Saved draft v${simulation.draft.version} · ${new Date(simulation.draft.updatedAt!).toLocaleString()}`:'New draft · save to keep your quantities, prices and selected articles'}</p><p className="text-xs text-fg-3">{simulation.draft?.forecastRun&&`Forecast ${simulation.draft.forecastRun.slice(0,8)} · `}Separate draft for each scenario. Catalogue prices remain the defaults for new forecasts. <Link href="/purchase-orders" className="font-bold text-brand-700 hover:text-brand-800">Open supplier POs</Link></p></div>
 </div>
 {simulation.draft?.stale&&<Notice tone="brand" icon={WarningIcon} role="alert">Source prices or settings changed since this draft was saved. Saved draft prices are retained. Refresh catalogue defaults to adopt new automatic prices, or keep the saved assumptions and save a new version before validation. Explicit price edits are retained. {simulation.draft.excludedEdits>0?`${simulation.draft.excludedEdits} edits are outside the current scope and excluded.`:''}{simulation.draft.supplierPriceChanged?' A supplier price selection is no longer available; select it again.':''}{simulation.draft.currencyChanged?' Currency changed: previous currency price assumptions were removed; review the new currency prices.':''}</Notice>}
 {dirty&&<Notice tone="brand" icon={PencilSimpleIcon} className="items-center rounded-[14px] px-4 py-3">Unsaved draft changes. Save &amp; recalculate to keep these edits and update the figures.</Notice>}
 <div className="flex flex-wrap gap-5">
  <section className="relative flex flex-[2_1_520px] flex-col justify-between gap-6 overflow-hidden rounded-[32px] bg-[#1A1A1A] p-6 text-white dark:border dark:border-line sm:p-8">
   <span aria-hidden className="absolute -right-[100px] -top-[100px] h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(245,130,32,0.35),rgba(245,130,32,0)_70%)]"/>
   <div className="relative flex flex-wrap justify-between gap-4">
    <div className="flex flex-col gap-1.5"><span className="text-sm text-white/70">Remaining draft allowance</span><span className="font-display text-[44px] font-bold leading-none tracking-[-0.03em] sm:text-[64px]">{money(simulation.articlePlan.remaining)}</span><span className="text-sm text-white/70">{simulation.articlePlan.provisional?'Provisional · unresolved commitments excluded':'After known commitments and allocated articles'}</span></div>
    <div className="flex flex-col gap-1.5 sm:items-end"><span className="text-[13px] text-white/70">Buying budget</span><span className="font-display text-[28px] font-bold text-brand-tile">{money(summary.budget)}</span><span className="text-[13px] text-white/70">Target gross margin {percent(summary.targetMargin)}</span></div>
   </div>
   <div className="relative flex flex-col gap-2.5">
    <div aria-hidden className="flex h-3.5 gap-0.5 overflow-hidden rounded-full bg-white/[0.12]"><div className="bg-brand-tile" style={{width:`${commitW}%`}}/><div className="bg-brand" style={{width:`${allocW}%`}}/></div>
    <div className="flex flex-wrap gap-[18px] text-xs text-white/80"><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-brand-tile"/>Priced supplier orders</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-brand"/>Articles fitting draft budget</span><span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-white/25"/>Remaining</span></div>
   </div>
  </section>
  <div className="flex flex-[1_1_300px] flex-col gap-4">
   {[
    ['Priced supplier orders',money(covered.commitments),`${covered.supplierLines} source-backed lines in ${simulation.currency}`],
    ['Articles fitting draft budget',money(simulation.articlePlan.purchaseCost),`${simulation.articlePlan.articles.filter(a=>a.status==='included').length} whole articles · priced draft assumptions`],
   ].map(([title,value,note])=><section key={title} className="flex flex-1 flex-col gap-1.5 rounded-3xl border border-line bg-card p-[22px] shadow-card"><span className="text-[13px] font-semibold text-fg-2">{title}</span><span className="font-display text-[30px] font-bold">{value}</span><span className="text-[13px] text-fg-3">{note}</span></section>)}
  </div>
 </div>
 {covered.balanceAfterCovered<0&&<Notice tone="danger" icon={WarningIcon}>Included order values exceed the buying budget by {money(-covered.balanceAfterCovered)}.</Notice>}
 <details className="group/cover rounded-2xl border-[1.5px] border-dashed border-line px-[18px]"><summary className="flex cursor-pointer list-none items-center gap-2.5 py-3.5 text-[13px] font-semibold text-fg-2 [&::-webkit-details-marker]:hidden"><InfoIcon className="h-4 w-4 text-plum-600"/>What these totals cover<CaretDownIcon weight="bold" className="ml-auto h-3 w-3 transition-transform group-open/cover:rotate-180"/></summary><div className="flex flex-col gap-2 pb-4 text-[13px] leading-[1.65] text-fg-2"><p>The tracker includes {covered.supplierLines} priced supplier lines and draft articles with complete price assumptions that meet the margin target and fit the allowance. {covered.excludedSupplierLines} supplier lines are excluded from the commitment subtotal.</p><p>Excluded records are retained in the database. Missing values are not treated as zero. The balance only subtracts included amounts, so it is not spending approval for the whole season.</p></div></details>
 <ArticlePlanner simulation={simulation} edits={edits} onEdit={edit} disabled={loading||busy||saving} dirty={dirty} selected={selected} onSelect={(ids,checked)=>{setSelected(v=>checked?Array.from(new Set([...v,...ids])):v.filter(id=>!ids.includes(id)));setDirty(true);}}/>
 {selected.length>0&&<section aria-label="Selected articles financial review" className="flex flex-col gap-4 rounded-3xl bg-plum-50 px-6 py-[22px]">
  <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-base font-bold">PO selection · {reviewArticles} selected articles · {reviewRows.length} variants</h2><BrandButton size="sm" variant="outline" onClick={()=>{setSelected([]);setDirty(true);}}>Clear selection</BrandButton></div>
  <p className="text-[13px] leading-[1.55] text-fg-2">Articles: <span className="font-mono text-plum-600">{Array.from(new Set(reviewRows.map(r=>r.reference))).join(', ')}</span>. {dirty?'Recalculate to include your latest edits. The totals show the last calculation.':'These figures cover only your selection.'}</p>
  <div className="flex flex-wrap gap-8">{[['Purchase cost',money(reviewTotal('orderCost'))],['Expected turnover',money(reviewTotal('orderTurnover'))],['Gross margin',money(reviewTotal('orderGrossMargin'))]].map(([title,value])=><div key={title} className="flex flex-col gap-0.5"><p className="text-xs text-plum-600">{title}</p><p className="font-display text-[22px] font-bold">{value}</p></div>)}</div>
  {reviewChecks.length>0&&<div className="rounded-[14px] border border-brand-200 bg-brand-50 px-4 py-3.5 text-[13px] leading-[1.55]"><p className="font-bold">These checks remain visible for final PO validation. They do not prevent draft creation:</p><ul className="mt-2 list-disc space-y-1 pl-5">{reviewChecks.map(check=><li key={check}>{check}</li>)}</ul></div>}
 </section>}
 <footer className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-line bg-card py-3.5 pl-[22px] pr-4 shadow-lift">
  <div className="flex flex-col gap-0.5"><p className="text-sm font-bold"><span className="font-display text-lg">{reviewArticles}</span> articles selected for PO creation</p><p className="text-xs text-fg-3">Save selected quantities → choose supplier and edit PO → validate and download final PO.</p></div>
  <div className="flex flex-wrap gap-2"><BrandButton variant="outline" disabled={loading||busy||saving||dirty||!simulation.draft?.version} onClick={()=>void saveDraft(true)}>Refresh catalogue defaults</BrandButton><BrandButton variant="outline" disabled={loading||busy||saving} onClick={()=>void saveDraft()}><ArrowsClockwiseIcon className={saving?'animate-spin':''}/>Save &amp; recalculate draft</BrandButton><BrandButton disabled={loading||saving||!selected.length} onClick={()=>void createPOs()}>{saving?'Saving and preparing…':'Create PO from selected articles'}</BrandButton></div>
 </footer>
 <Link href="/purchase-orders" className="flex items-center gap-2 self-start rounded-2xl border border-line bg-card px-[18px] py-3.5 text-sm font-bold text-brand-700 hover:border-brand-200">Create supplier purchase orders from the saved draft<ArrowUpRightIcon className="h-4 w-4"/></Link>
 <p className="text-xs text-fg-3">Joolan history through {report.source.historyThrough} · Inventory snapshot {report.source.inventoryAsOf?new Date(report.source.inventoryAsOf).toLocaleString():'unknown'} · <Link href="/setup" className="inline-flex items-center gap-0.5 font-semibold text-brand-700 hover:text-brand-800">Manage data connection<ArrowUpRightIcon className="h-3 w-3"/></Link></p>
 </>}
 </AppShell>;
}
