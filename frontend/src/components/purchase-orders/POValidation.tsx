"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowsClockwiseIcon,CaretDownIcon,CheckIcon,ClipboardTextIcon,DownloadSimpleIcon,InfoIcon,NotePencilIcon,PrinterIcon,SealCheckIcon,ShieldCheckIcon,WarningIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher} from '@/components/shared';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,SelectField,TextField} from '@/components/ui/brand';
import {useSeasonStore} from '@/store/seasonStore';
import {purchaseOrdersApi,downloadPO,type POSummary,type POValidation} from '@/lib/api/purchaseOrders';
import {cn} from '@/lib/utils';

const inputLabel='flex flex-col gap-2 text-[13px] font-semibold text-fg-2';
const cell='px-[5px] py-2.5 first:pl-5 last:pr-5';

export default function PurchaseOrderValidation(){
 const {activeSeason,activeScenario}=useSeasonStore();const seasonId=activeSeason?.id;
 const [orders,setOrders]=useState<POSummary[]>([]),[data,setData]=useState<POValidation|null>(null);
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const [reviewer,setReviewer]=useState(''),[reason,setReason]=useState(''),[confirmed,setConfirmed]=useState(false);
 const sequence=useRef({version:0});
 const load=useCallback(async(id?:string)=>{
  const version=++sequence.current.version;setLoading(true);setError('');setData(null);setConfirmed(false);setReason('');setReviewer('');
  if(!seasonId){setOrders([]);setLoading(false);return;}
  try{
   const result=await purchaseOrdersApi.list(seasonId,activeScenario);if(version!==sequence.current.version)return;
   const available=result.orders.filter(o=>o.status!=='cancelled');setOrders(available);
   const requested=id||new URLSearchParams(window.location.search).get('po');
   const selected=available.find(o=>o.id===requested)||available.find(o=>o.status==='pending_validation')||available.find(o=>o.status==='validated');
   if(selected){const review=await purchaseOrdersApi.validation(selected.id);if(version===sequence.current.version)setData(review);}
  }catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Could not load PO validation.');}
  finally{if(version===sequence.current.version)setLoading(false);}
 },[seasonId,activeScenario]);
 useEffect(()=>{const token=sequence.current;void load();return()=>{token.version++;};},[load]);
 async function finalize(){
  if(!data)return;setSaving(true);setError('');const version=sequence.current.version;
  try{const doc=await purchaseOrdersApi.validate(data.order.id,data.order.version,reviewer,reason,confirmed);if(version===sequence.current.version)await load(doc.id);}
  catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Final validation failed.');}
  finally{setSaving(false);}
 }
 async function download(){if(!data)return;setError('');try{const file=await purchaseOrdersApi.finalExport(data.order.id);downloadPO(file.filename,file.csv);}catch(e){setError(e instanceof Error?e.message:'Could not download the final PO.');}}
 const order=data?.order,final=order?.status==='validated';
 const money=(value:number|null|undefined)=>value==null?'Unknown':new Intl.NumberFormat('en-GB',{style:'currency',currency:order?.currency||'EUR'}).format(value);
 const references=Array.from(new Set(order?.lines.map(line=>line.reference)||[]));
 const remaining=data?data.budget.remaining??data.budget.provisionalRemaining:null;
 return <AppShell>
  <PageHeader eyebrow="Buying · final review" title="Order Validation" description="Budget selection → supplier PO → final validation and download." actions={<ScenarioSwitcher/>}/>
  <div className="flex flex-wrap items-end gap-2.5 rounded-3xl border border-line bg-card px-[22px] py-5 shadow-card">
   <label className={cn(inputLabel,'flex-[1_1_320px]')}>Supplier purchase order<SelectField strong aria-label="Purchase order to validate" wrapperClassName="w-full" className="h-12 rounded-[14px]" disabled={loading||saving} value={order?.id||''} onChange={e=>void load(e.target.value)}><option value="">Choose a saved PO</option>{orders.map(o=><option key={o.id} value={o.id}>{o.number} · {o.supplier||'Supplier needed'} · {o.status.replace('_',' ')}</option>)}</SelectField></label>
   <BrandButton variant="outline" disabled={loading||saving} onClick={()=>void load(order?.id)}><ArrowsClockwiseIcon className={loading?'animate-spin':''}/>Refresh checks</BrandButton>
   <BrandButton asChild variant="outline"><Link href="/purchase-orders"><NotePencilIcon/>Open PO editor</Link></BrandButton>
  </div>
  {loading&&<p role="status" className="flex items-center gap-2 text-sm text-fg-3"><ArrowsClockwiseIcon className="h-4 w-4 animate-spin"/>Checking the PO against current prices, supply and the buying budget…</p>}
  {error&&<Notice tone="danger">{error}</Notice>}
  {!loading&&!data&&!error&&<p className="rounded-3xl border-[1.5px] border-dashed border-line p-8 text-sm leading-relaxed text-fg-3">Create a PO from selected Budget Tracker articles, choose its supplier, then use “Save & send to Order Validation” in the PO editor.</p>}
  {data&&order&&<>
   <div className="flex flex-wrap gap-5">
    <section className="relative flex flex-[2_1_560px] flex-col gap-[22px] overflow-hidden rounded-[32px] bg-champagne p-6 sm:px-8 sm:py-[30px]">
     <span aria-hidden className="absolute -right-20 -top-[90px] h-[300px] w-[300px] rounded-full bg-[radial-gradient(circle,var(--glow),rgba(245,130,32,0)_70%)]"/>
     <div className="relative flex flex-wrap justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1.5"><h2 className="text-2xl font-extrabold tracking-[-0.02em]"><span className="font-mono">{order.number}</span> · {order.supplier||'Supplier not selected'}</h2><p className="text-sm text-fg-2">{final?'Validated locally · final PO available':order.status==='pending_validation'?'Awaiting final validation':'Draft · send from the PO editor'} · v{order.version} · {order.totals.units??'Unknown'} units · {order.totals.articles} articles</p></div>
      <Link href={`/purchase-orders?po=${order.id}`} className="self-start text-sm font-bold text-brand-800 underline hover:text-brand-700">{final?'View PO':'Edit supplier, quantities or prices'}</Link>
     </div>
     <div className="relative grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">{[['PO purchase cost',money(order.totals.purchaseCost)],['Expected turnover',money(order.totals.turnover)],['Gross margin',money(order.totals.grossMargin)],['Margin rate',order.totals.marginRate==null?'Unknown':`${order.totals.marginRate.toFixed(1)}%`]].map(([title,value])=><div key={title} className="flex flex-col gap-1 rounded-[18px] bg-card p-4"><p className="text-xs text-fg-3">{title}</p><p className="font-display text-[22px] font-bold tracking-[-0.01em]">{value}</p></div>)}</div>
    </section>
    <section className="flex flex-[1_1_320px] flex-col gap-2.5 rounded-3xl border border-line bg-card p-6 text-sm leading-[1.55] shadow-card">
     <h2 className="text-base font-bold">Buying budget check · {data.budget.currency}</h2>
     <p className="text-fg-2">Season budget {money(data.budget.amount)} · target margin {data.budget.targetMargin}%.</p>
     <p className="text-fg-2">Known active PO costs {money(data.budget.knownPOCost)} + known Joolan commitments {money(data.budget.knownCommitments)}.</p>
     <p className={cn('rounded-[14px] px-3.5 py-3 font-bold',data.budget.overBudget||remaining!=null&&remaining<0?'bg-danger-soft':'bg-success-50')}>{data.budget.remaining==null?'Provisional remaining':'Remaining'}: <span className="font-mono">{money(remaining)}</span></p>
     <p className="text-xs text-fg-3">Includes active POs in this scenario and validated POs from other scenarios for the season. Unselected Budget Tracker recommendations do not consume this PO approval budget. Unknown commitments still require reconciliation.</p>
    </section>
   </div>
   {!final&&data.blockers.length>0&&<section role="alert" className="flex flex-col gap-2.5 rounded-[20px] border border-brand-200 bg-brand-50 px-[22px] py-5 text-fg-1">
    <h2 className="flex items-center gap-2.5 text-base font-bold"><WarningIcon weight="fill" className="h-[18px] w-[18px] shrink-0 text-brand-700"/>Resolve before final validation · {data.blockers.length} checks</h2>
    <ul className="flex max-h-64 list-disc flex-col gap-1.5 overflow-auto pl-[22px] text-sm">{data.blockers.map(check=><li key={check}>{check}</li>)}</ul>
    <p className="text-sm"><Link className="font-bold underline hover:text-brand-800" href={`/purchase-orders?po=${order.id}`}>Edit this PO</Link> · <Link className="font-bold underline hover:text-brand-800" href="/budget/reconciliation">Review source inputs</Link></p>
   </section>}
   {data.warnings.length>0&&<div className="flex gap-2.5 rounded-2xl bg-soft px-4 py-3.5 text-[13px] text-fg-2"><InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-plum-600"/><div className="flex flex-col gap-1">{data.warnings.map(warning=><p key={warning}>{warning}</p>)}</div></div>}
   <section className="flex flex-col gap-2.5">{references.map(reference=>{const rows=order.lines.filter(line=>line.reference===reference);return <details key={reference} className="group overflow-hidden rounded-[18px] border border-line bg-card open:border-brand-200">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-[15px] font-bold text-fg-1 hover:bg-page [&::-webkit-details-marker]:hidden"><span className="min-w-0"><span className="font-mono text-brand-700">{reference}</span> · {rows[0]?.name}</span><CaretDownIcon weight="bold" className="h-[13px] w-[13px] shrink-0 text-fg-3 transition-transform group-open:rotate-180"/></summary>
    <div className="overflow-x-auto border-t border-line"><table className="w-full min-w-[760px] text-left text-[13px]">
     <thead><tr className="bg-page text-[10px] uppercase tracking-[0.08em] text-fg-3">{['Colour','Size','Forecast','PO qty','Purchase / unit','Selling / unit','Purchase cost'].map((title,i)=><th key={title} className={cn(cell,'font-bold',i>1&&'text-right')}>{title}</th>)}</tr></thead>
     <tbody>{rows.map(line=><tr key={line.id} className="border-t border-line"><td className={cn(cell,'font-semibold')}>{line.color}</td><td className={cn(cell,'font-mono font-bold')}>{line.size}</td><td className={cn(cell,'text-right font-mono')}>{line.forecast}</td><td className={cn(cell,'text-right font-mono font-bold')}>{line.quantity??'Unknown'}</td><td className={cn(cell,'text-right font-mono',line.unitCost==null&&'text-danger')}>{money(line.unitCost)}</td><td className={cn(cell,'text-right font-mono')}>{money(line.unitPrice)}</td><td className={cn(cell,'text-right font-mono font-bold')}>{money(line.purchaseCost)}</td></tr>)}</tbody>
    </table></div>
   </details>;})}</section>
   {final?<section className="flex flex-col gap-2.5 rounded-[28px] border border-success-400 bg-success-50 px-7 py-[26px] text-fg-1">
    <h2 className="flex items-center gap-2.5 text-xl font-extrabold tracking-[-0.02em]"><SealCheckIcon weight="fill" className="h-[26px] w-[26px] shrink-0 text-success-600"/>Final PO ready</h2>
    <p className="text-sm leading-[1.55]">Validated by {order.validation?.reviewer} on {order.validation?new Date(order.validation.createdAt).toLocaleString():''}. This document has not been sent to Joolan or the supplier.</p>
    <p className="text-xs text-fg-2">{order.validation?.reason} · Reviewer name is a local label.</p>
    <div className="mt-1.5 flex flex-wrap gap-2.5"><BrandButton onClick={()=>void download()}><DownloadSimpleIcon/>Download final PO CSV</BrandButton><BrandButton asChild variant="outline"><Link target="_blank" href={`/purchase-orders/${order.id}/print`}><PrinterIcon/>Print / save final PDF</Link></BrandButton></div>
   </section>:<section className="flex flex-col gap-4 rounded-[28px] border border-line bg-card px-7 py-[26px] shadow-card">
    <h2 className="flex items-center gap-2.5 text-xl font-extrabold tracking-[-0.02em]"><ClipboardTextIcon className="h-[22px] w-[22px] shrink-0 text-brand"/>Confirm this supplier PO</h2>
    <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3.5"><label className={inputLabel}>Reviewer name<TextField aria-label="PO reviewer name" className="h-[46px] w-full font-normal" maxLength={120} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label className={inputLabel}>Review reason<TextField aria-label="PO validation reason" className="h-[46px] w-full font-normal" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label></div>
    <label className={cn('flex cursor-pointer items-start gap-3 rounded-2xl border-[1.5px] px-4 py-3.5 text-sm leading-normal text-fg-1 transition-colors has-[:focus-visible]:shadow-[0_0_0_3px_rgba(245,130,32,0.35)]',confirmed?'border-brand bg-brand-soft':'border-line bg-card')}>
     <input type="checkbox" className="sr-only" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
     <span aria-hidden className={cn('flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[7px] border-[1.5px]',confirmed?'border-brand bg-brand':'border-border-strong bg-transparent')}>{confirmed&&<CheckIcon weight="bold" className="h-3 w-3 text-white"/>}</span>
     I reviewed the supplier, purchase quantities, purchase and selling prices, currency assumptions and financial totals.
    </label>
    <p className="text-xs leading-[1.55] text-fg-3">Validation locks this local PO and enables final downloads. It does not send an order. The reviewer name is recorded as a user-entered label.</p>
    <div><BrandButton size="lg" disabled={saving||loading||data.blockers.length>0||!reviewer.trim()||!reason.trim()||!confirmed} onClick={()=>void finalize()}><ShieldCheckIcon/>{saving?'Validating…':'Validate & finalize PO'}</BrandButton></div>
   </section>}
  </>}
 </AppShell>;
}
