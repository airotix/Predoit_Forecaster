"use client";
import {useEffect,useState} from 'react';
import {useParams} from 'next/navigation';
import Link from 'next/link';
import {purchaseOrdersApi,type PurchaseOrder} from '@/lib/api/purchaseOrders';
import {Button} from '@/components/ui/button';

export default function PrintablePO(){
 const {id}=useParams<{id:string}>();const [order,setOrder]=useState<PurchaseOrder|null>(null),[error,setError]=useState('');
 useEffect(()=>{let active=true;void purchaseOrdersApi.read(id).then(value=>{if(active)setOrder(value);}).catch(e=>{if(active)setError(e instanceof Error?e.message:'Could not load PO.');});return()=>{active=false;};},[id]);
 if(error)return <main className="mx-auto max-w-4xl p-8"><p role="alert">{error}</p><Link href="/purchase-orders">Back to purchase orders</Link></main>;
 if(!order)return <p role="status" className="p-8">Loading printable PO…</p>;
 const money=(value:number|null)=>value==null?'Unknown':new Intl.NumberFormat('en-GB',{style:'currency',currency:order.supplierCurrency||order.currency}).format(value);
 const lines=order.lines.filter(line=>line.quantity!==0).sort((a,b)=>a.reference.localeCompare(b.reference,undefined,{numeric:true})||a.color.localeCompare(b.color)||a.size.localeCompare(b.size,undefined,{numeric:true}));
 return <main className="mx-auto max-w-5xl bg-white p-6 text-slate-900 sm:p-10 print:max-w-none print:p-0">
 <div className="mb-8 flex flex-wrap items-center justify-between gap-3 print:hidden"><Link className="text-sm text-blue-600" href="/purchase-orders">← Back to purchase orders</Link><Button onClick={()=>window.print()}>Print / save PDF</Button></div>
 <header className="flex items-start justify-between gap-5 border-b-2 border-slate-900 pb-6"><div><p className="text-xs font-semibold uppercase tracking-widest">Supplier purchase order</p><h1 className="mt-3 text-3xl font-semibold">{order.number}</h1><p className="mt-2 text-sm">Version {order.version} · {order.supplierCurrency||order.currency}</p></div><strong className="rounded border-2 border-amber-500 px-4 py-2 text-amber-800">{order.status==='cancelled'?'CANCELLED':order.status==='validated'?'FINAL · VALIDATED · NOT SENT':'DRAFT · NOT SENT'}</strong></header>
 <div className="my-7 grid grid-cols-2 gap-8 text-sm"><section><h2 className="font-semibold">Supplier</h2><p className="mt-2">{order.supplier||'Supplier not assigned'}</p><h2 className="mt-5 font-semibold">Deliver to</h2><p className="mt-2 whitespace-pre-wrap">{order.shipTo||'Not specified'}</p></section><section className="text-right"><p>PO date: {order.orderDate}</p><p className="mt-2">Requested delivery: {order.deliveryDate||'Not specified'}</p><p className="mt-2">{order.seasonName}</p></section></div>
 <table className="w-full border-collapse text-left text-xs"><thead className="bg-slate-100"><tr>{['Article / description','Colour','Size','Quantity','Purchase / unit','Line total'].map(label=><th key={label} className="border-y border-slate-300 px-2 py-3">{label}</th>)}</tr></thead><tbody>{lines.map(line=><tr key={line.id} className="break-inside-avoid border-b border-slate-200"><td className="p-2"><strong>{line.reference}</strong><p className="mt-1">{line.name}</p></td><td className="p-2">{line.color}</td><td className="p-2">{line.size}</td><td className="p-2">{line.quantity??'Unknown'}</td><td className="p-2">{money(line.supplierUnitCost===undefined?line.unitCost:line.supplierUnitCost)}</td><td className="p-2">{money(line.supplierPurchaseCost===undefined?line.purchaseCost:line.supplierPurchaseCost)}</td></tr>)}</tbody></table>
 <div className="ml-auto mt-6 max-w-sm border-t border-slate-300 pt-4 text-sm"><p className="flex justify-between"><span>Ordered units</span><strong>{order.totals.units??'Unknown'}</strong></p><p className="mt-3 flex justify-between text-lg"><span>Purchase subtotal</span><strong>{money(order.supplierTotals?order.supplierTotals.purchaseCost:order.totals.purchaseCost)}</strong></p><p className="mt-3 text-xs text-slate-500">Supplier currency: {order.supplierCurrency||order.currency}. Unmapped VAT, freight, duty and other charges are not included. Unknown prices are blank estimates, not zero-cost goods.</p></div>
 {order.notes&&<section className="mt-8 break-inside-avoid border-t pt-4"><h2 className="text-sm font-semibold">Notes / instructions</h2><p className="mt-2 whitespace-pre-wrap text-sm">{order.notes}</p></section>}
 <footer className="mt-10 border-t pt-4 text-xs text-slate-500">{order.status==='validated'?'Final local PO validated for download. This document has not been sent to Joolan or the supplier.':'Editable local draft for supplier review. This document has not been sent and is not a confirmed purchase commitment.'}</footer>
 </main>;
}
