"use client";
import {useEffect,useState} from 'react';
import {BrandButton} from '@/components/ui/brand-button';
import {fetchProductSizeHistory,type ProductRow,type ProductSizeHistory} from '@/lib/api/forecast';

export default function RecentSizeHistory({product}:{product:ProductRow}){
 const [data,setData]=useState<ProductSizeHistory|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{
  let current=true;setLoading(true);setData(null);setError('');
  const [reference,...parts]=product.skuId.split('|');
  fetchProductSizeHistory(reference,parts.join('|')).then(result=>{if(current)setData(result);})
   .catch(reason=>{if(current)setError(reason instanceof Error?reason.message:'Could not load recent size demand.');})
   .finally(()=>{if(current)setLoading(false);});
  return()=>{current=false;};
 },[product,retry]);
 const date=(value:string)=>new Date(`${value}T12:00:00`).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
 const units=(value:number)=>value.toLocaleString('en-GB',{maximumFractionDigits:1});
 const sizes=Object.entries(data?.sizeBreakdown||{}),maxQty=Math.max(0,...sizes.map(([,qty])=>qty));
 return <section aria-label="Size demand in the previous six months" className="flex flex-col gap-2">
  <h4 className="text-[15px] font-bold">Size breakdown · previous 6 months</h4>
  {loading&&<p role="status" className="text-sm text-fg-3">Loading recent size demand…</p>}
  {error&&<div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-danger">{error}<BrandButton variant="outline" size="sm" onClick={()=>setRetry(v=>v+1)}>Retry</BrandButton></div>}
  {data&&!loading&&<figure className="flex flex-col gap-2">
   <p className="text-xs text-fg-3">{date(data.startDate)} – {date(data.endDate)} · {units(data.totalUnits)} booked units</p>
   <div className="flex h-[190px] items-end gap-2.5 overflow-x-auto rounded-[18px] bg-soft p-4">
    {sizes.map(([size,qty])=><div key={size} className="flex h-full min-w-10 flex-1 flex-col items-center justify-end gap-1.5">
     <div className="w-full max-w-14 rounded-b-[4px] rounded-t-[10px] bg-gradient-to-b from-brand-tile to-brand transition-all" style={{height:`${maxQty>0?qty/maxQty*120:0}px`,minHeight:qty>0?4:0}}/>
     <span className="font-mono text-xs font-bold">{size}</span><span className="text-[11px] text-fg-3">{units(qty)}</span>
    </div>)}
    {!sizes.length&&<p className="self-center text-sm text-fg-3">No recorded size demand for this article/colour in this six-month period.</p>}
   </div>
   <figcaption className="text-xs text-fg-3">{data.definition}</figcaption>
  </figure>}
 </section>;
}
