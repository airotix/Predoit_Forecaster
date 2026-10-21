import {CaretDownIcon,PackageIcon} from '@phosphor-icons/react';
import {cn} from '@/lib/utils';
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
 return <details className="group border-t border-line">
 <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-4 px-4 py-3.5 text-fg-1 transition-colors hover:bg-page [&::-webkit-details-marker]:hidden">
 <div className="flex min-w-0 items-center gap-3"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50"><PackageIcon className="h-[17px] w-[17px] text-brand-700"/></span><div className="flex min-w-0 flex-col gap-0.5"><p className="font-mono text-[13px] font-bold">{article.reference}</p>{article.name&&article.name!==article.reference&&<p className="truncate text-[13px] text-fg-2" title={article.name}>{article.name}</p>}<p className="text-xs text-fg-3">{colors.length} colours · {sizes.length} sizes</p></div></div>
 <div className="ml-auto flex shrink-0 items-center gap-5">{([{field:'ordered',label:'Ordered'},{field:'delivered',label:'Delivered'},{field:'forecast',label:'Season forecast'}] as const).map(({field,label})=><div key={field} className="text-right"><p className={cn('text-[10px]',field==='forecast'?'text-plum-600':'text-fg-3')}>{label}</p><p className={cn('font-mono text-sm font-bold tabular-nums',field==='forecast'&&'text-plum-600')}>{units(article[field])}</p>{field==='forecast'&&<p className="text-[9px] text-fg-3">All customers</p>}</div>)}<CaretDownIcon weight="bold" className="h-[13px] w-[13px] text-fg-3 transition-transform group-open:rotate-180"/></div>
 </summary>
 <div className="border-t border-line bg-page px-4 pb-4 pt-3.5"><p className="mb-2.5 text-xs font-semibold text-fg-3">Colour and size breakdown · order actuals and base season forecast</p>
 <div className="overflow-x-auto rounded-xl border border-line bg-card"><table className="w-full text-left text-xs"><thead className="bg-soft font-bold text-fg-3"><tr><th className="px-3 py-[9px] font-bold">Colour</th><th className="px-3 py-[9px] font-bold">Quantity</th>{sizes.map(s=><th key={s} className="min-w-12 px-3 py-[9px] text-right font-mono font-bold">{s}</th>)}<th className="px-3 py-[9px] text-right font-bold">Total</th></tr></thead><tbody>
 {colors.flatMap(color=>(['ordered','delivered','forecast'] as const).map((field,index)=>{
  const variants=article.variants.filter(v=>v.color===color);
  const relevant=field==='forecast'?variants:variants.filter(v=>v.lineCount>0);
  const total=relevant.length&&relevant.every(v=>v[field]!=null)?relevant.reduce((n,v)=>n+(v[field]||0),0):null;
  return <tr key={`${color}-${field}`} className={cn(index===0&&'border-t border-line',field==='delivered'&&'text-success-600',field==='forecast'&&'bg-plum-50 text-plum-600')}>
   {index===0&&<td rowSpan={3} className="whitespace-nowrap bg-card px-3 py-2 align-top font-bold text-fg-1">{color}</td>}
   <td className="whitespace-nowrap px-3 py-2">{field==='ordered'?'Ordered':field==='delivered'?'Delivered':'Forecast · all customers'}</td>
   {sizes.map(size=><td key={size} className="px-3 py-2 text-right font-mono tabular-nums">{units(variants.find(v=>v.size===size)?.[field]??null)}</td>)}<td className="px-3 py-2 text-right font-mono font-bold tabular-nums">{units(total)}</td>
  </tr>;
 }))}</tbody></table></div>
 <p className="mt-2 text-[11px] leading-normal text-fg-3">Ordered and delivered are this customer’s recorded order quantities. Forecast is total season demand across all customers, including forecast-only colours and sizes. It repeats wherever this article appears; do not add it across orders. — means no recorded quantity or no published prediction.</p></div>
 </details>;
}
