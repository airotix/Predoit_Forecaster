"use client";
import {Fragment} from 'react';
import {DropIcon} from '@phosphor-icons/react';
import {cn} from '@/lib/utils';
import {SKUDetailedProjection, SizeData} from '@/types/stockMatrix';
import {ConfidenceBadge} from '@/components/shared';

const format=(v:number|null|undefined)=>v==null?'Unknown':v.toLocaleString(undefined,{maximumFractionDigits:2});
const total=(values:SizeData|undefined)=>{
 const entries=Object.values(values||{});
 return entries.length&&entries.every((v):v is number=>v!==null)?entries.reduce((a,b)=>a+b,0):null;
};
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XL2','XXXL','XL3','XL4','XL5','XL6','XL7'];

/** One measure row of a colour block. `term` names the matching row of the Joolan
 * "Etat du stock théorique détaillé" report; measures without one are Preduit additions. */
type Measure={label:string;values:SizeData|undefined;term?:string;tone:string;swatch:string;weight:string};

export function SKUStockMatrix({data,className}:{data:SKUDetailedProjection;className?:string}){
 const sizes=Array.from(new Set(data.colorVariants.flatMap(c=>Object.keys(c.recommendedQty)))).sort((a,b)=>{
  const ai=sizeOrder.indexOf(a),bi=sizeOrder.indexOf(b);
  return ai>=0&&bi>=0?ai-bi:a.localeCompare(b,undefined,{numeric:true});
 });
 const season=data.projectionBasis==='season_bookings';
 const summary=[
  {label:'Available warehouse stock',term:'Stock Réel',value:data.stockSummary.stockReel,bar:'border-t-fg-1',text:'text-fg-1'},
  {label:'Incoming supply',term:'Fournisseur',value:data.stockSummary.fournisseur,bar:'border-t-success-600',text:'text-success-600'},
  {label:'Stock plus incoming supply',term:'Qté',value:data.stockSummary.total,bar:'border-t-brand',text:'text-brand-700'},
 ];
 // Report row order: Produit (stock), Fournisseur (supply), CltNegoce (customer orders), LeStock (result).
 const measuresFor=(color?:SKUDetailedProjection['colorVariants'][number]):Measure[]=>[
  {label:'Available stock',values:color?.availableStock,term:'Total de Produit',tone:'text-fg-1',swatch:'bg-fg-1',weight:'font-medium'},
  {label:'Incoming supply',values:color?.totalDeFournisseur,term:'Total de Fournisseur',tone:'text-success-600',swatch:'bg-success-600',weight:'font-medium'},
  {label:season?'Season booked units':'Recorded open order balance',values:color?.totalDeProduit,term:'Total de CltNegoce',tone:'text-plum-600',swatch:'bg-plum-600',weight:'font-semibold'},
  {label:season?'Delivered against season bookings':'Historical delivered units',values:color?.totalDeCitNegoce,tone:'text-plum-600',swatch:'bg-plum-600',weight:'font-normal'},
  {label:'Forecast demand',values:color?.recommendedQty,tone:'text-brand-700',swatch:'bg-brand',weight:'font-semibold'},
  // Not labelled 'Total de LeStock': the report's LeStock is stock + supply − customer orders, a different calculation.
  {label:'Net purchase quantity',values:color?.totalDeLeStock,tone:'text-danger',swatch:'bg-danger',weight:'font-bold'},
 ];
 const legend=measuresFor();
 return <section className={cn('overflow-hidden rounded-[20px] border border-line bg-card',className)}>
  <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-[22px] py-5">
   <div className="flex min-w-0 flex-col gap-1">
    <h3 className="text-[17px] font-bold"><span className="font-mono">{data.productInfo.reference}</span> · {data.productInfo.name}</h3>
    <p className="text-[13px] text-fg-3">{data.productInfo.famille} · {data.productInfo.matiere} · {data.productInfo.saison}</p>
    <p className="mt-1 text-sm text-fg-2"><span className="capitalize">{data.scenario||'base'}</span> scenario · colour and size breakdown</p>
   </div>
   <ConfidenceBadge level={data.confidence} size="sm"/>
  </header>

  <div className="flex flex-wrap items-stretch gap-2.5 px-[22px] py-[18px]">
   {summary.map((item,i)=><Fragment key={item.label}>
    {i>0&&<span aria-hidden className="self-center font-display text-[22px] font-bold text-fg-3">{i===1?'+':'='}</span>}
    <div className={cn('flex flex-[1_1_180px] flex-col gap-1.5 rounded-[14px] border-t-[3px] bg-soft px-4 py-3.5',item.bar)}>
     <span className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
      <span className={cn('text-xs font-semibold',item.text)}>{item.label}</span>
      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-fg-3">{item.term}</span>
     </span>
     <span className="font-display text-[22px] font-bold text-fg-1">{format(item.value)}</span>
    </div>
   </Fragment>)}
  </div>

  <p className="text-pretty px-[22px] pb-4 text-xs leading-relaxed text-fg-3">Forecast units describe demand. Net purchase units require complete stock, supply and delivery inputs. {season?'Recorded bookings and delivered units refer to orders booked within the season. Planned customer deliveries are checked separately for purchasing.':'Open balances and deliveries refer to the older recorded source history.'} Deliveries are not subtracted from current stock. “—” means this colour has no such size; “Unknown” means a required value is missing.</p>

  <ul aria-label="Measures" className="flex flex-wrap gap-x-4 gap-y-2 px-[22px] pb-3.5">
   {legend.map(m=><li key={m.label} className={cn('flex items-center gap-1.5 text-xs font-semibold',m.tone)}><span aria-hidden className={cn('h-2.5 w-2.5 rounded-[3px]',m.swatch)}/>{m.label}</li>)}
  </ul>

  <div className="mx-[22px] mb-[22px] max-h-[520px] overflow-auto rounded-[14px] border border-line">
   <table className="w-full min-w-max border-collapse text-[13px]">
    <thead className="sticky top-0 z-10 bg-soft text-[11px] font-bold uppercase tracking-[0.08em] text-fg-3 shadow-[inset_0_-1px_0_var(--line)]">
     <tr>
      <th scope="col" rowSpan={2} className="min-w-[140px] border-r border-line px-3.5 py-2.5 text-left align-bottom">Colour</th>
      <th scope="col" rowSpan={2} className="min-w-[230px] border-r border-line px-3.5 py-2.5 text-left align-bottom">Measure</th>
      {sizes.length>0&&<th scope="colgroup" colSpan={sizes.length} className="border-b border-line px-3.5 pb-1.5 pt-2.5 text-left">Size</th>}
      <th scope="col" rowSpan={2} className="border-l border-line px-3.5 py-2.5 text-right align-bottom">Total</th>
     </tr>
     <tr>{sizes.map(size=><th key={size} scope="col" className="min-w-16 px-3.5 pb-2.5 pt-1.5 text-right font-mono tracking-normal">{size}</th>)}</tr>
    </thead>
    {data.colorVariants.map(color=>{const measures=measuresFor(color);return <tbody key={color.color} className="border-t-2 border-border-strong first-of-type:border-t-0">
     {measures.map((m,i)=><tr key={m.label} className={cn('hover:bg-brand-50',i>0&&'border-t border-line',m.tone,m.weight)}>
      {i===0&&<th scope="rowgroup" rowSpan={measures.length} className="border-r border-line bg-page px-3.5 py-2.5 text-left align-top font-bold text-fg-1"><span className="flex items-center gap-2"><DropIcon weight="fill" aria-hidden className="h-[13px] w-[13px] shrink-0 text-brand"/>{color.color}</span></th>}
      <th scope="row" className="border-r border-line px-3.5 py-2 text-left font-[inherit]">
       <span className="flex items-center gap-2"><span aria-hidden className={cn('h-2 w-2 shrink-0 rounded-sm',m.swatch)}/><span className="flex flex-col"><span>{m.label}</span>{m.term&&<span className="font-mono text-[10px] font-medium uppercase tracking-[0.04em] text-fg-3">{m.term}</span>}</span></span>
      </th>
      {sizes.map(size=><td key={size} className={cn('px-3.5 py-2 text-right font-mono tabular-nums',!(m.values&&size in m.values)&&'text-fg-4')}>{m.values&&size in m.values?format(m.values[size]):'—'}</td>)}
      <td className="border-l border-line px-3.5 py-2 text-right font-mono font-bold tabular-nums">{format(total(m.values))}</td>
     </tr>)}
    </tbody>;})}
   </table>
  </div>
 </section>;
}
export default SKUStockMatrix;
