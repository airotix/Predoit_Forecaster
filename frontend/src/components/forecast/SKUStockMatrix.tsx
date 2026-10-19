"use client";
import {cn} from '@/lib/utils';
import {SKUDetailedProjection, SizeData} from '@/types/stockMatrix';
import {ConfidenceBadge} from '@/components/shared';

const format=(v:number|null|undefined)=>v==null?'Unknown':v.toLocaleString(undefined,{maximumFractionDigits:2});
const total=(values:SizeData|undefined)=>{
 const entries=Object.values(values||{});
 return entries.length&&entries.every((v):v is number=>v!==null)?entries.reduce((a,b)=>a+b,0):null;
};
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XL2','XXXL','XL3','XL4','XL5','XL6','XL7'];
export function SKUStockMatrix({data,className}:{data:SKUDetailedProjection;className?:string}){
 const sizes=Array.from(new Set(data.colorVariants.flatMap(c=>Object.keys(c.recommendedQty)))).sort((a,b)=>{
  const ai=sizeOrder.indexOf(a),bi=sizeOrder.indexOf(b);
  return ai>=0&&bi>=0?ai-bi:a.localeCompare(b,undefined,{numeric:true});
 });
 return <section className={cn('rounded-xl border bg-white dark:bg-slate-950 overflow-hidden',className)}>
  <header className="flex flex-wrap items-start justify-between gap-3 border-b p-4">
   <div><h3 className="font-semibold">{data.productInfo.reference} · {data.productInfo.name}</h3>
   <p className="mt-1 text-xs text-slate-500">{data.productInfo.famille} · {data.productInfo.matiere} · {data.productInfo.saison}</p>
   <p className="mt-2 text-sm capitalize">{data.scenario||'base'} scenario · colour and size breakdown</p></div>
   <ConfidenceBadge level={data.confidence} size="sm"/>
  </header>
  <div className="grid gap-4 p-4 sm:grid-cols-3">
   {[['Available warehouse stock',data.stockSummary.stockReel],['Incoming supply',data.stockSummary.fournisseur],['Stock plus incoming supply',data.stockSummary.total]].map(([label,value])=><div key={String(label)}><p className="text-xs text-slate-500">{label}</p><p className="mt-1 font-semibold">{format(value as number|null)}</p></div>)}
  </div>
  <p className="px-4 pb-4 text-xs text-slate-500">Forecast units describe demand. Net purchase units require complete stock, supply and delivery inputs. {data.projectionBasis==='season_bookings'?'Recorded bookings and delivered units refer to orders booked within the season. Planned customer deliveries are checked separately for purchasing.':'Open balances and deliveries refer to the older recorded source history.'} Deliveries are not subtracted from current stock. “—” means this colour has no such size; “Unknown” means a required value is missing.</p>
  <div className="max-h-[520px] overflow-auto"><table className="w-full text-xs">
   <thead className="sticky top-0 bg-slate-100 dark:bg-slate-900"><tr><th className="p-3 text-left">Colour / measure</th>{sizes.map(size=><th key={size} className="min-w-16 p-3 text-right">{size}</th>)}<th className="p-3 text-right">Total</th></tr></thead>
   {data.colorVariants.map(color=><tbody key={color.color} className="border-t">
    <tr className="bg-slate-50 dark:bg-slate-900"><th className="p-3 text-left" colSpan={sizes.length+2}>{color.color}</th></tr>
    {([
     ['Forecast demand',color.recommendedQty],['Available stock',color.availableStock],['Incoming supply',color.totalDeFournisseur],
     ['Net purchase quantity',color.totalDeLeStock],[data.projectionBasis==='season_bookings'?'Season booked units':'Recorded open order balance',color.totalDeProduit],[data.projectionBasis==='season_bookings'?'Delivered against season bookings':'Historical delivered units',color.totalDeCitNegoce],
    ] as [string,SizeData|undefined][]).map(([label,values])=><tr key={label} className="border-t border-slate-100 dark:border-slate-800"><th className="min-w-48 p-3 text-left font-normal">{label}</th>{sizes.map(size=><td key={size} className="p-3 text-right tabular-nums">{values&&size in values?format(values[size]):'—'}</td>)}<td className="p-3 text-right font-semibold tabular-nums">{format(total(values))}</td></tr>)}
   </tbody>)}
  </table></div>
 </section>;
}
export default SKUStockMatrix;
