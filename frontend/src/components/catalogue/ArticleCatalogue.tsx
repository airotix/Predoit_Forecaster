"use client";
import ActivityBadge,{type ArticleActivity} from '@/components/shared/ArticleActivity';
import {useState} from 'react';
import {BookOpenIcon,CaretDownIcon,CaretUpIcon,DropIcon} from '@phosphor-icons/react';
import StatusControl,{StatusBadge,type CatalogueStatus,type StatusChange} from './StatusControl';
import type {SupplierFX} from '@/lib/api/budget';
import {cn} from '@/lib/utils';
export interface OrderPriceEvidence {supplier?:string;customer?:string;orderId?:string;orderNumber?:string;orderDate?:string;currency:string;price?:number;unitCost?:number;method?:string;matchLevel?:string;matchedVariant?:string[];reason?:string|null;cutoff:string;previousPrice?:number|null;changedAt?:string;fx?:SupplierFX;}
export interface CatalogueSKU{activity?:ArticleActivity|null;sku:string;reference:string;color:string;size:string;name:string;brand:string;category:string;supplier:string;purchase:number|null;selling:number|null;purchaseSource:string;sellingSource:string;updatedAt:string|null;purchasePriceDetails?:OrderPriceEvidence|null;sellingPriceDetails?:OrderPriceEvidence|null;status?:CatalogueStatus|null;}
function Evidence({row,side,disabled,reset}:{row:CatalogueSKU;side:'purchase'|'selling';disabled:boolean;reset:(row:CatalogueSKU,side:'purchase'|'selling')=>void}){
 const [open,setOpen]=useState(false);
 const evidence=side==='purchase'?row.purchasePriceDetails:row.sellingPriceDetails;
 const source=side==='purchase'?row.purchaseSource:row.sellingSource;
 const age=evidence?.orderDate?Math.max(0,Math.floor((Date.now()-Date.parse(evidence.orderDate))/86400000)):null;
 return <div className="flex flex-col gap-[3px]">
  <span className="font-bold text-fg-1">{side==='purchase'?'Purchase':'Selling'}: {source==='manual'?'Saved manually':row[side]==null?'Needs review':side==='purchase'?'Latest supplier order':'Latest customer order'}</span>
  {evidence?.reason&&<span className="text-brand-800">{evidence.reason}</span>}
  {evidence?.fx&&<span className="text-plum-600">{evidence.fx.nativeUnitCost} {evidence.fx.nativeCurrency} ÷ {evidence.fx.exchangeRate} = {evidence.fx.unitCost} {evidence.fx.currency}. Recorded supplier-order rate, verified against Joolan receipts; not a current FX quote.</span>}
  {evidence?.orderId&&<>
   <button type="button" aria-expanded={open} onClick={()=>setOpen(v=>!v)} className="flex items-center gap-1 self-start font-mono text-xs font-semibold text-brand-700">{evidence.orderNumber||evidence.orderId} · {evidence.orderDate} · {evidence.currency}{open?<CaretUpIcon weight="bold" className="h-[11px] w-[11px]"/>:<CaretDownIcon weight="bold" className="h-[11px] w-[11px]"/>}</button>
   {open&&<div className="flex flex-col gap-0.5 rounded-[10px] bg-soft px-2.5 py-2 text-fg-2">
    <span>{side==='purchase'?'Supplier':'Customer'}: {evidence.supplier||evidence.customer||'Not recorded'}</span>
    <span>Net unit price: {evidence.price?.toFixed(2)} {evidence.currency} · {age} days old</span>
    <span>{evidence.matchLevel}{evidence.matchedVariant?` (${evidence.matchedVariant.join(' / ')})`:''}</span>
    <span>{evidence.method}</span>
    <span>Data through {evidence.cutoff}.</span>
    {evidence.changedAt&&<span>Previous automatic price: {evidence.previousPrice==null?'Unknown':evidence.previousPrice.toFixed(2)} {evidence.currency}</span>}
   </div>}
  </>}
  {source==='manual'&&evidence&&<button type="button" disabled={disabled} className="self-start text-xs font-semibold text-brand-700 underline disabled:opacity-40" onClick={()=>reset(row,side)}>Use latest Joolan {side} price</button>}
 </div>;
}

