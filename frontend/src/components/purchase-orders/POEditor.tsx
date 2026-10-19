"use client";
import {useEffect,useMemo,useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {Download,Save,FileText,ChevronDown} from 'lucide-react';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {downloadPO,purchaseOrdersApi,type PurchaseOrder,type POChanges,type POLine,type POEdit} from '@/lib/api/purchaseOrders';

const inputLabel='text-xs font-medium text-slate-600 dark:text-slate-400';
const sizeRanks=['XXS','XS','S','M','L','XL','XXL','XXXL','UNIQUE','O/S'];
function rank(size:string){if(/^XL\d+$/.test(size))return 5+Number(size.slice(2));const n=sizeRanks.indexOf(size);return n<0?100:n;}

export default function POEditor({order,suppliers,onSaved,onDirtyChange}:{order:PurchaseOrder;suppliers:string[];onSaved:(order:PurchaseOrder)=>void;onDirtyChange:(dirty:boolean)=>void}){
 const router=useRouter();
 const [fields,setFields]=useState<POChanges>({version:order.version});
 const [edits,setEdits]=useState<Record<string,POEdit>>({});const [saving,setSaving]=useState(false),[error,setError]=useState('');
 const [search,setSearch]=useState(''),[page,setPage]=useState(0);
 const dirty=Object.keys(fields).length>1||Object.keys(edits).length>0;const readOnly=order.status==='cancelled'||order.status==='validated';
 useEffect(()=>{onDirtyChange(dirty);const warn=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty,onDirtyChange]);
 const money=(n:number|null)=>n==null?'Unknown':new Intl.NumberFormat('en-GB',{style:'currency',currency:order.currency}).format(n);
 const lines=useMemo(()=>order.lines.map(line=>{const edit=edits[line.id];const result={...line,...edit};if(edit&&'supplierUnitCost' in edit)result.unitCost=edit.supplierUnitCost==null?null:edit.supplierUnitCost/(line.fx?.exchangeRate||1);else if(edit&&'unitCost' in edit)result.supplierUnitCost=edit.unitCost==null?null:edit.unitCost*(line.fx?.exchangeRate||1);return result;}),[order.lines,edits]);
 const groups=useMemo(()=>{const map=new Map<string,POLine[]>();for(const line of lines){const group=map.get(line.reference)||[];group.push(line);map.set(line.reference,group);}return [...map.entries()];},[lines]);
 const articles=groups.filter(([ref,rows])=>`${ref} ${rows[0].name} ${rows.map(r=>r.color).join(' ')}`.toLowerCase().includes(search.toLowerCase()));
 const amounts=lines.map(line=>{const sold=line.quantity==null?null:line.quantity*line.sellThrough/100;
  const cost=line.quantity===0?0:line.quantity==null||line.unitCost==null?null:Math.round(line.quantity*line.unitCost*100)/100;
  const revenue=line.quantity===0?0:sold==null||line.unitPrice==null?null:Math.round(sold*line.unitPrice*100)/100;
  const cogs=line.quantity===0?0:sold==null||line.unitCost==null?null:Math.round(sold*line.unitCost*100)/100;
  return {cost,revenue,margin:revenue==null||cogs==null?null:revenue-cogs};});
 const total=(field:'cost'|'revenue'|'margin')=>amounts.every(a=>a[field]!=null)?Math.round(amounts.reduce((sum,a)=>sum+(a[field]||0),0)*100)/100:null;
 const cost=dirty?total('cost'):order.totals.purchaseCost,revenue=dirty?total('revenue'):order.totals.turnover,margin=dirty?total('margin'):order.totals.grossMargin;const rate=revenue&&margin!=null?margin/revenue*100:null;
 const otherCost=order.status==='cancelled'?order.batch.purchaseCost:order.batch.purchaseCost==null||order.totals.purchaseCost==null?null:order.batch.purchaseCost-order.totals.purchaseCost;
 const balance=otherCost==null||(order.status!=='cancelled'&&cost==null)?null:order.batch.buyingBudget-order.batch.knownCommitments-otherCost-(order.status==='cancelled'?0:cost!);
 function change(id:string,key:'quantity'|'unitCost'|'unitPrice'|'sellThrough'|'supplierUnitCost',value:string){if(key==='sellThrough'&&value.trim()==='')return;setEdits(prev=>{const next={...prev[id],id,[key]:value.trim()===''?null:Number(value)};if(key==='unitCost')delete next.supplierUnitCost;if(key==='supplierUnitCost')delete next.unitCost;return {...prev,[id]:next};});}
 async function save(cancel=false,send=false){setSaving(true);setError('');try{
  let result=dirty||cancel?await purchaseOrdersApi.save(order.id,{...fields,edits:Object.values(edits),...(cancel?{status:'cancelled' as const}:{})}):order;
  if(send)result=await purchaseOrdersApi.submit(order.id,result.version);
  setFields({version:result.version});setEdits({});onSaved(result);
  if(send)router.push(`/validation?po=${encodeURIComponent(result.id)}`);
 }catch(e){setError(e instanceof Error?e.message:'Could not save PO.');}finally{setSaving(false);}}
 async function download(){setError('');try{const file=await purchaseOrdersApi.export(order.id);downloadPO(file.filename,file.csv);}catch(e){setError(e instanceof Error?e.message:'Could not download PO.');}}
 return <section className="min-w-0 space-y-5" aria-label={`Purchase order ${order.number}`}>
 <header className="flex flex-wrap justify-between gap-3 rounded-xl border bg-white p-5 dark:bg-slate-950"><div><p className="text-xs font-medium uppercase tracking-wider text-blue-600">Supplier purchase order</p><h2 className="mt-2 text-xl font-semibold">{order.number}</h2><p className="mt-1 text-xs text-slate-500">{order.status==='cancelled'?'Cancelled':order.status==='validated'?'Validated · not sent':order.status==='pending_validation'?'Awaiting final validation':'Draft · not sent'} · v{order.version} · {order.currency} · Budget draft v{order.budgetVersion} · supplier currency {order.supplierCurrency||order.currency}</p></div><div className="flex flex-wrap gap-2">{!dirty&&!readOnly&&<Link href={`/purchase-orders/${order.id}/print`} target="_blank" className="rounded-lg border px-3 py-2 text-sm">Print / save PDF</Link>}<Button variant="outline" disabled={dirty||saving||readOnly} onClick={()=>void download()}><Download className="mr-2 h-4 w-4"/>Download draft CSV</Button></div></header>
 {error&&<p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
 {order.sourceChanged&&<p className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">Budget inputs or the published forecast have changed. This PO keeps its original snapshot. Compare its quantities and prices with Budget Tracker before using it.</p>}
 {order.supplierCurrency&&order.supplierCurrency!==order.currency&&<p className="rounded-lg border bg-blue-50 p-4 text-sm text-blue-950">Financial totals are in {order.currency}; supplier CSV/PDF prices are in {order.supplierCurrency}. Conversion uses each source order’s recorded rate. Native supplier prices remain editable below. These historical rates are planning assumptions, not current settlement quotes.</p>}
 <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[['Purchase cost',money(cost)],['Expected turnover',money(revenue)],['Gross margin',money(margin)],['Margin rate',rate==null?'Unknown':`${rate.toFixed(1)}%`]].map(([label,value])=><div key={label} className="rounded-xl border bg-white p-4 dark:bg-slate-950"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>)}</div>
 <div className={`rounded-xl border p-4 text-sm ${balance!=null&&balance<0?'border-red-200 bg-red-50 text-red-800':'bg-slate-100 dark:bg-slate-900'}`}><p className="font-medium">Combined PO draft budget</p><p className="mt-2">Buying budget {money(order.batch.buyingBudget)} · other supplier drafts {money(otherCost)} · known Joolan commitments {money(order.batch.knownCommitments)}</p><p className="mt-1">Balance after this PO: <strong>{money(balance)}</strong> · target margin {order.budget.targetMargin}%{!order.batch.commitmentsComplete?' · provisional: some commitments are unresolved.':'.'}{dirty?' Preview only; save for server-checked totals.':''}</p></div>
 <div className="grid gap-4 rounded-xl border bg-white p-5 dark:bg-slate-950 sm:grid-cols-2"><label className={inputLabel}>Supplier<select aria-label="PO supplier" className="mt-2 block w-full rounded-lg border bg-transparent p-3 text-sm" disabled={readOnly||saving} value={fields.supplier??order.supplier} onChange={e=>setFields(v=>({...v,supplier:e.target.value}))}><option value="">Choose a supplier</option>{Array.from(new Set([...suppliers,...(order.supplier?[order.supplier]:[])])).sort().map(supplier=><option key={supplier} value={supplier}>{supplier}</option>)}</select></label><label className={inputLabel}>Deliver to<Input className="mt-2" disabled={readOnly||saving} value={fields.shipTo??order.shipTo} onChange={e=>setFields(v=>({...v,shipTo:e.target.value}))}/></label><label className={inputLabel}>PO date<Input className="mt-2" type="date" disabled={readOnly||saving} value={fields.orderDate??order.orderDate} onChange={e=>setFields(v=>({...v,orderDate:e.target.value}))}/></label><label className={inputLabel}>Requested delivery date · optional<Input className="mt-2" type="date" disabled={readOnly||saving} value={fields.deliveryDate??order.deliveryDate} onChange={e=>setFields(v=>({...v,deliveryDate:e.target.value}))}/></label><label className={`${inputLabel} sm:col-span-2`}>Supplier notes<Input className="mt-2" disabled={readOnly||saving} placeholder="Terms, delivery instructions or supplier reference" value={fields.notes??order.notes} onChange={e=>setFields(v=>({...v,notes:e.target.value}))}/></label><label className={`${inputLabel} sm:col-span-2`}>Reason for quantity or price changes<Input className="mt-2" disabled={readOnly||saving} placeholder="Explain amendments to the Budget Tracker quantities or prices" value={fields.changeReason??order.changeReason} onChange={e=>setFields(v=>({...v,changeReason:e.target.value}))}/></label></div>
 <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">Articles in this PO</h3><p className="mt-1 text-xs text-slate-500">Forecast → saved budget quantity → editable PO quantity. Purchase and selling prices are per unit in {order.currency}. Selling prices exclude VAT.</p></div><Input aria-label="Search PO articles" className="max-w-xs" placeholder="Find article or colour" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/></div>
 <div className="space-y-3">{articles.slice(page*8,(page+1)*8).map(([ref,rows])=>
  <details key={ref} className="overflow-hidden rounded-xl border bg-white dark:bg-slate-950">
   <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4">
    <div><p className="font-semibold">{ref} <span className="ml-2 font-normal">{rows[0].name}</span></p>
     <p className="mt-1 text-xs text-slate-500">{new Set(rows.map(r=>r.color)).size} colours · {rows.length} sizes · {rows.reduce((n,r)=>n+(r.quantity||0),0)} PO units</p></div>
    <ChevronDown className="h-4 w-4 shrink-0"/>
   </summary>
   <div className="space-y-3 border-t p-4">
    <p className="text-xs text-slate-500">Budget decision at import: {rows[0].allocationReason}</p>
    {Array.from(new Set(rows.map(r=>r.color))).sort().map(color=>
     <details key={color} className="overflow-hidden rounded-lg border">
      <summary className="cursor-pointer bg-slate-50 p-3 text-sm font-medium dark:bg-slate-900">{color} · {rows.filter(r=>r.color===color).length} sizes</summary>
      <div className="overflow-x-auto"><table className="w-full min-w-[920px] text-left text-sm">
       <thead className="text-xs text-slate-500"><tr>{['Size','Forecast','Budget qty','PO qty',`Budget purchase / unit (${order.currency})`,`Selling / unit (${order.currency})`,'Sell-through %','Line cost'].map(h=><th key={h} className="p-3">{h}</th>)}</tr></thead>
       <tbody>{rows.filter(r=>r.color===color).sort((a,b)=>rank(a.size)-rank(b.size)||a.size.localeCompare(b.size,undefined,{numeric:true})).map(line=>
        <tr key={line.id} className="border-t align-top">
         <td className="p-3 font-medium">{line.size}</td>
         <td className="p-3">{line.forecast.toLocaleString('en-GB',{maximumFractionDigits:1})}</td>
         <td className="p-3">{line.budgetQuantity}</td>
         {(['quantity','unitCost','unitPrice','sellThrough'] as const).map((key,i)=>
          <td key={key} className="p-3">
           <Input aria-label={`${ref} ${color} ${line.size} ${key}`} className="w-24" type="number" min="0" max={key==='sellThrough'?100:undefined} step={key==='quantity'?1:'0.01'} disabled={readOnly||saving} value={line[key]??''} placeholder="Unknown" onChange={e=>change(line.id,key,e.target.value)}/>
           {i===1&&line.fx&&<label className="mt-3 block text-xs text-blue-700">Supplier cost / unit ({line.fx.nativeCurrency})<Input aria-label={`${ref} ${color} ${line.size} supplier unit cost`} className="mt-1 w-28" type="number" min="0" step="any" disabled={readOnly||saving} value={line.supplierUnitCost??''} onChange={e=>change(line.id,'supplierUnitCost',e.target.value)}/><span className="mt-1 block">Recorded rate: {line.fx.exchangeRate} {line.fx.nativeCurrency} per {order.currency}</span></label>}{i===1&&<p className="mt-1 max-w-36 text-[10px] text-slate-500">{line.unitCost!==line.original.unitCost?'Edited PO price · original: ':''}{line.purchaseSource}</p>}
          </td>)}
         <td className="p-3 whitespace-nowrap">{money(!edits[line.id]?line.purchaseCost:line.quantity===0?0:line.quantity==null||line.unitCost==null?null:line.quantity*line.unitCost)}</td>
        </tr>)}</tbody>
      </table></div>
     </details>)}
   </div>
  </details>)}</div>
 <div className="flex items-center justify-between text-xs text-slate-500"><p>{articles.length} articles · page {page+1} of {Math.max(1,Math.ceil(articles.length/8))}</p><div className="flex gap-2"><Button variant="outline" disabled={!page} onClick={()=>setPage(v=>v-1)}>Previous</Button><Button variant="outline" disabled={(page+1)*8>=articles.length} onClick={()=>setPage(v=>v+1)}>Next</Button></div></div>
 <details className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><summary className="cursor-pointer font-medium">Financial and source checks · {order.checks.length}{dirty?' · based on last save':''}</summary><ul className="mt-3 list-disc space-y-1 pl-5">{order.checks.map(check=><li key={check}>{check}</li>)}</ul><p className="mt-3 text-xs">This is an editable PO draft. Missing amounts remain unknown. Saving or downloading does not approve spending or send an order.</p></details>
 <details className="rounded-xl border p-4 text-xs text-slate-500"><summary className="cursor-pointer font-medium">Source and version history</summary><p className="mt-3">{order.seasonName} · {order.scenario} · forecast {order.forecastRun} · budget draft v{order.budgetVersion}</p><p className="mt-2">Created {new Date(order.createdAt).toLocaleString()} · last saved {new Date(order.updatedAt).toLocaleString()}. PO edits do not overwrite catalogue prices or the Budget Tracker draft.</p><ul className="mt-2 space-y-1">{order.history.map(v=><li key={v.version}>v{v.version} · {new Date(v.updatedAt).toLocaleString()}</li>)}</ul></details>
 {order.status==='validated'&&<Link href={`/validation?po=${order.id}`} className="inline-flex rounded-lg bg-blue-600 px-4 py-3 text-sm text-white">Open validated PO and final downloads</Link>}
 {!readOnly&&<footer className="sticky bottom-3 z-10 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-white p-4 shadow-sm dark:bg-slate-950"><div className="flex items-center gap-2 text-sm"><FileText className="h-4 w-4 text-blue-600"/>{dirty?'Unsaved PO changes':'All PO changes saved'}</div><div className="flex flex-wrap gap-2"><Button variant="outline" disabled={saving||dirty} onClick={()=>void save(true)}>Cancel draft</Button>{dirty&&<Button variant="outline" disabled={saving} onClick={()=>{setFields({version:order.version});setEdits({});}}>Discard changes</Button>}<Button disabled={saving||!dirty} onClick={()=>void save()}><Save className="mr-2 h-4 w-4"/>{saving?'Saving…':'Save PO changes'}</Button><Button disabled={saving||!(fields.supplier??order.supplier).trim()} onClick={()=>void save(false,true)}>Save & send to Order Validation</Button></div></footer>}
 </section>;
}
