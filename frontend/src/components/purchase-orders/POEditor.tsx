"use client";
import {useEffect,useMemo,useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {ArrowRightIcon,CaretDownIcon,CheckCircleIcon,DownloadSimpleIcon,DropIcon,FloppyDiskIcon,MagnifyingGlassIcon,PencilSimpleIcon,PrinterIcon} from '@phosphor-icons/react';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,SelectField,TextField} from '@/components/ui/brand';
import {downloadPO,purchaseOrdersApi,type PurchaseOrder,type POChanges,type POLine,type POEdit,type SellingPricePreview} from '@/lib/api/purchaseOrders';
import {cn} from '@/lib/utils';

const inputLabel='flex flex-col gap-2 text-[13px] font-semibold text-fg-2';
const fieldInput='h-[46px] w-full font-normal';
const summaryReset='cursor-pointer list-none [&::-webkit-details-marker]:hidden';
const cell='px-[5px] py-2.5 align-top first:pl-4 last:pr-4';
const colWidths=['w-[70px]','w-[90px]','w-[90px]','w-[120px]','','w-[140px]','w-[120px]','w-[120px]'];
const sizeRanks=['XXS','XS','S','M','L','XL','XXL','XXXL','UNIQUE','O/S'];
function rank(size:string){if(/^XL\d+$/.test(size))return 5+Number(size.slice(2));const n=sizeRanks.indexOf(size);return n<0?100:n;}

