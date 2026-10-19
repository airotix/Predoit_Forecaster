"use client";
import {useEffect,useState} from 'react';
import {Button} from '@/components/ui/button';
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
 return <section aria-label="Size demand in the previous six months">
  <h4 className="text-sm font-medium">Size breakdown · previous 6 months</h4>
  {loading&&<p role="status" className="mt-3 text-sm text-slate-500">Loading recent size demand…</p>}
  {error&&<div role="alert" className="mt-3 text-sm text-red-700">{error}<Button variant="outline" size="sm" className="ml-2" onClick={()=>setRetry(v=>v+1)}>Retry</Button></div>}
  {data&&!loading&&<figure className="mt-2">
   <p className="mb-3 text-xs text-slate-500">{date(data.startDate)} – {date(data.endDate)} · {units(data.totalUnits)} booked units</p>
   <div className="flex h-44 items-end gap-2 overflow-x-auto rounded-lg bg-slate-50 p-4 dark:bg-slate-900">
    {sizes.map(([size,qty])=><div key={size} className="flex min-w-10 flex-1 flex-col items-center gap-1">
     <div className="w-full rounded-t bg-blue-500 transition-all" style={{height:`${maxQty>0?qty/maxQty*100:0}px`,minHeight:qty>0?4:0}}/>
     <span className="text-xs font-medium">{size}</span><span className="text-xs text-slate-500">{units(qty)}</span>
    </div>)}
    {!sizes.length&&<p className="text-sm text-slate-500">No recorded size demand for this article/colour in this six-month period.</p>}
   </div>
   <figcaption className="mt-2 text-xs text-slate-500">{data.definition}</figcaption>
  </figure>}
 </section>;
}