type Field='purchase'|'selling';
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XL2','3XL','XL3','4XL','XL4','5XL','XL5','6XL','XL6','7XL','XL7'];
function compareSizes(a:CatalogueSKU,b:CatalogueSKU){
 const x=sizeOrder.indexOf(a.size.toUpperCase()),y=sizeOrder.indexOf(b.size.toUpperCase());
 return x>=0&&y>=0?x-y:a.size.localeCompare(b.size,undefined,{numeric:true});
}
const GRID='grid grid-cols-[minmax(130px,0.7fr)_250px_150px_170px_minmax(280px,1.5fr)_110px] gap-4';
export default function ArticleCatalogue({rows,busy,statusDisabled,value,edit,edited,select,reset,changeStatus}:{rows:CatalogueSKU[];busy:boolean;statusDisabled:boolean;value:(row:CatalogueSKU,field:Field)=>string|number;edit:(row:CatalogueSKU,field:Field,value:string)=>void;edited:(sku:string)=>boolean;select:(row:CatalogueSKU)=>void;reset:(row:CatalogueSKU,side:Field)=>void;changeStatus:StatusChange}){
 const [open,setOpen]=useState<Record<string,boolean>>({});
 const articles=new Map<string,CatalogueSKU[]>();
 for(const row of rows)articles.set(row.reference,[...(articles.get(row.reference)||[]),row]);
 if(!rows.length)return <p className="p-10 text-center text-sm text-fg-3">No articles match these filters.</p>;
 return <div className="flex flex-col gap-3 p-4">{Array.from(articles,([reference,variants])=>{
  const first=variants[0];const colours=new Map<string,CatalogueSKU[]>();
  for(const row of variants)colours.set(row.color,[...(colours.get(row.color)||[]),row]);
  const isOpen=open[reference]??articles.size===1;
  return <div key={reference} className={cn('overflow-hidden rounded-[20px] border bg-card',isOpen?'border-brand-200':'border-line')}>
   <button type="button" aria-expanded={isOpen} onClick={()=>setOpen(o=>({...o,[reference]:!isOpen}))} className={cn('flex w-full items-center justify-between gap-4 px-5 py-4 text-left text-fg-1 hover:bg-soft',isOpen?'bg-page':'bg-card')}>
    <span className="flex min-w-0 flex-col gap-1">
     <span className="flex flex-wrap items-baseline gap-2.5"><span className="font-mono text-sm font-bold text-brand-700">{reference}</span><span className="text-base font-bold">{first.name}</span><ActivityBadge activity={first.activity}/></span>
     <span className="text-[13px] text-fg-3">{Array.from(new Set(variants.map(r=>r.brand))).join(', ')} · {first.category} · {colours.size} colours · {variants.length} SKUs</span>
    </span>
    <span className="flex shrink-0 items-center gap-3"><StatusBadge active={first.status?.articleActive}/><span className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-card">{isOpen?<CaretUpIcon weight="bold" className="h-[13px] w-[13px]"/>:<CaretDownIcon weight="bold" className="h-[13px] w-[13px]"/>}</span></span>
   </button>
   {isOpen&&<div className="flex flex-col gap-3.5 border-t border-line px-5 pb-5 pt-4">
    <div className="flex flex-wrap items-start gap-6 rounded-2xl bg-soft px-[18px] py-4">
     <StatusControl level="article" id={reference} status={first.status} disabled={statusDisabled} onChange={changeStatus}/>
     <div className="flex flex-col gap-1 pt-5 text-xs leading-[1.55] text-fg-2"><span>Inactive articles block new purchases for every colour and size.</span><span>Active articles can still contain inactive individual SKUs.</span><span><strong className="text-fg-1">{variants.filter(r=>r.status?.purchasingBlocked).length} of {variants.length}</strong> variants currently blocked for purchasing.</span></div>
    </div>
    {Array.from(colours,([colour,sizes])=><div key={colour} className="overflow-hidden rounded-2xl border border-line">
     <div className="flex items-center justify-between gap-3 bg-brand-50 px-4 py-3"><span className="flex items-center gap-2 text-sm font-bold"><DropIcon weight="fill" className="h-[13px] w-[13px] text-brand"/>{colour||'Colour unspecified'}</span><span className="text-xs text-fg-3">{sizes.length} sizes / SKUs</span></div>
     <div className="overflow-x-auto"><div role="table" aria-label={`${reference} ${colour} SKUs`} className="min-w-[1080px]">
      <div role="row" className={cn(GRID,'border-b border-line bg-page px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3')}>{['Size / SKU','Status','Purchase / unit','Selling / unit (ex VAT)','Price source',''].map((h,i)=><span role="columnheader" key={i}>{h}</span>)}</div>
      {[...sizes].sort(compareSizes).map((row,i)=><div role="row" key={row.sku} className={cn(GRID,'items-start px-4 py-3.5',i>0&&'border-t border-line',row.status?.purchasingBlocked&&'bg-soft')}>
       <div role="cell" className="flex flex-col gap-1"><span className="text-[15px] font-bold">{row.size||'Size unspecified'}</span><span className="font-mono text-xs text-fg-3">SKU {row.sku}</span></div>
       <div role="cell" className="flex flex-col items-start gap-1.5"><StatusBadge active={row.status?.active}/><StatusControl level="sku" id={row.sku} status={row.status} disabled={statusDisabled} onChange={changeStatus}/></div>
       {(['purchase','selling'] as Field[]).map(field=>{const changed=edited(row.sku)&&value(row,field)!==(row[field]??'');return <div role="cell" key={field}><input aria-label={`SKU ${row.sku} ${field} price`} disabled={busy} type="number" min="0" step="0.01" placeholder={field==='purchase'?'Unknown':'Enter price'} value={value(row,field)} onChange={e=>edit(row,field,e.target.value)}
        className={cn('h-[42px] rounded-xl border-[1.5px] bg-card px-3 text-right font-mono text-sm font-bold text-fg-1 outline-none [color-scheme:light_dark] placeholder:font-normal placeholder:text-fg-3 focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:opacity-60',field==='purchase'?'w-[130px]':'w-[140px]',changed?'border-brand':'border-line')}/></div>;})}
       <div role="cell" className="flex flex-col gap-2.5 text-xs leading-normal text-fg-3"><Evidence row={row} side="purchase" disabled={busy} reset={reset}/><Evidence row={row} side="selling" disabled={busy} reset={reset}/>{edited(row.sku)&&<span className="font-bold text-brand-800">Unsaved edits</span>}</div>
       <div role="cell" className="flex justify-end"><button type="button" onClick={()=>select(row)} className="flex h-9 items-center gap-1.5 rounded-[10px] px-3 text-[13px] font-semibold text-fg-2 hover:bg-soft hover:text-fg-1"><BookOpenIcon className="h-[15px] w-[15px]"/>Details</button></div>
      </div>)}
     </div></div>
    </div>)}
   </div>}
  </div>;
 })}</div>;
}
