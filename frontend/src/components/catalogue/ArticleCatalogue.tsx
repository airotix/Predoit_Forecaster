"use client";
import {BookOpen,ChevronDown} from 'lucide-react';
import {Input} from '@/components/ui/input';
import {Button} from '@/components/ui/button';
import StatusControl,{StatusBadge,type CatalogueStatus,type StatusChange} from './StatusControl';
import type {SupplierFX} from '@/lib/api/budget';
export interface OrderPriceEvidence {supplier?:string;customer?:string;orderId?:string;orderNumber?:string;orderDate?:string;currency:string;price?:number;unitCost?:number;method?:string;matchLevel?:string;matchedVariant?:string[];reason?:string|null;cutoff:string;previousPrice?:number|null;changedAt?:string;fx?:SupplierFX;}
export interface CatalogueSKU{sku:string;reference:string;color:string;size:string;name:string;brand:string;category:string;supplier:string;purchase:number|null;selling:number|null;purchaseSource:string;sellingSource:string;updatedAt:string|null;purchasePriceDetails?:OrderPriceEvidence|null;sellingPriceDetails?:OrderPriceEvidence|null;status?:CatalogueStatus|null;}
function Evidence({row,side,disabled,reset}:{row:CatalogueSKU;side:'purchase'|'selling';disabled:boolean;reset:(row:CatalogueSKU,side:'purchase'|'selling')=>void}){
 const evidence=side==='purchase'?row.purchasePriceDetails:row.sellingPriceDetails;
 const source=side==='purchase'?row.purchaseSource:row.sellingSource;
 const age=evidence?.orderDate?Math.max(0,Math.floor((Date.now()-Date.parse(evidence.orderDate))/86400000)):null;
 return <div className="mb-3 max-w-72"><p className="font-medium">{side==='purchase'?'Purchase':'Selling'}: {source==='manual'?'Saved manually':row[side]==null?'Needs review':side==='purchase'?'Latest supplier order':'Latest customer order'}</p>
 {evidence?.reason&&<p className="mt-1 text-amber-700">{evidence.reason}</p>}
 {evidence?.fx&&<p className="mt-2 text-blue-700">{evidence.fx.nativeUnitCost} {evidence.fx.nativeCurrency} ÷ {evidence.fx.exchangeRate} = {evidence.fx.unitCost} {evidence.fx.currency}. Recorded supplier-order rate, verified against Joolan receipts; not a current FX quote.</p>}
 {evidence?.orderId&&<details className="mt-1"><summary className="cursor-pointer text-blue-600">{evidence.orderNumber||evidence.orderId} · {evidence.orderDate} · {evidence.currency}</summary><div className="mt-2 space-y-1"><p>{side==='purchase'?'Supplier':'Customer'}: {evidence.supplier||evidence.customer||'Not recorded'}</p><p>Net unit price: {evidence.price?.toFixed(2)} {evidence.currency} · {age} days old</p><p>{evidence.matchLevel}{evidence.matchedVariant?` (${evidence.matchedVariant.join(' / ')})`:''}</p><p>{evidence.method}</p><p>Data through {evidence.cutoff}.</p>{evidence.changedAt&&<p>Previous automatic price: {evidence.previousPrice==null?'Unknown':evidence.previousPrice.toFixed(2)} {evidence.currency}</p>}</div></details>}
 {source==='manual'&&evidence&&<button type="button" disabled={disabled} className="mt-2 text-xs text-blue-600 underline disabled:opacity-40" onClick={()=>reset(row,side)}>Use latest Joolan {side} price</button>}
 </div>;
}

