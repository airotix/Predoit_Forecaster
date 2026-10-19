"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher} from '@/components/shared';
import {Button} from '@/components/ui/button';
import {useSeasonStore} from '@/store/seasonStore';
import {useDataRefresh} from '@/hooks/useDataRefresh';
import {budgetApi,BuyingSimulation,BuyingReview} from '@/lib/api/budget';

export default function OrderReview(){
 const {activeScenario,activeSeason}=useSeasonStore();
 const [data,setData]=useState<BuyingSimulation|null>(null),[reviews,setReviews]=useState<BuyingReview[]>([]);
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const request=useRef({version:0});
 const load=useCallback(async()=>{const version=++request.current.version;setLoading(true);setError('');setData(null);try{const [draft,history]=await Promise.all([budgetApi.draft(activeScenario),budgetApi.reviews()]);if(version!==request.current.version)return;setData(draft);setReviews(history);}catch(e){if(version===request.current.version)setError(e instanceof Error?e.message:'Could not load the saved draft.');}finally{if(version===request.current.version)setLoading(false);}},[activeScenario]);
 useEffect(()=>{void load();const token=request.current;return()=>{token.version++;};},[load,activeSeason?.id]);useDataRefresh(load);
 const rows=data?.rows.filter(r=>data.draft?.selected.includes(r.id))||[];
 const total=(field:'orderCost'|'orderTurnover'|'orderGrossMargin')=>rows.length&&rows.every(r=>r[field]!=null)?Math.round(rows.reduce((n,r)=>n+(r[field]||0),0)*100)/100:null;
 const money=(n:number|null)=>n==null?'Unknown':new Intl.NumberFormat('en-GB',{style:'currency',currency:data?.currency||'EUR'}).format(n);
 const checks=Array.from(new Set([...(data?.blockers||[]),...rows.flatMap(r=>r.blockers),...(!rows.length?['Select articles in Budget Tracker and save the draft.']:[]),...(!data?.draft?.version?['Save your draft before financial validation.']:[]),...(data?.draft?.stale?['Prices or settings changed. Review and save a new draft version in Budget Tracker.']:[])]));
 const groups=Array.from(new Set(rows.map(r=>r.reference)));
 async function review(){if(!data)return;setSaving(true);setError('');try{const result=await budgetApi.reviewDraft(data);setNotice(`Review ${result.id.slice(0,8)} saved. ${result.notice}`);await load();}catch(e){setError(e instanceof Error?e.message:'Could not validate this draft.');}finally{setSaving(false);}}
 function download(){if(!data)return;
  const cell=(v:unknown)=>'"'+String(v??'').replace(/^[=+@\-\t\r]/,"'$&").replace(/"/g,'""')+'"';
  const csv=[['Status','Forecast run','Draft version','Scenario','Currency','Article','Colour','Size','Quantity','Purchase per unit','Selling per unit ex VAT','Sell-through %','Purchase cost','Expected turnover','Gross margin','Margin %','Checks'],...rows.map(r=>['DRAFT - NOT A PURCHASE ORDER',data.draft?.forecastRun,data.draft?.version,data.scenario,data.currency,r.reference,r.color,r.size,r.quantity,r.orderUnitCost,r.orderUnitPrice,r.sellThrough,r.orderCost,r.orderTurnover,r.orderGrossMargin,r.orderMarginRate,r.blockers.join('; ')])].map(row=>row.map(cell).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`purchase-draft-${data.scenario}-v${data.draft?.version||0}.csv`;a.click();URL.revokeObjectURL(url);
 }
 return <AppShell><div className="space-y-6">
  <header className="flex flex-wrap justify-between gap-4"><div><h1 className="text-2xl font-semibold">Order review</h1><p className="mt-2 text-sm text-slate-500">Review the same saved articles, quantities and price assumptions used in Budget Tracker.</p></div><ScenarioSwitcher/></header>
  {loading&&<p role="status">Loading saved purchase draft…</p>}{error&&<p role="alert" className="rounded border border-red-200 p-4 text-red-800">{error} <Button variant="outline" onClick={()=>void load()}>Reload</Button></p>}{notice&&<p role="status" className="rounded border p-4">{notice}</p>}
  {data&&!loading&&<><div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border p-5"><div><p className="font-semibold">{data.context.season.name} · {data.scenario} · Draft v{data.draft?.version||0}</p><p className="mt-1 text-xs text-slate-500">Forecast {data.draft?.forecastRun.slice(0,8)} · {groups.length} selected articles · {rows.length} variants</p><p className="mt-2 text-sm">Financial validation saves a local review snapshot. Supplier orders are created separately.</p></div><Link className="rounded-lg border px-4 py-2 text-sm" href="/budget">Edit in Budget Tracker</Link></div>
  <section className="grid gap-4 sm:grid-cols-3">{[['Selected purchase cost',money(total('orderCost'))],['Expected turnover',money(total('orderTurnover'))],['Gross margin',money(total('orderGrossMargin'))]].map(([label,value])=><div key={label} className="rounded-xl border p-5"><p className="text-sm text-slate-500">{label}</p><p className="mt-3 text-xl font-semibold">{value}</p></div>)}</section>
  <p className="text-sm text-slate-600">Buying budget {money(data.summary.budget)} · target margin {data.summary.targetMargin}% · known existing commitments {money(data.summary.knownCommitments)}. Checks consider the complete draft and existing commitments.</p>
  {checks.length>0&&<section className="rounded-xl border border-amber-200 bg-amber-50 p-5"><h2 className="font-semibold">Resolve before financial validation</h2><ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{checks.map(check=><li key={check}>{check}</li>)}</ul></section>}
  <div className="flex flex-wrap gap-3"><Button variant="outline" disabled={!rows.length||!!data.draft?.stale||!data.draft?.version} onClick={download}>Download selected draft CSV</Button><Button disabled={saving||!!checks.length} onClick={()=>void review()}>{saving?'Saving review…':'Validate saved draft'}</Button></div>
  <section className="space-y-3">{groups.map(ref=><details key={ref} className="rounded-xl border p-4"><summary className="cursor-pointer font-semibold">{ref} · {rows.find(r=>r.reference===ref)?.name}</summary><div className="mt-4 overflow-auto"><table className="w-full text-sm"><thead><tr>{['Colour','Size','Quantity','Purchase / unit','Selling / unit','Purchase cost','Turnover','Margin'].map(label=><th className="p-2 text-left" key={label}>{label}</th>)}</tr></thead><tbody>{rows.filter(r=>r.reference===ref).map(r=><tr key={r.id} className="border-t"><td className="p-2">{r.color}</td><td className="p-2">{r.size}</td><td className="p-2">{r.quantity??'Unknown'}</td>{[r.orderUnitCost,r.orderUnitPrice,r.orderCost,r.orderTurnover,r.orderGrossMargin].map((n,i)=><td key={i} className="p-2">{money(n)}</td>)}</tr>)}</tbody></table></div></details>)}</section>
  <section className="rounded-xl border p-5"><h2 className="font-semibold">Saved financial reviews</h2><p className="mt-1 text-xs text-slate-500">Each review preserves its original prices, quantities and source. Later edits require a new review.</p>{reviews.filter(r=>r.seasonId===data.context.season.id).map(r=><details key={r.id} className="mt-4 border-t pt-3"><summary className="cursor-pointer text-sm">{new Date(r.createdAt).toLocaleString()} · {r.scenario} · {r.orders.length} variants · {r.forecastRun?.slice(0,8)||'Earlier review'} · v{r.draftVersion??'—'}</summary><p className="mt-2 text-xs">{r.notice}</p><ul className="mt-2 space-y-1 text-xs">{r.orders.map(o=><li key={o.id}>{o.reference} / {o.color} / {o.size} · {o.quantity} units · purchase {o.orderCost??'Unknown'} {r.currency} · turnover {o.orderTurnover??'Unknown'} {r.currency}</li>)}</ul></details>)}{!reviews.some(r=>r.seasonId===data.context.season.id)&&<p className="mt-4 text-sm text-slate-500">No financial reviews saved for this season.</p>}</section>
  </>}
 </div></AppShell>;
}