export default function POEditor({order,suppliers,onSaved,onDirtyChange}:{order:PurchaseOrder;suppliers:string[];onSaved:(order:PurchaseOrder)=>void;onDirtyChange:(dirty:boolean)=>void}){
 const router=useRouter();
 const [fields,setFields]=useState<POChanges>({version:order.version});
 const [edits,setEdits]=useState<Record<string,POEdit>>({});const [saving,setSaving]=useState(false),[error,setError]=useState('');
 const [search,setSearch]=useState(''),[page,setPage]=useState(0);
 const [pricePreview,setPricePreview]=useState<SellingPricePreview|null>(null),[pricesLoading,setPricesLoading]=useState(false);
 const [bulkPrices,setBulkPrices]=useState<Record<string,string>>({});
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
  setFields({version:result.version});setEdits({});setBulkPrices({});setPricePreview(null);onSaved(result);
  if(send)router.push(`/validation?po=${encodeURIComponent(result.id)}`);
 }catch(e){setError(e instanceof Error?e.message:'Could not save PO.');}finally{setSaving(false);}}
 async function download(){setError('');try{const file=await purchaseOrdersApi.export(order.id);downloadPO(file.filename,file.csv);}catch(e){setError(e instanceof Error?e.message:'Could not download PO.');}}
 async function refreshSellingPrices(){setPricesLoading(true);setError('');try{setPricePreview(await purchaseOrdersApi.sellingPrices(order.id));}catch(e){setError(e instanceof Error?e.message:'Could not read saved selling prices.');}finally{setPricesLoading(false);}}
 const missing=lines.filter(line=>line.quantity!==0&&(line.quantity==null||line.unitCost==null||line.unitPrice==null));
 const supplier=fields.supplier??order.supplier;
 const edited=(id:string,key:keyof POEdit)=>!!edits[id]&&key in edits[id];
 return <section className="flex min-w-0 flex-col gap-[18px]" aria-label={`Purchase order ${order.number}`}>
 <header className="flex flex-wrap justify-between gap-3.5 rounded-3xl border border-line bg-card px-6 py-[22px] shadow-card">
  <div className="flex min-w-0 flex-col gap-1"><p className="text-xs font-bold uppercase tracking-[0.12em] text-brand">Supplier purchase order</p><h2 className="font-mono text-2xl font-bold">{order.number}</h2><p className="text-[13px] text-fg-3">{order.status==='cancelled'?'Cancelled':order.status==='validated'?'Validated · not sent':order.status==='pending_validation'?'Awaiting final validation':'Draft · not sent'} · v{order.version} · {order.currency} · Budget draft v{order.budgetVersion} · supplier currency {order.supplierCurrency||order.currency}</p></div>
  <div className="flex flex-wrap items-center gap-2">{!dirty&&!readOnly&&<BrandButton asChild variant="outline" size="sm"><Link href={`/purchase-orders/${order.id}/print`} target="_blank"><PrinterIcon/>Print / save PDF</Link></BrandButton>}<BrandButton variant="outline" size="sm" disabled={dirty||saving||readOnly} onClick={()=>void download()}><DownloadSimpleIcon/>Download draft CSV</BrandButton></div>
 </header>
 {error&&<Notice tone="danger">{error}</Notice>}
 {!readOnly&&<div className="flex flex-wrap items-center gap-3"><BrandButton variant="outline" disabled={dirty||saving||pricesLoading} onClick={()=>void refreshSellingPrices()}>{pricesLoading?'Reading saved prices…':'Refresh selling prices from Budget / Catalogue'}</BrandButton><p className="text-xs text-fg-3">Preview changes first. Manual PO prices are kept.</p></div>}
 {pricePreview&&<Notice tone="brand"><p>{pricePreview.changes.length} prices can be updated · {pricePreview.protectedOverrides} manual PO overrides retained.</p>{pricePreview.changes.map(item=><p key={item.id} className="text-xs">{item.reference} / {item.color} / {item.size}: {money(item.previous)} → {money(item.unitPrice)} · {item.source}</p>)}<div className="mt-2 flex gap-2"><BrandButton size="sm" disabled={!pricePreview.changes.length||dirty||pricePreview.version!==order.version} onClick={()=>{setEdits(Object.fromEntries(pricePreview.changes.map(p=>[p.id,{id:p.id,unitPrice:p.unitPrice}])));setFields(v=>({...v,changeReason:v.changeReason||order.changeReason||'Updated selling prices from saved Budget / Catalogue after reviewing the preview.'}));setPricePreview(null);}}>Apply to draft</BrandButton><BrandButton size="sm" variant="outline" onClick={()=>setPricePreview(null)}>Close preview</BrandButton></div><p className="mt-2 text-xs">If no price is available, enter it below. Save PO changes to keep applied prices.</p></Notice>}
 {order.sourceChanged&&<Notice tone="brand">Budget inputs or the published forecast have changed. This PO keeps its original snapshot. Compare its quantities and prices with Budget Tracker before using it.</Notice>}
 {order.supplierCurrency&&order.supplierCurrency!==order.currency&&<p className="rounded-2xl bg-plum-50 px-[18px] py-3.5 text-sm leading-[1.55] text-fg-1">Financial totals are in {order.currency}; supplier CSV/PDF prices are in {order.supplierCurrency}. Conversion uses each source order’s recorded rate. Native supplier prices remain editable below. These historical rates are planning assumptions, not current settlement quotes.</p>}
 <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">{[['Purchase cost',money(cost)],['Expected turnover',money(revenue)],['Gross margin',money(margin)],['Margin rate',rate==null?'Unknown':`${rate.toFixed(1)}%`]].map(([label,value])=><div key={label} className="flex flex-col gap-1.5 rounded-[20px] border border-line bg-card p-[18px] shadow-card"><p className="text-[13px] text-fg-3">{label}</p><p className="font-display text-2xl font-bold tracking-[-0.01em]">{value}</p></div>)}</div>
 {missing.length>0&&<Notice tone="brand"><p className="font-semibold">Totals need inputs for {missing.length} variants:</p>{missing.slice(0,10).map(line=><p key={line.id} className="text-xs">{line.reference} / {line.color} / {line.size}: {[line.quantity==null?'order quantity':null,line.unitCost==null?'purchase price':null,line.unitPrice==null?'selling price':null].filter(Boolean).join(', ')}.</p>)}{missing.length>10&&<p>And {missing.length-10} more variants.</p>}<p className="mt-1 text-xs">Enter prices on each size, or type a price for the whole article or colour below. Totals preview immediately; save to retain them.</p></Notice>}
 <div className={cn('rounded-[18px] px-[18px] py-4 text-sm leading-relaxed text-fg-1',balance!=null&&balance<0?'bg-danger-soft':'bg-soft')}><p className="font-bold">Combined PO draft budget</p><p className="mt-1 text-fg-2">Buying budget {money(order.batch.buyingBudget)} · other supplier drafts {money(otherCost)} · known Joolan commitments {money(order.batch.knownCommitments)}</p><p className="mt-1">Balance after this PO: <strong className={cn('font-mono',balance!=null&&balance<0&&'text-danger')}>{money(balance)}</strong> · target margin {order.budget.targetMargin}%{!order.batch.commitmentsComplete?' · provisional: some commitments are unresolved.':'.'}{dirty?' Preview only; save for server-checked totals.':''}</p></div>
 <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3.5 rounded-3xl border border-line bg-card px-6 py-[22px] shadow-card">
  <label className={inputLabel}>Supplier<SelectField strong aria-label="PO supplier" wrapperClassName="w-full" className={cn('h-[46px]',!supplier&&'border-brand-200')} disabled={readOnly||saving} value={supplier} onChange={e=>setFields(v=>({...v,supplier:e.target.value}))}><option value="">Choose a supplier</option>{Array.from(new Set([...suppliers,...(order.supplier?[order.supplier]:[])])).sort().map(s=><option key={s} value={s}>{s}</option>)}</SelectField></label>
  <label className={inputLabel}>Deliver to<TextField className={fieldInput} disabled={readOnly||saving} value={fields.shipTo??order.shipTo} onChange={e=>setFields(v=>({...v,shipTo:e.target.value}))}/></label>
  <label className={inputLabel}>PO date<TextField className={fieldInput} type="date" disabled={readOnly||saving} value={fields.orderDate??order.orderDate} onChange={e=>setFields(v=>({...v,orderDate:e.target.value}))}/></label>
  <label className={inputLabel}>Requested delivery date · optional<TextField className={fieldInput} type="date" disabled={readOnly||saving} value={fields.deliveryDate??order.deliveryDate} onChange={e=>setFields(v=>({...v,deliveryDate:e.target.value}))}/></label>
  <label className={cn(inputLabel,'col-span-full')}>Supplier notes<TextField className={fieldInput} disabled={readOnly||saving} placeholder="Terms, delivery instructions or supplier reference" value={fields.notes??order.notes} onChange={e=>setFields(v=>({...v,notes:e.target.value}))}/></label>
  <label className={cn(inputLabel,'col-span-full')}>Reason for quantity or price changes<TextField className={fieldInput} disabled={readOnly||saving} placeholder="Explain amendments to the Budget Tracker quantities or prices" value={fields.changeReason??order.changeReason} onChange={e=>setFields(v=>({...v,changeReason:e.target.value}))}/></label>
 </div>
 <div className="flex flex-wrap items-end justify-between gap-3">
  <div className="flex flex-col gap-1"><h3 className="text-xl font-extrabold tracking-[-0.02em]">Articles in this PO</h3><p className="text-pretty text-[13px] text-fg-3">Forecast → saved budget quantity → editable PO quantity. Purchase and selling prices are per unit in {order.currency}. Selling prices exclude VAT.</p></div>
  <div className="relative flex w-full items-center sm:w-[260px]"><MagnifyingGlassIcon className="absolute left-3.5 h-4 w-4 text-fg-3"/><TextField aria-label="Search PO articles" className="w-full pl-10" placeholder="Find article or colour" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/></div>
 </div>
 <div className="flex flex-col gap-3">{articles.slice(page*8,(page+1)*8).map(([ref,rows])=>
  <details key={ref} className="group/art overflow-hidden rounded-[20px] border border-line bg-card shadow-card open:border-brand-200">
   <summary className={cn(summaryReset,'flex items-center justify-between gap-3 px-5 py-4 text-fg-1 hover:bg-page')}>
    <div className="flex min-w-0 flex-col gap-[3px]"><p className="text-[15px] font-bold"><span className="font-mono text-brand-700">{ref}</span> <span className="ml-1">{rows[0].name}</span></p>
     <p className="text-xs text-fg-3">{new Set(rows.map(r=>r.color)).size} colours · {rows.length} sizes · {rows.reduce((n,r)=>n+(r.quantity||0),0)} PO units</p></div>
    <CaretDownIcon weight="bold" className="h-[13px] w-[13px] shrink-0 text-fg-3 transition-transform group-open/art:rotate-180"/>
   </summary>
   <div className="flex flex-col gap-3 border-t border-line bg-page px-5 pb-5 pt-3.5">
    <p className="text-xs text-fg-3">Budget decision at import: {rows[0].allocationReason}</p>
    {!readOnly&&<label className={inputLabel}>Selling price for all colours / sizes ({order.currency}, ex VAT)<TextField aria-label={`${ref} selling price for all sizes`} className="max-w-60" type="number" min="0" step="0.01" disabled={saving} value={bulkPrices[ref]??''} placeholder="Apply unit selling price" onChange={e=>{const value=e.target.value;setBulkPrices(p=>({...p,[ref]:value}));if(value.trim()!==''&&Number.isFinite(Number(value))&&Number(value)>=0)rows.forEach(line=>change(line.id,'unitPrice',value));}}/><span className="text-xs font-normal text-fg-3">Typing a valid price applies it immediately. Save PO changes to keep it.</span></label>}

    {Array.from(new Set(rows.map(r=>r.color))).sort().map(color=>
     <details key={color} open className="group/col overflow-hidden rounded-2xl border border-line bg-card">
      <summary className={cn(summaryReset,'flex items-center justify-between gap-3 bg-brand-50 px-4 py-3 text-sm font-bold text-fg-1')}><span className="flex items-center gap-2"><DropIcon weight="fill" className="h-[13px] w-[13px] text-brand"/>{color} · {rows.filter(r=>r.color===color).length} sizes</span><CaretDownIcon weight="bold" className="h-3 w-3 shrink-0 transition-transform group-open/col:rotate-180"/></summary>
      {!readOnly&&<label className="m-4 flex max-w-60 flex-col gap-1 text-xs font-semibold">Selling price for {color} ({order.currency}, ex VAT)<TextField aria-label={`${ref} ${color} selling price for all sizes`} type="number" min="0" step="0.01" disabled={saving} value={bulkPrices[`${ref}|${color}`]??''} placeholder="Apply to this colour" onChange={e=>{const value=e.target.value;setBulkPrices(p=>({...p,[`${ref}|${color}`]:value}));if(value.trim()!==''&&Number.isFinite(Number(value))&&Number(value)>=0)rows.filter(line=>line.color===color).forEach(line=>change(line.id,'unitPrice',value));}}/></label>}
      <div className="overflow-x-auto"><table className="w-full min-w-[940px] text-left text-sm">
       <thead><tr className="bg-page text-[10px] uppercase tracking-[0.08em] text-fg-3">{['Size','Forecast','Budget qty','PO qty',`Budget purchase / unit (${order.currency})`,`Selling / unit (${order.currency})`,'Sell-through %','Line cost'].map((h,i)=><th key={h} className={cn(cell,colWidths[i],'align-bottom font-bold',i===7&&'text-right')}>{h}</th>)}</tr></thead>
       <tbody>{rows.filter(r=>r.color===color).sort((a,b)=>rank(a.size)-rank(b.size)||a.size.localeCompare(b.size,undefined,{numeric:true})).map(line=>
        <tr key={line.id} className="border-t border-line">
         <td className={cn(cell,'pt-[19px] font-mono font-bold')}>{line.size}</td>
         <td className={cn(cell,'pt-[19px] font-mono')}>{line.forecast.toLocaleString('en-GB',{maximumFractionDigits:1})}</td>
         <td className={cn(cell,'pt-[19px] font-mono text-fg-2')}>{line.budgetQuantity}</td>
         {(['quantity','unitCost','unitPrice','sellThrough'] as const).map((key,i)=>
          <td key={key} className={cell}><div className="flex flex-col gap-1">
           <TextField strong={false} aria-label={`${ref} ${color} ${line.size} ${key}`} className={cn('h-[38px] w-[100px] rounded-[10px] px-2.5 text-right font-mono text-[13px] font-bold',edited(line.id,key)&&'border-brand')} type="number" min="0" max={key==='sellThrough'?100:undefined} step={key==='quantity'?1:'0.01'} disabled={readOnly||saving} value={line[key]??''} placeholder="Unknown" onChange={e=>change(line.id,key,e.target.value)}/>
           {i===1&&line.fx&&<label className="mt-2 flex max-w-[170px] flex-col gap-1 text-[11px] leading-[1.4] text-plum-600">Supplier cost / unit ({line.fx.nativeCurrency})<TextField strong={false} aria-label={`${ref} ${color} ${line.size} supplier unit cost`} className={cn('h-[38px] w-28 rounded-[10px] px-2.5 text-right font-mono text-[13px] font-bold',edited(line.id,'supplierUnitCost')&&'border-brand')} type="number" min="0" step="any" disabled={readOnly||saving} value={line.supplierUnitCost??''} onChange={e=>change(line.id,'supplierUnitCost',e.target.value)}/><span>Recorded rate: {line.fx.exchangeRate} {line.fx.nativeCurrency} per {order.currency}</span></label>}{i===1&&<p className="max-w-[170px] text-[10px] leading-[1.4] text-fg-3">{line.unitCost!==line.original.unitCost?'Edited PO price · original: ':''}{line.purchaseSource}</p>}
          </div></td>)}
         <td className={cn(cell,'whitespace-nowrap pt-[19px] text-right font-mono font-bold')}>{money(!edits[line.id]?line.purchaseCost:line.quantity===0?0:line.quantity==null||line.unitCost==null?null:line.quantity*line.unitCost)}</td>
        </tr>)}</tbody>
      </table></div>
     </details>)}
   </div>
  </details>)}</div>
 <div className="flex flex-wrap items-center justify-between gap-3 text-[13px] text-fg-3"><p>{articles.length} articles · page {page+1} of {Math.max(1,Math.ceil(articles.length/8))}</p><div className="flex gap-2"><BrandButton variant="outline" size="sm" disabled={!page} onClick={()=>setPage(v=>v-1)}>Previous</BrandButton><BrandButton variant="outline" size="sm" disabled={(page+1)*8>=articles.length} onClick={()=>setPage(v=>v+1)}>Next</BrandButton></div></div>
 <details className="group/checks rounded-[18px] border border-brand-200 bg-brand-50 px-[18px] text-fg-1"><summary className={cn(summaryReset,'flex items-center justify-between gap-3 py-3.5 text-sm font-bold')}>Financial and source checks · {order.checks.length}{dirty?' · based on last save':''}<CaretDownIcon weight="bold" className="h-3 w-3 shrink-0 transition-transform group-open/checks:rotate-180"/></summary><div className="pb-4 text-[13px] leading-[1.55]"><ul className="list-disc space-y-1 pl-5">{order.checks.map(check=><li key={check}>{check}</li>)}</ul><p className="mt-2.5 text-xs text-fg-2">This is an editable PO draft. Missing amounts remain unknown. Saving or downloading does not approve spending or send an order.</p></div></details>
 <details className="group/history rounded-[18px] border border-line bg-card px-[18px] text-fg-1"><summary className={cn(summaryReset,'flex items-center justify-between gap-3 py-3.5 text-sm font-bold')}>Source and version history<CaretDownIcon weight="bold" className="h-3 w-3 shrink-0 transition-transform group-open/history:rotate-180"/></summary><div className="flex flex-col gap-1.5 pb-4 text-xs leading-[1.55] text-fg-3"><p>{order.seasonName} · {order.scenario} · forecast {order.forecastRun} · budget draft v{order.budgetVersion}</p><p>Created {new Date(order.createdAt).toLocaleString()} · last saved {new Date(order.updatedAt).toLocaleString()}. PO edits do not overwrite catalogue prices or the Budget Tracker draft.</p><ul className="flex flex-col gap-1 font-mono">{order.history.map(v=><li key={v.version}>v{v.version} · {new Date(v.updatedAt).toLocaleString()}</li>)}</ul></div></details>
 {order.status==='validated'&&<div><BrandButton asChild><Link href={`/validation?po=${order.id}`}>Open validated PO and final downloads<ArrowRightIcon/></Link></BrandButton></div>}
 {!readOnly&&<footer className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-line bg-card py-3.5 pl-5 pr-4 shadow-lift">
  <p className="flex items-center gap-2 text-sm font-semibold">{dirty?<PencilSimpleIcon weight="fill" className="h-[17px] w-[17px] text-brand-700"/>:<CheckCircleIcon weight="fill" className="h-[17px] w-[17px] text-success-600"/>}{dirty?'Unsaved PO changes':'All PO changes saved'}</p>
  <div className="flex flex-wrap gap-2"><BrandButton variant="outline" disabled={saving||dirty} onClick={()=>void save(true)}>Cancel draft</BrandButton>{dirty&&<BrandButton variant="outline" disabled={saving} onClick={()=>{setFields({version:order.version});setEdits({});setBulkPrices({});setPricePreview(null);}}>Discard changes</BrandButton>}<BrandButton variant="dark" disabled={saving||!dirty} onClick={()=>void save()}><FloppyDiskIcon/>{saving?'Saving…':'Save PO changes'}</BrandButton><BrandButton disabled={saving||!supplier.trim()} onClick={()=>void save(false,true)}>Save & send to Order Validation</BrandButton></div>
 </footer>}
 </section>;
}