type Field='purchase'|'selling';
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XL2','3XL','XL3','4XL','XL4','5XL','XL5','6XL','XL6','7XL','XL7'];
function compareSizes(a:CatalogueSKU,b:CatalogueSKU){
 const x=sizeOrder.indexOf(a.size.toUpperCase()),y=sizeOrder.indexOf(b.size.toUpperCase());
 return x>=0&&y>=0?x-y:a.size.localeCompare(b.size,undefined,{numeric:true});
}
export default function ArticleCatalogue({rows,busy,statusDisabled,value,edit,edited,select,reset,changeStatus}:{rows:CatalogueSKU[];busy:boolean;statusDisabled:boolean;value:(row:CatalogueSKU,field:Field)=>string|number;edit:(row:CatalogueSKU,field:Field,value:string)=>void;edited:(sku:string)=>boolean;select:(row:CatalogueSKU)=>void;reset:(row:CatalogueSKU,side:Field)=>void;changeStatus:StatusChange}){
 const articles=new Map<string,CatalogueSKU[]>();
 for(const row of rows)articles.set(row.reference,[...(articles.get(row.reference)||[]),row]);
 if(!rows.length)return <p className="p-8 text-center text-sm text-slate-500">No articles match these filters.</p>;
 return <div className="space-y-4 p-4">{Array.from(articles,([reference,variants])=>{
  const first=variants[0];const colours=new Map<string,CatalogueSKU[]>();
  for(const row of variants)colours.set(row.color,[...(colours.get(row.color)||[]),row]);
  return <details key={reference} open={articles.size===1} className="group rounded-xl border bg-white">
   <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-xl bg-slate-50 p-4 [&::-webkit-details-marker]:hidden">
    <div><h2 className="text-base font-semibold">{reference} <span className="ml-2 font-medium">{first.name}</span></h2><p className="mt-1 text-xs text-slate-500">{Array.from(new Set(variants.map(r=>r.brand))).join(', ')} · {first.category} · {colours.size} colours · {variants.length} SKUs</p></div>
    <div className="flex items-center gap-3"><StatusBadge active={first.status?.articleActive}/><ChevronDown className="h-5 w-5 shrink-0 text-slate-500 group-open:rotate-180"/></div>
   </summary>
   <div className="space-y-3 p-4"><div className="flex flex-wrap items-center gap-5 rounded-lg border bg-slate-50 p-4"><StatusControl level="article" id={reference} status={first.status} disabled={statusDisabled} onChange={changeStatus}/><div className="text-xs text-slate-500"><p>Inactive articles block new purchases for every colour and size.</p><p className="mt-1">Active articles can still contain inactive individual SKUs.</p><p className="mt-1">{variants.filter(r=>r.status?.purchasingBlocked).length} of {variants.length} variants currently blocked for purchasing.</p></div></div>{Array.from(colours,([colour,sizes])=><details key={colour} open className="rounded-lg border">
    <summary className="flex cursor-pointer items-center justify-between gap-3 bg-blue-50 px-4 py-3 text-sm"><span className="font-semibold">{colour||'Colour unspecified'}</span><span className="text-xs text-slate-500">{sizes.length} sizes / SKUs</span></summary>
    <div className="overflow-x-auto"><table className="w-full min-w-[1040px] text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr>{['Size / SKU','Status','Purchase / unit','Selling / unit (ex VAT)','Price source',''].map((h,i)=><th key={i} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead><tbody>{[...sizes].sort(compareSizes).map(row=><tr key={row.sku} className={`border-t ${row.status?.purchasingBlocked?'bg-slate-50':''}`}>
     <td className="px-4 py-3"><p className="font-semibold">{row.size||'Size unspecified'}</p><p className="mt-1 text-xs text-slate-500">SKU {row.sku}</p></td>
     <td className="px-4 py-3"><StatusBadge active={row.status?.active}/><div className="mt-2"><StatusControl level="sku" id={row.sku} status={row.status} disabled={statusDisabled} onChange={changeStatus}/></div></td>
     {(['purchase','selling'] as Field[]).map(field=><td key={field} className="px-4 py-3"><Input aria-label={`SKU ${row.sku} ${field} price`} disabled={busy} className="w-32" type="number" min="0" step="0.01" placeholder={field==='purchase'?'Unknown':'Enter price'} value={value(row,field)} onChange={e=>edit(row,field,e.target.value)}/></td>)}
     <td className="px-4 py-3 text-xs text-slate-500"><Evidence row={row} side="purchase" disabled={busy} reset={reset}/><Evidence row={row} side="selling" disabled={busy} reset={reset}/>{edited(row.sku)&&<p className="mt-1 text-amber-700">Unsaved edits</p>}</td>
     <td className="px-4 py-3"><Button variant="ghost" size="sm" onClick={()=>select(row)}><BookOpen className="h-4 w-4"/>Details</Button></td>
    </tr>)}</tbody></table></div>
   </details>)}</div>
  </details>;
 })}</div>;
}
