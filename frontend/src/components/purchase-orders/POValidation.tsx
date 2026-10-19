"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher} from '@/components/shared';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {useSeasonStore} from '@/store/seasonStore';
import {purchaseOrdersApi,downloadPO,type POSummary,type POValidation} from '@/lib/api/purchaseOrders';

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
 return <AppShell><div className="space-y-6">
  <header className="flex flex-wrap justify-between gap-3"><div><p className="text-xs font-medium uppercase tracking-wider text-blue-600">Buying · final review</p><h1 className="mt-2 text-3xl font-semibold">Order Validation</h1><p className="mt-2 text-sm text-slate-500">Budget selection → supplier PO → final validation and download.</p></div><ScenarioSwitcher/></header>
  <div className="flex flex-wrap items-end gap-3 rounded-xl border bg-white p-5 dark:bg-slate-950"><label className="flex-1 text-xs text-slate-500">Supplier purchase order<select aria-label="Purchase order to validate" className="mt-2 block w-full rounded-lg border bg-transparent p-3 text-sm" disabled={loading||saving} value={order?.id||''} onChange={e=>void load(e.target.value)}><option value="">Choose a saved PO</option>{orders.map(o=><option key={o.id} value={o.id}>{o.number} · {o.supplier||'Supplier needed'} · {o.status.replace('_',' ')}</option>)}</select></label><Button variant="outline" disabled={loading||saving} onClick={()=>void load(order?.id)}>Refresh checks</Button><Link className="rounded-lg border px-4 py-3 text-sm text-blue-600" href="/purchase-orders">Open PO editor</Link></div>
  {loading&&<p role="status" className="text-sm text-slate-500">Checking the PO against current prices, supply and the buying budget…</p>}
  {error&&<p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</p>}
  {!loading&&!data&&!error&&<p className="rounded-xl border p-6 text-sm text-slate-500">Create a PO from selected Budget Tracker articles, choose its supplier, then use “Save & send to Order Validation” in the PO editor.</p>}
  {data&&order&&<>
   <section className="rounded-xl border bg-white p-5 dark:bg-slate-950"><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-xl font-semibold">{order.number} · {order.supplier||'Supplier not selected'}</h2><p className="mt-2 text-sm text-slate-500">{final?'Validated locally · final PO available':order.status==='pending_validation'?'Awaiting final validation':'Draft · send from the PO editor'} · v{order.version} · {order.totals.units??'Unknown'} units · {order.totals.articles} articles</p></div><Link href={`/purchase-orders?po=${order.id}`} className="text-sm text-blue-600 underline">{final?'View PO':'Edit supplier, quantities or prices'}</Link></div><div className="mt-5 grid gap-4 sm:grid-cols-4">{[['PO purchase cost',money(order.totals.purchaseCost)],['Expected turnover',money(order.totals.turnover)],['Gross margin',money(order.totals.grossMargin)],['Margin rate',order.totals.marginRate==null?'Unknown':`${order.totals.marginRate.toFixed(1)}%`]].map(([title,value])=><div key={title}><p className="text-xs text-slate-500">{title}</p><p className="mt-2 font-semibold">{value}</p></div>)}</div></section>
   <section className="rounded-xl border p-5 text-sm"><h2 className="font-semibold">Buying budget check · {data.budget.currency}</h2><p className="mt-3">Season budget {money(data.budget.amount)} · target margin {data.budget.targetMargin}%.</p><p className="mt-2">Known active PO costs {money(data.budget.knownPOCost)} + known Joolan commitments {money(data.budget.knownCommitments)}.</p><p className="mt-2 font-medium">{data.budget.remaining==null?'Provisional remaining':'Remaining'}: {money(data.budget.remaining??data.budget.provisionalRemaining)}</p><p className="mt-2 text-xs text-slate-500">Includes active POs in this scenario and validated POs from other scenarios for the season. Unselected Budget Tracker recommendations do not consume this PO approval budget. Unknown commitments still require reconciliation.</p></section>
   {!final&&data.blockers.length>0&&<section role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-amber-950"><h2 className="font-semibold">Resolve before final validation · {data.blockers.length} checks</h2><ul className="mt-3 max-h-64 list-disc space-y-2 overflow-auto pl-5 text-sm">{data.blockers.map(check=><li key={check}>{check}</li>)}</ul><p className="mt-4 text-sm"><Link className="underline" href={`/purchase-orders?po=${order.id}`}>Edit this PO</Link> · <Link className="underline" href="/budget/reconciliation">Review source inputs</Link></p></section>}
   {data.warnings.length>0&&<div className="rounded-xl border bg-slate-50 p-4 text-xs text-slate-600 dark:bg-slate-900">{data.warnings.map(warning=><p className="mt-1" key={warning}>{warning}</p>)}</div>}
   <section className="space-y-3">{references.map(reference=><details key={reference} className="rounded-xl border p-4"><summary className="cursor-pointer font-medium">{reference} · {order.lines.find(line=>line.reference===reference)?.name}</summary><div className="mt-4 overflow-auto"><table className="w-full text-left text-sm"><thead><tr>{['Colour','Size','Forecast','PO qty','Purchase / unit','Selling / unit','Purchase cost'].map(title=><th key={title} className="p-2 text-xs text-slate-500">{title}</th>)}</tr></thead><tbody>{order.lines.filter(line=>line.reference===reference).map(line=><tr key={line.id} className="border-t"><td className="p-2">{line.color}</td><td className="p-2">{line.size}</td><td className="p-2">{line.forecast}</td><td className="p-2">{line.quantity??'Unknown'}</td><td className="p-2">{money(line.unitCost)}</td><td className="p-2">{money(line.unitPrice)}</td><td className="p-2">{money(line.purchaseCost)}</td></tr>)}</tbody></table></div></details>)}</section>
   {final?<section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5"><h2 className="font-semibold">Final PO ready</h2><p className="mt-2 text-sm">Validated by {order.validation?.reviewer} on {order.validation?new Date(order.validation.createdAt).toLocaleString():''}. This document has not been sent to Joolan or the supplier.</p><p className="mt-2 text-xs text-slate-600">{order.validation?.reason} · Reviewer name is a local label.</p><div className="mt-4 flex flex-wrap gap-3"><Button onClick={()=>void download()}>Download final PO CSV</Button><Link target="_blank" className="rounded-lg border bg-white px-4 py-2 text-sm" href={`/purchase-orders/${order.id}/print`}>Print / save final PDF</Link></div></section>:<section className="space-y-4 rounded-xl border bg-white p-5 dark:bg-slate-950"><h2 className="font-semibold">Confirm this supplier PO</h2><div className="grid gap-3 sm:grid-cols-2"><label className="text-xs text-slate-500">Reviewer name<Input aria-label="PO reviewer name" className="mt-2" maxLength={120} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label className="text-xs text-slate-500">Review reason<Input aria-label="PO validation reason" className="mt-2" maxLength={1000} value={reason} onChange={e=>setReason(e.target.value)}/></label></div><label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I reviewed the supplier, purchase quantities, purchase and selling prices, currency assumptions and financial totals.</label><p className="text-xs text-slate-500">Validation locks this local PO and enables final downloads. It does not send an order. The reviewer name is recorded as a user-entered label.</p><Button disabled={saving||loading||data.blockers.length>0||!reviewer.trim()||!reason.trim()||!confirmed} onClick={()=>void finalize()}>{saving?'Validating…':'Validate & finalize PO'}</Button></section>}
  </>}
 </div></AppShell>;
}
