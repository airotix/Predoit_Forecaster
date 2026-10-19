"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowUpRight,RefreshCw,SlidersHorizontal} from 'lucide-react';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher} from '@/components/shared';
import {Button} from '@/components/ui/button';
import FinancialSettings from '@/components/budget/FinancialSettings';
import ArticlePlanner from '@/components/budget/ArticlePlanner';
import {useRouter} from 'next/navigation';
import {purchaseOrdersApi} from '@/lib/api/purchaseOrders';
import {updateBuyingEdit} from '@/lib/budgetEdits';
import {useSeasonStore} from '@/store/seasonStore';
import {useDataRefresh} from '@/hooks/useDataRefresh';
import {budgetApi,type BuyingSimulation,type BuyingEdit,type BuyingRow} from '@/lib/api/budget';

const label='text-xs font-medium uppercase tracking-wide text-slate-500';
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
 return <AppShell><div className="space-y-6 pb-16">
 <Link href="/budget/reconciliation" className="inline-flex items-center gap-2 text-sm font-medium text-blue-600">Resolve missing purchasing inputs <ArrowUpRight className="h-4 w-4"/></Link>
 <header className="flex flex-wrap items-start justify-between gap-4"><div><p className={label}>Seasonal purchasing</p><h1 className="mt-1 text-3xl font-semibold tracking-tight">Budget tracker</h1><p className="mt-2 text-sm text-slate-500">Plan forecast orders by article, compare margins and understand what fits your buying budget.</p></div><Button variant="outline" onClick={()=>setSettingsOpen(v=>!v)}><SlidersHorizontal className="mr-2 h-4 w-4"/>{settingsOpen?'Close settings':'Budget & price settings'}</Button></header>
 <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-4"><div><p className="font-medium">{report?.settings.brands.join(', ')||activeSeason?.name||'Loading season'}</p><p className="mt-1 text-xs text-slate-500">{report?`${report.settings.warehouses.join(', ')} · ${report.season.startDate} to ${report.season.endDate} · ${simulation?.currency}`:'Preparing Joolan data'}</p></div><ScenarioSwitcher/></div>
 {error&&<div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}<Button variant="outline" className="ml-3" onClick={()=>void load()}>Reload saved draft</Button></div>}
 {notice&&<p role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">{notice}</p>}
 {settingsOpen&&<section className="rounded-lg border bg-slate-50 p-4"><FinancialSettings/><Button className="mt-4" variant="outline" onClick={()=>{setSettingsOpen(false);setEdits({});void load();}}>Return to buying plan and refresh</Button></section>}
 {loading&&<p role="status" className="flex items-center gap-2 text-sm text-slate-500"><RefreshCw className="h-4 w-4 animate-spin"/>Loading saved prices and calculating the buying plan. The first load after starting the backend takes longer.</p>}
 {simulation&&report&&summary&&covered&&<>
 <div className="rounded-lg border p-4 text-sm"><p>{simulation.draft?.version?`Saved draft v${simulation.draft.version} · ${new Date(simulation.draft.updatedAt!).toLocaleString()}`:'New draft · save to keep your quantities, prices and selected articles'}</p><p className="mt-1 text-xs text-slate-500">{simulation.draft?.forecastRun&&`Forecast ${simulation.draft.forecastRun.slice(0,8)} · `}Separate draft for each scenario. Catalogue prices remain the defaults for new forecasts. <Link href="/purchase-orders" className="underline">Open supplier POs</Link></p></div>
 {simulation.draft?.stale&&<p role="alert" className="rounded-lg border border-amber-200 p-4 text-sm">Source prices or settings changed since this draft was saved. Saved draft prices are retained. Refresh catalogue defaults to adopt new automatic prices, or keep the saved assumptions and save a new version before validation. Explicit price edits are retained. {simulation.draft.excludedEdits>0?`${simulation.draft.excludedEdits} edits are outside the current scope and excluded.`:''}{simulation.draft.supplierPriceChanged?' A supplier price selection is no longer available; select it again.':''}{simulation.draft.currencyChanged?' Currency changed: previous currency price assumptions were removed; review the new currency prices.':''}</p>}
 {dirty&&<p role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">Unsaved draft changes. Save & recalculate to keep these edits and update the figures.</p>}
 <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[
 ['Buying budget',money(summary.budget),`Target gross margin ${percent(summary.targetMargin)}`],
 ['Priced supplier orders',money(covered.commitments),`${covered.supplierLines} source-backed lines in ${simulation.currency}`],
 ['Articles fitting draft budget',money(simulation.articlePlan.purchaseCost),`${simulation.articlePlan.articles.filter(a=>a.status==='included').length} whole articles · priced draft assumptions`],
 ['Remaining draft allowance',money(simulation.articlePlan.remaining),simulation.articlePlan.provisional?'Provisional · unresolved commitments excluded':'After known commitments and allocated articles'],
 ].map(([title,value,note],i)=><div key={title} className={`rounded-lg border p-5 ${i===3?'bg-slate-900 text-white':'bg-white'}`}><p className={`text-sm ${i===3?'text-slate-300':'text-slate-500'}`}>{title}</p><p className="mt-3 text-2xl font-semibold">{value}</p><p className={`mt-2 text-xs ${i===3?'text-slate-300':'text-slate-500'}`}>{note}</p></div>)}</section>
 {covered.balanceAfterCovered<0&&<p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">Included order values exceed the buying budget by {money(-covered.balanceAfterCovered)}.</p>}
 <details className="rounded-lg border bg-slate-50 p-4 text-sm text-slate-600"><summary className="cursor-pointer font-medium">What these totals cover</summary><p className="mt-3">The tracker includes {covered.supplierLines} priced supplier lines and draft articles with complete price assumptions that meet the margin target and fit the allowance. {covered.excludedSupplierLines} supplier lines are excluded from the commitment subtotal.</p><p className="mt-2">Excluded records are retained in the database. Missing values are not treated as zero. The balance only subtracts included amounts, so it is not spending approval for the whole season.</p></details>
 <ArticlePlanner simulation={simulation} edits={edits} onEdit={edit} disabled={loading||busy||saving} dirty={dirty} selected={selected} onSelect={(ids,checked)=>{setSelected(v=>checked?Array.from(new Set([...v,...ids])):v.filter(id=>!ids.includes(id)));setDirty(true);}}/>
 {selected.length>0&&<section aria-label="Selected articles financial review" className="rounded-xl border border-blue-200 bg-blue-50 p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">PO selection · {reviewArticles} selected articles · {reviewRows.length} variants</h2><Button variant="outline" onClick={()=>{setSelected([]);setDirty(true);}}>Clear selection</Button></div><p className="mt-2 text-sm">Articles: {Array.from(new Set(reviewRows.map(r=>r.reference))).join(', ')}. {dirty?'Recalculate to include your latest edits. The totals show the last calculation.':'These figures cover only your selection.'}</p><div className="mt-4 grid gap-4 sm:grid-cols-3">{[['Purchase cost',money(reviewTotal('orderCost'))],['Expected turnover',money(reviewTotal('orderTurnover'))],['Gross margin',money(reviewTotal('orderGrossMargin'))]].map(([title,value])=><div key={title}><p className="text-xs text-slate-600">{title}</p><p className="mt-1 font-semibold">{value}</p></div>)}</div>{reviewChecks.length>0&&<div className="mt-4 rounded border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-medium">These checks remain visible for final PO validation. They do not prevent draft creation:</p><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900">{reviewChecks.map(check=><li key={check}>{check}</li>)}</ul></div>}</section>}
 <footer className="sticky bottom-3 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-4"><div><p className="text-sm font-medium">{reviewArticles} articles selected for PO creation</p><p className="mt-1 text-xs text-slate-500">Save selected quantities → choose supplier and edit PO → validate and download final PO.</p></div><div className="flex flex-wrap gap-2"><Button variant="outline" disabled={loading||busy||saving||dirty||!simulation.draft?.version} onClick={()=>void saveDraft(true)}>Refresh catalogue defaults</Button><Button variant="outline" disabled={loading||busy||saving} onClick={()=>void saveDraft()}><RefreshCw className="mr-2 h-4 w-4"/>Save & recalculate draft</Button><Button disabled={loading||saving||!selected.length} onClick={()=>void createPOs()}>{saving?'Saving and preparing…':'Create PO from selected articles'}</Button></div></footer>
 <Link href="/purchase-orders" className="inline-flex items-center gap-2 rounded-lg border bg-white px-4 py-3 text-sm font-medium text-blue-600">Create supplier purchase orders from the saved draft <ArrowUpRight className="h-4 w-4"/></Link>
 <p className="text-xs text-slate-400">Joolan history through {report.source.historyThrough} · Inventory snapshot {report.source.inventoryAsOf?new Date(report.source.inventoryAsOf).toLocaleString():'unknown'} · <Link href="/setup" className="underline">Manage data connection <ArrowUpRight className="inline h-3 w-3"/></Link></p>
 </>}
 </div></AppShell>;
}
