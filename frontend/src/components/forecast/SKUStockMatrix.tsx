"use client";
import React from 'react';
import {CaretDownIcon,DropIcon} from '@phosphor-icons/react';
import {cn} from '@/lib/utils';
import {SKUDetailedProjection, SizeData} from '@/types/stockMatrix';
import ConfidenceBadge from '@/components/shared/ConfidenceBadge';

const format=(v:number|null|undefined)=>v==null?'Unknown':v.toLocaleString(undefined,{maximumFractionDigits:2});
const total=(values:SizeData|undefined)=>{
 const entries=Object.values(values||{});
 return entries.length&&entries.every((v):v is number=>v!==null)?entries.reduce((a,b)=>a+b,0):null;
};
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XL2','XXXL','XL3','XL4','XL5','XL6','XL7'];
const sortSizes=(values:string[])=>Array.from(new Set(values)).sort((a,b)=>{
 const ai=sizeOrder.indexOf(a),bi=sizeOrder.indexOf(b);
 return ai>=0&&bi>=0?ai-bi:ai>=0?-1:bi>=0?1:a.localeCompare(b,undefined,{numeric:true});
});
type Measure={label:string;values:SizeData|undefined;term?:string;description:string;tone:string;swatch:string;weight?:string};

export function SKUStockMatrix({data,className}:{data:SKUDetailedProjection;className?:string}){
 const snapshot=data.warehouseStock;
 const season=data.projectionBasis==='season_bookings';
 const colors=data.colorVariants.map(c=>c.color);
 const sizes=sortSizes(data.colorVariants.flatMap(c=>Object.keys(c.recommendedQty)));
 const sourceColors=Array.from(new Set([...colors,...(snapshot?.colors.map(c=>c.color)||[])])).sort();
 const sourceSizes=sortSizes([...sizes,...(snapshot?.colors.flatMap(c=>Object.keys(c.stock))||[])]);
 const forecastMeasures=(name:string):Measure[]=>{
  const stock=snapshot?.colors.find(c=>c.color===name);const forecast=data.colorVariants.find(c=>c.color===name);
  return [
   {label:'Available stock',values:stock?stock.available:forecast?.availableStock,term:'Disponible',description:'Joolan available balance. Physical stock and allocations are shown separately in the expanded source details.',tone:'text-fg-1',swatch:'bg-fg-1'},
   {label:'Incoming supply',values:stock?.toReceive,term:'À recevoir · Reliquat_Fournisseur',description:'Full Joolan À recevoir balance, across all receipt dates. Net purchase uses only eligible receipts within the planning period.',tone:'text-success-600',swatch:'bg-success-600'},
   {label:season?'Season booked units':'Recorded open order balance',values:forecast?.totalDeProduit,description:'Customer units booked within the season. This is not the outstanding Clients warehouse balance.',tone:'text-plum-600',swatch:'bg-plum-600'},
   {label:season?'Delivered against season bookings':'Historical delivered units',values:forecast?.totalDeCitNegoce,description:'Recorded deliveries against these bookings. Not subtracted again from current stock.',tone:'text-plum-600',swatch:'bg-plum-600'},
   {label:'Forecast demand',values:forecast?.recommendedQty,description:'Published demand forecast for the selected scenario and planning period. Not Joolan theoretical stock.',tone:'text-brand-700',swatch:'bg-brand',weight:'font-semibold'},
   {label:'Net purchase quantity',values:forecast?.totalDeLeStock,description:'Published purchasing need after available stock and eligible scheduled receipts. Unknown inputs remain unknown; full À recevoir is not automatically deducted.',tone:'text-danger',swatch:'bg-danger',weight:'font-bold'},
  ];
 };
 const sourceMeasures=(name:string):Measure[]=>{
  const stock=snapshot?.colors.find(c=>c.color===name);const forecast=data.colorVariants.find(c=>c.color===name);
  return [
   {label:'Stock',values:stock?.stock,term:'En_Stock',description:'Physical stock in the supplying warehouses.',tone:'text-fg-1',swatch:'bg-fg-1'},
   {label:'À recevoir',values:stock?.toReceive,term:'Reliquat_Fournisseur',description:'Outstanding supplier receipts across dates.',tone:'text-success-600',swatch:'bg-success-600'},
   {label:'Clients',values:stock?.clients,term:'En_Commande',description:'Outstanding customer-order units; not season bookings or a customer count.',tone:'text-plum-600',swatch:'bg-plum-600'},
   {label:'Attribué',values:stock?.allocated,term:'Attribue',description:'Allocated units; do not deduct again from Disponible.',tone:'text-plum-600',swatch:'bg-plum-600'},
   {label:'Théorique',values:stock?.theoretical,term:'Theorique',description:'Joolan theoretical stock balance, including negative values. Not the demand forecast.',tone:'text-fg-1',swatch:'bg-fg-1',weight:'font-bold'},
   {label:'Receipts used for net purchasing',values:forecast?.totalDeFournisseur,term:'Eligible receipts · planning period',description:'Supplier quantities eligible by planned receipt date and status for the published net purchase calculation.',tone:'text-success-600',swatch:'bg-success-600'},
  ];
 };
 function table(names:string[],columns:string[],measuresFor:(name:string)=>Measure[],source=false){
  return <div className="overflow-x-auto rounded-[14px] border border-line">
   <table aria-label={source?'Joolan source stock balances':'Forecast and purchase quantities'} className="w-full min-w-max border-collapse text-[13px]">
    <thead className="bg-soft text-[11px] font-bold uppercase tracking-[0.08em] text-fg-3">
     <tr><th scope="col" rowSpan={2} className="min-w-[140px] border-r border-line px-3.5 py-2.5 text-left align-bottom">Colour</th><th scope="col" rowSpan={2} className="min-w-[245px] border-r border-line px-3.5 py-2.5 text-left align-bottom">Measure</th>
      {columns.length>0&&<th scope="colgroup" colSpan={columns.length} className="border-b border-line px-3.5 pb-1.5 pt-2.5 text-left">Size</th>}
      <th scope="col" rowSpan={2} className="border-l border-line px-3.5 py-2.5 text-right align-bottom">Total</th></tr>
     <tr>{columns.map(size=><th key={size} scope="col" className="min-w-16 px-3.5 pb-2.5 pt-1.5 text-right font-mono tracking-normal">{size}</th>)}</tr>
    </thead>
    {names.map(color=>{
     const measures=measuresFor(color);
     const forecastSizes=Object.keys(data.colorVariants.find(c=>c.color===color)?.recommendedQty||{});
     const definedSizes=new Set(source?[...forecastSizes,...Object.keys(snapshot?.colors.find(c=>c.color===color)?.stock||{})]:forecastSizes);
     return <tbody key={color} className="border-t-2 border-border-strong first-of-type:border-t-0">
      {measures.map((m,i)=><tr key={m.label} className={cn('hover:bg-brand-50',i>0&&'border-t border-line',m.tone,m.weight||'font-medium')}>
       {i===0&&<th scope="rowgroup" rowSpan={measures.length} className="border-r border-line bg-page px-3.5 py-2.5 text-left align-top font-bold text-fg-1"><span className="flex items-center gap-2"><DropIcon weight="fill" aria-hidden className="h-[13px] w-[13px] shrink-0 text-brand"/>{color}</span></th>}
       <th scope="row" title={m.description} className="border-r border-line px-3.5 py-2 text-left font-[inherit]"><span className="flex items-center gap-2"><span aria-hidden className={cn('h-2 w-2 shrink-0 rounded-full',m.swatch)}/><span className="flex flex-col"><span>{m.label}</span>{m.term&&<span className="font-mono text-[10px] font-medium text-fg-3">{m.term}</span>}</span></span></th>
       {columns.map(size=><td key={size} className={cn('px-3.5 py-2 text-right font-mono tabular-nums',!definedSizes.has(size)&&'text-fg-4')}>{definedSizes.has(size)?format(m.values?.[size]):'—'}</td>)}
       <td className="border-l border-line px-3.5 py-2 text-right font-mono font-bold tabular-nums">{format(total(Object.fromEntries([...definedSizes].map(size=>[size,m.values?.[size]??null]))))}</td>
      </tr>)}
     </tbody>;
    })}
   </table>
  </div>;
 }
 return <section className={cn('overflow-hidden rounded-[20px] border border-line bg-card',className)}>
  <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-[22px] py-5">
   <div className="flex min-w-0 flex-col gap-1">
    <h3 className="text-[17px] font-bold"><span className="font-mono">{data.productInfo.reference}</span> · {data.productInfo.name}</h3>
    <p className="text-[13px] text-fg-3">{data.productInfo.famille} · {data.productInfo.matiere} · {data.productInfo.saison}</p>
    <p className="text-sm text-fg-2">{snapshot?.warehouses.join(' + ')||'Published forecast'} · <span className="capitalize">{data.scenario||'base'}</span> scenario</p>
    {snapshot&&<p className="text-xs text-fg-3">Joolan snapshot: {snapshot.snapshotAt?new Date(snapshot.snapshotAt).toLocaleString():'capture time unavailable'}</p>}
   </div>
   <ConfidenceBadge level={data.confidence} size="sm"/>
  </header>
  <p className="px-[22px] py-3 text-xs leading-relaxed text-fg-3">Incoming supply shows the full Joolan À recevoir balance. Net purchase quantity uses only eligible receipts within the forecast dates, so it may not equal forecast minus the incoming supply shown here. Unknown values remain unknown.</p>
  <div className="mx-[22px] mb-[22px]">{table(colors,sizes,forecastMeasures)}</div>
  <details className="group/source mx-[22px] mb-[22px] rounded-[14px] border border-line">
   <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">Joolan stock details and receipt eligibility<CaretDownIcon className="h-4 w-4 shrink-0 transition-transform group-open/source:rotate-180"/></summary>
   <div className="flex flex-col gap-3 border-t border-line p-4">
    <p className="text-xs leading-relaxed text-fg-3">Stock (En_Stock), À recevoir (Reliquat_Fournisseur), Clients (En_Commande), Attribué and Théorique are Joolan source balances. Clients is not season booked units; Théorique is not forecast demand. Allocations are already reflected in Disponible.</p>
    {snapshot?<p className="text-xs text-fg-3">{snapshot.completeVariants} of {snapshot.totalVariants} catalogue / forecast variants have all stock measures across {snapshot.warehouses.join(' + ')}. Missing warehouse records remain unknown. Catalogue-only sizes appear here without an invented forecast. Source: {snapshot.source}.</p>:<p className="text-xs text-brand-800">The published forecast has no matching complete Joolan stock snapshot. Full À recevoir and other source balances remain unknown; published forecast quantities are retained.</p>}
    {table(sourceColors,sourceSizes,sourceMeasures,true)}
   </div>
  </details>
 </section>;
}
export default SKUStockMatrix;
