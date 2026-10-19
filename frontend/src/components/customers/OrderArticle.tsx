import {ChevronDown,Package} from 'lucide-react';
interface OrderVariant {color:string;size:string;ordered:number|null;delivered:number|null;forecast:number|null;lineCount:number;}
export interface CustomerOrderArticle {orderId:string;date:string;reference:string;name:string;ordered:number|null;delivered:number|null;forecast:number|null;lineCount:number;variants:OrderVariant[];}
const units=(n:number|null)=>n==null?'—':n.toLocaleString('en-GB',{maximumFractionDigits:1});
const sizeOrder=['XXS','XS','S','M','L','XL','XXL','XXXL','XXXXL','UNIQUE','O/S'];
function compareSizes(a:string,b:string){
 const rank=(s:string)=>/^XL\d+$/.test(s)?5+Number(s.slice(2)):sizeOrder.indexOf(s);
 const left=rank(a),right=rank(b);
 return left>=0&&right>=0?left-right:left>=0?-1:right>=0?1:a.localeCompare(b,undefined,{numeric:true});
}
export default function OrderArticle({article}:{article:CustomerOrderArticle}){
 const colors=Array.from(new Set(article.variants.map(v=>v.color)));
 const sizes=Array.from(new Set(article.variants.map(v=>v.size))).sort(compareSizes);
 return <details className="group border-t">
 <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-4 px-4 py-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-900">
 <div className="flex min-w-0 items-center gap-3"><span className="rounded-lg bg-blue-50 p-2 text-blue-600 dark:bg-blue-950"><Package className="h-4 w-4"/></span><div className="min-w-0"><p className="text-sm font-semibold">{article.reference}</p>{article.name&&article.name!==article.reference&&<p className="mt-0.5 truncate text-xs text-slate-600 dark:text-slate-300" title={article.name}>{article.name}</p>}<p className="mt-1 text-xs text-slate-400">{colors.length} colours · {sizes.length} sizes</p></div></div>
 <div className="ml-auto flex shrink-0 items-center gap-5">{([{field:'ordered',label:'Ordered'},{field:'delivered',label:'Delivered'},{field:'forecast',label:'Season forecast'}] as const).map(({field,label})=><div key={field} className="text-right"><p className={`text-[10px] ${field==='forecast'?'text-blue-600 dark:text-blue-400':'text-slate-400'}`}>{label}</p><p className={`text-sm font-medium tabular-nums ${field==='forecast'?'text-blue-700 dark:text-blue-300':''}`}>{units(article[field])}</p>{field==='forecast'&&<p className="text-[9px] text-slate-400">All customers</p>}</div>)}<ChevronDown className="h-4 w-4 text-slate-400 transition-transform group-open:rotate-180"/></div>
 </summary>
 <div className="border-t bg-slate-50/60 p-4 dark:bg-slate-900/50"><p className="mb-3 text-xs font-medium text-slate-500">Colour and size breakdown · order actuals and base season forecast</p>
 <div className="overflow-x-auto rounded-lg border bg-white dark:bg-slate-950"><table className="w-full text-left text-xs"><thead className="bg-slate-50 text-slate-500 dark:bg-slate-900"><tr><th className="px-3 py-2 font-medium">Colour</th><th className="px-3 py-2 font-medium">Quantity</th>{sizes.map(s=><th key={s} className="min-w-12 px-3 py-2 text-right font-medium">{s}</th>)}<th className="px-3 py-2 text-right font-medium">Total</th></tr></thead><tbody>
 {colors.flatMap(color=>(['ordered','delivered','forecast'] as const).map((field,index)=>{
  const variants=article.variants.filter(v=>v.color===color);
  const relevant=field==='forecast'?variants:variants.filter(v=>v.lineCount>0);
  const total=relevant.length&&relevant.every(v=>v[field]!=null)?relevant.reduce((n,v)=>n+(v[field]||0),0):null;
  return <tr key={`${color}-${field}`} className={`${index===0?'border-t ':''}${field==='forecast'?'bg-blue-50/60 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300':''}`}>
   {index===0&&<td rowSpan={3} className="whitespace-nowrap px-3 py-3 align-top font-medium text-foreground">{color}</td>}
   <td className={`whitespace-nowrap px-3 py-2 ${field==='delivered'?'text-emerald-700 dark:text-emerald-400':''}`}>{field==='ordered'?'Ordered':field==='delivered'?'Delivered':'Forecast · all customers'}</td>
   {sizes.map(size=><td key={size} className="px-3 py-2 text-right tabular-nums">{units(variants.find(v=>v.size===size)?.[field]??null)}</td>)}<td className="px-3 py-2 text-right font-semibold tabular-nums">{units(total)}</td>
  </tr>;
 }))}</tbody></table></div>
 <p className="mt-2 text-[10px] leading-4 text-slate-400">Ordered and delivered are this customer’s recorded order quantities. Forecast is total season demand across all customers, including forecast-only colours and sizes. It repeats wherever this article appears; do not add it across orders. — means no recorded quantity or no published prediction.</p></div>
 </details>;
}
