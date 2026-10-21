"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowLeftIcon,ArrowUpRightIcon,ArrowsClockwiseIcon,ClockCounterClockwiseIcon,CurrencyCircleDollarIcon,MagnifyingGlassIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,SelectField,TextField} from '@/components/ui/brand';
import {budgetApi,type PurchasingInputs} from '@/lib/api/budget';
import {useSeasonStore} from '@/store/seasonStore';
import {useDataRefresh} from '@/hooks/useDataRefresh';
import {cn} from '@/lib/utils';

const names:Record<string,string>={purchase:'Purchase costs',selling:'Selling prices',stock:'Warehouse stock',incoming:'Incoming supply',delivery:'Customer deliveries'};
export default function PurchasingData(){
 const {activeScenario,activeSeason}=useSeasonStore();
 const [data,setData]=useState<PurchasingInputs|null>(null),[issue,setIssue]=useState('purchase'),[search,setSearch]=useState(''),[page,setPage]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const sequence=useRef({version:0});
 const load=useCallback(async()=>{const version=++sequence.current.version;setLoading(true);setError('');try{const result=await budgetApi.reconciliation(activeScenario,issue,search,page*25);if(version===sequence.current.version)setData(result);}catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Could not load purchasing input review.');}finally{if(version===sequence.current.version)setLoading(false);}},[activeScenario,issue,search,page]);
 useEffect(()=>{const token=sequence.current;const timer=setTimeout(()=>void load(),200);return()=>{clearTimeout(timer);token.version++;};},[load,activeSeason?.id]);useDataRefresh(load);
 useEffect(()=>setPage(0),[activeScenario,activeSeason?.id]);
 const money=(n:number,currency:string)=>new Intl.NumberFormat('en-GB',{style:'currency',currency,maximumFractionDigits:4}).format(n);
 return <AppShell>
 <Link href="/budget" className="flex items-center gap-1.5 self-start text-sm font-bold text-brand-700 hover:text-brand-800"><ArrowLeftIcon className="h-4 w-4"/>Back to Budget Tracker</Link>
 <PageHeader eyebrow="Purchasing data quality" title="Resolve purchasing inputs" description="See why an input is missing and which saved Joolan evidence can help resolve it."
  actions={<BrandButton variant="outline" disabled={loading} onClick={()=>void load()}><ArrowsClockwiseIcon className={loading?'animate-spin':''}/>Recheck saved data</BrandButton>}/>
 {error&&<Notice tone="danger">{error}</Notice>}
 {data&&<>
  <Notice>{data.notice}</Notice>
  <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">{Object.entries(names).map(([key,name])=><button key={key} type="button" aria-pressed={key===issue} className={cn('flex flex-col gap-2 rounded-[20px] border-[1.5px] p-[18px] text-left text-fg-1 transition-colors hover:border-brand',key===issue?'border-brand bg-brand-soft':'border-line bg-card')} onClick={()=>{setIssue(key);setPage(0);}}><span className="text-[13px] font-semibold text-fg-2">{name}</span><span className="font-display text-[28px] font-bold leading-none">{data.summary[key]?.toLocaleString()}</span></button>)}</div>
  {Object.entries(data.fxPolicy.pairs||{}).map(([pair,proof])=><section key={pair} className="flex items-start gap-3 rounded-2xl bg-plum-50 px-[18px] py-3.5 text-sm leading-relaxed"><CurrencyCircleDollarIcon weight="fill" className="mt-0.5 h-[18px] w-[18px] shrink-0 text-plum-600"/><div><p className="font-bold">Verified recorded-order conversion: {pair.replace('>',' → ')}</p><p className="mt-1 text-fg-2">Budget price = native price ÷ that supplier order’s recorded rate. Verified against {proof.sampleCount} Joolan receipt lines. Original currency, price and rate remain visible. This is a historical planning rate, not a current settlement quote.</p></div></section>)}
  <div className="flex flex-wrap items-center gap-2.5">
   <div className="relative flex flex-[0_1_420px] items-center"><MagnifyingGlassIcon className="pointer-events-none absolute left-3.5 h-4 w-4 text-fg-3"/><TextField aria-label="Search purchasing input issues" className="w-full pl-10" placeholder="Find article, colour or size" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/></div>
   <SelectField aria-label="Purchasing input issue" value={issue} onChange={e=>{setIssue(e.target.value);setPage(0);}}><option value="all">All unresolved inputs</option>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</SelectField>
   <p className="ml-auto text-[13px] text-fg-3">{data.total.toLocaleString()} matching variants · {data.budgetVariants.toLocaleString()} budget variants</p>
  </div>
 </>}
 {loading&&<p role="status" className="flex items-center gap-2.5 text-sm text-fg-3"><ArrowsClockwiseIcon className="h-4 w-4 shrink-0 animate-spin text-brand"/>Checking saved order, price and warehouse evidence…</p>}
 {data&&!loading&&<>
  <section className="flex flex-col gap-3">{data.rows.map(row=><article key={row.id} className="flex flex-col gap-4 rounded-[22px] border border-line bg-card px-[22px] py-5 shadow-card">
   <div className="flex flex-wrap items-start justify-between gap-3"><div className="flex min-w-0 flex-col gap-1"><h2 className="text-base font-bold"><span className="font-mono text-brand-700">{row.reference}</span> <span className="ml-1">{row.name}</span></h2><p className="text-[13px] text-fg-3">{row.color} / {row.size} · draft {row.quantity??'unknown'} units{row.inactive?' · inactive / purchasing blocked':''}</p></div><Link href={`/budget?article=${encodeURIComponent(row.reference)}`} className="flex items-center gap-1 text-sm font-bold text-brand-700 hover:text-brand-800">Review article in Budget Tracker<ArrowUpRightIcon className="h-4 w-4"/></Link></div>
   <dl className="flex flex-col divide-y divide-line overflow-hidden rounded-2xl border border-line">{Object.entries(row.issues).map(([key,reason])=><div key={key} className="grid gap-1 px-4 py-3 text-sm sm:grid-cols-[170px_minmax(0,1fr)] sm:gap-4"><dt className="font-bold">{names[key]}</dt><dd className="text-fg-2">{reason}</dd></div>)}</dl>
   {row.purchaseCost==null&&row.draftPurchaseCost!=null&&<p className="text-xs text-plum-600">Saved draft has {money(row.draftPurchaseCost,data.currency)} per unit. The automatic Catalogue default is still unresolved; draft overrides do not rewrite source data.</p>}
   {row.candidates.length>0&&<div className="rounded-2xl border border-brand-200 bg-brand-50 px-4 py-3.5"><h3 className="flex items-center gap-2 text-sm font-bold"><ClockCounterClockwiseIcon className="h-4 w-4 text-brand-700"/>Historical alternatives requiring supplier confirmation</h3>{row.candidates.map(q=><p key={q.id} className="mt-2 font-mono text-xs">{q.supplier} · {money(q.unitCost,data.currency)} · order {q.order} · {q.date}{q.fx?` · originally ${money(q.fx.nativeUnitCost,q.fx.nativeCurrency)} ÷ ${q.fx.exchangeRate}`:''}</p>)}<p className="mt-3 text-xs text-brand-800">Choose a candidate in Budget Tracker, save the draft, then confirm the supplier and price assumptions with a reason. These alternatives are not automatic defaults.</p></div>}
   {row.otherCurrencyCandidates.length>0&&<div className="rounded-2xl bg-soft px-4 py-3.5 text-xs text-fg-2"><p className="font-bold text-fg-1">Native prices without a usable verified conversion</p>{row.otherCurrencyCandidates.map((q,i)=><p key={i} className="mt-1 font-mono">{money(q.price,q.currency)} · {q.supplier} · order {q.orderId} · {q.orderDate}</p>)}</div>}
   <p className="text-xs leading-relaxed text-fg-3">{row.issues.purchase&&!row.candidates.length?'Confirm the price/currency on the supplier order in Joolan, or obtain a supplier quote and record a reviewed draft price. ':''}{row.issues.stock||row.issues.incoming||row.issues.delivery?'Reconcile the affected SKU, receipt balance or delivery date in Joolan and refresh the source. Historical receipts must not be added to current stock again.':''}</p>
  </article>)}{!data.rows.length&&<p className="rounded-[20px] border border-line bg-card p-6 text-sm text-fg-3">No unresolved inputs match this filter.</p>}</section>
  <footer className="flex flex-wrap items-center justify-between gap-3 text-[13px] text-fg-3"><p>Source through {data.source.historyThrough} · {data.supplierExceptionCount.toLocaleString()} supplier lines require reconciliation</p><div className="flex items-center gap-3"><BrandButton size="sm" variant="outline" disabled={!page} onClick={()=>setPage(v=>v-1)}>Previous</BrandButton><span>Page {page+1} of {Math.max(1,Math.ceil(data.total/25))}</span><BrandButton size="sm" variant="outline" disabled={(page+1)*25>=data.total} onClick={()=>setPage(v=>v+1)}>Next</BrandButton></div></footer>
  <p className="text-xs text-fg-3">This page reads saved data. Recheck does not start a remote export. <Link className="font-semibold text-brand-700 hover:text-brand-800" href="/setup">Open Season Setup to refresh Joolan data</Link>.</p>
 </>}
 </AppShell>;
}
