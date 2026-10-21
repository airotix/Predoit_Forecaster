"use client";
// @refresh reset
import {useEffect,useMemo,useState} from 'react';
import {CaretDownIcon,CaretUpIcon,MagnifyingGlassIcon} from '@phosphor-icons/react';
import {BrandButton} from '@/components/ui/brand-button';
import {Pill,SelectField,TextField} from '@/components/ui/brand';
import {cn} from '@/lib/utils';
import ColourPlanner from './ColourPlanner';
import CheckboxField from './CheckboxField';
import {BuyingEdit,BuyingRow,BuyingSimulation} from '@/lib/api/budget';

const tones:Record<string,'success'|'danger'|'brand'|'neutral'>={included:'success',budget:'danger',margin:'danger',waiting:'brand',zero:'neutral',inactive:'brand'};
export default function ArticlePlanner({simulation,edits,onEdit,disabled,dirty,selected,onSelect}:{simulation:BuyingSimulation;edits:Record<string,BuyingEdit>;onEdit:(row:BuyingRow,key:keyof BuyingEdit,value:string)=>void;disabled:boolean;dirty:boolean;selected:string[];onSelect:(ids:string[],checked:boolean)=>void}){
 const [search,setSearch]=useState('');const [status,setStatus]=useState('');const [open,setOpen]=useState<string|null>(null);const [page,setPage]=useState(0);
 const [articlePrice,setArticlePrice]=useState('');const [articleReason,setArticleReason]=useState('');
 useEffect(()=>{const article=new URLSearchParams(window.location.search).get('article');if(article){setSearch(article);setOpen(article);setPage(0);}},[]);
 const money=(n:number|null)=>n==null?'—':new Intl.NumberFormat('en-GB',{style:'currency',currency:simulation.currency}).format(n);
 const groups=useMemo(()=>{const map=new Map<string,BuyingRow[]>();simulation.rows.forEach(r=>map.set(r.reference,[...(map.get(r.reference)||[]),r]));return map;},[simulation.rows]);
 const articles=simulation.articlePlan.articles.filter(a=>(!status||a.status===status)&&(groups.get(a.reference)||[]).some(r=>`${r.reference} ${r.name} ${r.color} ${r.size}`.toLowerCase().includes(search.toLowerCase())));
 const names:Record<string,string>={included:'Fits draft budget',budget:'Left out: budget',margin:'Below margin target',waiting:'Needs prices / settings',zero:'No order quantity',inactive:'Inactive / purchasing blocked'};
 const fieldLabel='flex flex-col gap-1.5 text-xs font-semibold text-fg-2';
 return <section className="flex flex-col gap-4">
 <div className="flex flex-col gap-1"><h2 className="text-2xl font-extrabold tracking-[-0.02em]">Article order planner</h2><p className="text-sm text-fg-2">One article, all colours and sizes. Start with forecast quantities, then edit your buying assumptions.</p></div>
 <div className="flex flex-wrap items-center gap-2.5">
  <div className="relative flex flex-[0_1_380px] items-center"><MagnifyingGlassIcon className="pointer-events-none absolute left-3.5 h-4 w-4 text-fg-3"/><TextField aria-label="Search articles" className="w-full pl-10" placeholder="Find article, colour or size" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/></div>
  <SelectField aria-label="Budget decision filter" value={status} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">All budget decisions</option>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</SelectField>
  <span className="ml-auto text-sm text-fg-3">{articles.length} articles</span>
 </div>
 <p className="text-xs leading-relaxed text-fg-3">Quantities use the full forecast, rounded up, before stock or incoming-supply deductions. Prices are per unit in {simulation.currency}, selling prices exclude VAT. Edits are draft assumptions and do not change Joolan orders.</p>
 <p className="rounded-[14px] bg-soft px-4 py-3.5 text-sm leading-[1.55]">{simulation.articlePlan.method} {simulation.articlePlan.provisional?'Allocation is provisional because some existing supplier commitments are unresolved.':''} {dirty?'Recalculate to update the decisions below.':''}</p>
 {articles.slice(page*10,(page+1)*10).map(a=>{const rows=groups.get(a.reference)||[];const colors=Array.from(new Set(rows.map(r=>r.color))).sort();const candidates=rows.filter(r=>{const draft=edits[r.id];const quantity=draft&&'quantity' in draft?draft.quantity:r.quantity;return quantity==null||quantity>0;});const isOpen=open===a.reference;return <article key={a.reference} className={cn('overflow-hidden rounded-[22px] border bg-card shadow-card',isOpen?'border-brand-200':'border-line')}>
 <button type="button" className="flex w-full flex-wrap items-center justify-between gap-4 px-[22px] py-[18px] text-left text-fg-1 hover:bg-page" onClick={()=>setOpen(v=>v===a.reference?null:a.reference)} aria-expanded={isOpen}>
  <div className="flex min-w-0 flex-col gap-1"><h3 className="text-base font-bold"><span className="font-mono text-brand-700">{a.reference}</span> <span className="ml-1">{rows[0]?.name}</span></h3><p className="text-[13px] text-fg-3">{rows[0]?.category} · {colors.length} colours · {rows.length} size variants · forecast {Math.ceil(a.forecast)} units · draft {a.quantity} units</p></div>
  <div className="flex items-center gap-4"><div className="flex flex-col items-end"><p className="font-display text-xl font-bold">{money(a.purchaseCost)}</p><p className="text-xs text-fg-3">Whole article purchase cost</p></div><Pill tone={tones[a.status]||'brand'}>{names[a.status]}</Pill>{isOpen?<CaretUpIcon weight="bold" className="h-3.5 w-3.5 text-fg-3"/>:<CaretDownIcon weight="bold" className="h-3.5 w-3.5 text-fg-3"/>}</div>
 </button>
 <div className="border-t border-line px-[22px] py-2.5 text-[13px] text-fg-2">{a.reason}{a.shortfall!=null&&<strong className="ml-2 text-danger">Shortfall {money(a.shortfall)}</strong>}</div>
 {isOpen&&<div className="flex flex-col gap-4 border-t border-line bg-page px-[22px] pb-[22px] pt-5">
  <div className="flex flex-col gap-1.5">
   <CheckboxField className="self-start font-bold" aria-label={`Select article ${a.reference} for PO creation`} disabled={disabled||!candidates.length} checked={candidates.length>0&&candidates.every(r=>selected.includes(r.id))} onChange={e=>onSelect(e.target.checked?candidates.map(r=>r.id):rows.map(r=>r.id),e.target.checked)}>Select whole article for PO creation</CheckboxField>
   <p className="text-xs text-fg-3">Select the article, then create its PO draft. Choose the supplier in the PO editor; final checks happen in Order Validation.{dirty?' Recalculate to review the updated figures.':''}</p>
  </div>
  <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-card px-4 py-3.5"><BrandButton size="sm" variant="outline" disabled={disabled||!rows.some(r=>r.quotes.length)} onClick={()=>rows.filter(r=>r.quotes.length).forEach(r=>onEdit(r,'quoteId',r.quotes[0].id))}>Use saved supplier-order prices for this article</BrandButton><p className="flex-[1_1_320px] text-xs leading-normal text-fg-3">Confirms the latest Catalogue order price where available, otherwise a season supplier-order price. Review each colour and size below. Historical prices are not new supplier quotations; selling prices stay editable.</p></div>
  <div className="flex flex-wrap gap-4">
   <div className="flex flex-[1_1_320px] flex-wrap items-end gap-2.5"><label className={fieldLabel}>Selling price for all colours / sizes ({simulation.currency}, ex VAT)<TextField aria-label="Article selling price" className="h-[42px] w-60 px-3 font-mono" disabled={disabled} type="number" min="0" step="0.01" placeholder="Enter unit selling price" value={articlePrice} onChange={e=>setArticlePrice(e.target.value)}/></label><BrandButton size="sm" variant="outline" className="mb-[5px]" disabled={disabled||articlePrice.trim()===''||!Number.isFinite(Number(articlePrice))||Number(articlePrice)<0} onClick={()=>rows.forEach(r=>onEdit(r,'unitPrice',articlePrice))}>Apply to all sizes</BrandButton><p className="w-full text-xs text-fg-3">Then adjust individual prices below if needed.</p></div>
   <div className="flex flex-[1_1_320px] flex-wrap items-end gap-2.5"><label className={fieldLabel}>Reason for quantity or assumption changes<TextField aria-label="Article adjustment reason" className="h-[42px] w-[300px] max-w-full px-3" disabled={disabled} placeholder="Explain the planning decision" value={articleReason} onChange={e=>setArticleReason(e.target.value)}/></label><BrandButton size="sm" variant="outline" className="mb-[5px]" disabled={disabled||!articleReason.trim()} onClick={()=>rows.forEach(r=>onEdit(r,'reason',articleReason))}>Apply reason to this article</BrandButton></div>
  </div>
  {rows.some(r=>r.requiresAssortmentReview)&&<CheckboxField disabled={disabled} checked={rows.filter(r=>r.requiresAssortmentReview).every(r=>!!edits[r.id]?.assortmentReviewed)} onChange={e=>rows.filter(r=>r.requiresAssortmentReview).forEach(r=>onEdit(r,'assortmentReviewed',String(e.target.checked)))}>I reviewed the launch estimate and recorded my reason above.</CheckboxField>}
  <div className="grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">{[['Purchase cost',money(a.purchaseCost)],['Expected turnover',money(a.turnover)],['Gross margin',money(a.grossMargin)],['Margin rate',a.marginRate==null?'—':`${a.marginRate.toFixed(1)}%`]].map(([name,value])=><div key={name} className="flex flex-col gap-1 rounded-2xl border border-line bg-card px-4 py-3.5"><p className="text-xs text-fg-3">{name}</p><p className={cn('font-display text-xl font-bold',name==='Margin rate'&&a.marginRate!=null&&(a.marginRate<simulation.summary.targetMargin?'text-danger':'text-success-600'))}>{value}</p></div>)}</div>
  <div className="flex flex-col gap-3"><p className="text-xs text-fg-3">Open a colour to select its supplier and review or edit prices and sizes. Save &amp; recalculate to update the figures.</p>{colors.map(color=><ColourPlanner key={`${a.reference}-${color}`} color={color} rows={rows.filter(r=>r.color===color)} suppliers={simulation.context.supplierOptions||[]} currency={simulation.currency} edits={edits} onEdit={onEdit} disabled={disabled}/>)}</div>
  <p className="text-xs text-fg-3">Turnover = order units × sell-through × selling price. Gross margin subtracts the purchase cost of units expected to sell. Unsold units remain inventory.</p>
 </div>}
 </article>;})}
 {!articles.length&&<p className="rounded-[20px] border border-line bg-card p-6 text-sm text-fg-3">No articles match these filters.</p>}
 <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-fg-3">Page {page+1} of {Math.max(1,Math.ceil(articles.length/10))}</p><div className="flex gap-2"><BrandButton variant="outline" disabled={!page} onClick={()=>setPage(v=>v-1)}>Previous</BrandButton><BrandButton variant="outline" disabled={(page+1)*10>=articles.length} onClick={()=>setPage(v=>v+1)}>Next</BrandButton></div></div>
 </section>;
}
