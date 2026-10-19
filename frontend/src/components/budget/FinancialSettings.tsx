"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import Link from 'next/link';
import {Card,CardContent,CardHeader,CardTitle} from "@/components/ui/card";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {useSeasonStore} from "@/store/seasonStore";
import {useDataRefresh} from "@/hooks/useDataRefresh";
import {seasonsApi} from "@/lib/api/seasons";
import {budgetApi,type BudgetOptions,type BudgetSettings} from "@/lib/api/budget";

const currencies=['EUR','USD','GBP','CHF','CAD','AUD','PKR'];
export default function FinancialSettings(){
 const {activeSeason}=useSeasonStore();
 const [options,setOptions]=useState<BudgetOptions|null>(null);
 const [mapping,setMapping]=useState<BudgetSettings|null>(null);const [limit,setLimit]=useState('');const [margin,setMargin]=useState('');const [currency,setCurrency]=useState('EUR');
 const [key,setKey]=useState('');const [busy,setBusy]=useState(false);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [notice,setNotice]=useState('');
 const [mappingOpen,setMappingOpen]=useState(false);
 const sequence=useRef({version:0});
 const load=useCallback(async()=>{
  const version=++sequence.current.version;setLoading(true);
  try{const v=await budgetApi.options();if(version===sequence.current.version){setOptions(v);setError('');}}
  catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Could not load settings.');}
  finally{if(version===sequence.current.version)setLoading(false);}
 },[]);
 useEffect(()=>{const token=sequence.current;void load();return()=>{token.version++;};},[load,activeSeason?.id]);useDataRefresh(load);
 const savedSettings=options?JSON.stringify(options.settings):'';
 const savedSeasonId=options?.season.id;const savedBudget=options?.season.budget;const savedMargin=options?.season.targetMargin;const savedCurrency=options?.season.currency;
 useEffect(()=>{if(savedSettings)setMapping(JSON.parse(savedSettings));},[savedSettings,savedSeasonId]);
 useEffect(()=>{if(savedSeasonId&&savedBudget!=null&&savedMargin!=null&&savedCurrency){setLimit(String(savedBudget));setMargin(String(savedMargin));setCurrency(savedCurrency);}},[savedSeasonId,savedBudget,savedMargin,savedCurrency]);
 async function action(fn:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await fn();await load();}catch(e){setError(e instanceof Error?e.message:'Operation failed');}finally{setBusy(false);}}
 function edit<K extends keyof BudgetSettings>(name:K,value:BudgetSettings[K]){setMapping(v=>v?{...v,[name]:value}:v);}
 const selectClass="mt-1 h-10 w-full rounded border bg-background px-3 text-sm";
 return <div className="space-y-4">{error&&<p role="alert" className="text-red-700">{error}</p>}{notice&&<p role="status">{notice}</p>}{loading&&<p>Loading settings…</p>}
 {options&&mapping&&<Card><CardHeader><CardTitle>Season budget and financial settings</CardTitle></CardHeader><CardContent className="space-y-5">
 <p className="text-sm">{options.season.name} · {options.season.startDate} to {options.season.endDate}. Saving financial settings does not retrain the demand model.</p>
 <div className="grid gap-4 md:grid-cols-3"><label>Purchasing budget<Input type="number" min="0" step="0.01" value={limit} onChange={e=>setLimit(e.target.value)}/></label><label>Target gross margin (%)<Input type="number" min="0" max="100" step="0.1" value={margin} onChange={e=>setMargin(e.target.value)}/></label><label>Budget currency<select className={selectClass} value={currency} onChange={e=>setCurrency(e.target.value)}>{currencies.map(c=><option key={c}>{c}</option>)}</select></label></div>
 <Button disabled={busy||limit===''||margin===''||!Number.isFinite(Number(limit))||!Number.isFinite(Number(margin))||Number(limit)<0||Number(margin)<0||Number(margin)>100} onClick={()=>void action(async()=>{
  const season=await seasonsApi.update(options.season.id,{budget:Number(limit),targetMargin:Number(margin),currency});await budgetApi.save({budgetConfigured:true});
  useSeasonStore.setState(s=>({activeSeason:season,seasons:s.seasons.map(v=>v.id===season.id?season:v)}));setNotice('Season budget saved. Draft totals update using the selected scenario.');
 })}>Save seasonal budget</Button>
 <details open={mappingOpen} onToggle={e=>setMappingOpen(e.currentTarget.open)} className="rounded border p-4"><summary className="cursor-pointer font-medium">Map the Joolan price, brand and warehouse inputs</summary><div className="mt-4 space-y-4">
 {options.operatingScope?<p className="rounded border bg-blue-50 p-3 text-sm">Current brands: {mapping.brands.join(', ')}. Normal supply: {mapping.warehouses.join(', ')}. Clearance, faulty and consignment stock stay separate. <Link className="underline" href="/scope">Manage Business Scope</Link></p>:<>
 {options.brands.includes('DAYTONA73')&&options.warehouses.includes('CENTRAL')&&<div className="rounded border p-3 text-sm"><p>For the Daytona 73 plan, you can start with DAYTONA73 and CENTRAL. Verify that CENTRAL supplies your customer orders.</p><Button variant="outline" className="mt-2" disabled={busy} onClick={()=>{setMapping(v=>v?{...v,brands:['DAYTONA73'],warehouses:['CENTRAL']}:v);setNotice('DAYTONA73 / CENTRAL selected in the form. Review and save financial mappings to apply it.');}}>Select DAYTONA73 / CENTRAL</Button></div>}
 <fieldset><legend className="mb-2 font-medium">Brands included in this budget</legend><div className="flex flex-wrap gap-3">{options.brands.map(b=><label key={b} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={mapping.brands.includes(b)} onChange={e=>edit('brands',e.target.checked?[...mapping.brands,b]:mapping.brands.filter(v=>v!==b))}/>{b}</label>)}</div></fieldset>
 <fieldset><legend className="mb-2 font-medium">Supplying warehouses</legend><div className="flex flex-wrap gap-3">{options.warehouses.map(w=><label key={w} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={mapping.warehouses.includes(w)} onChange={e=>edit('warehouses',e.target.checked?[...mapping.warehouses,w]:mapping.warehouses.filter(v=>v!==w))}/>{w}</label>)}</div><p className="mt-2 text-sm text-slate-500">Use supplying warehouses such as CENTRAL; defective, collection and retail stock require their own supply rules.</p></fieldset>
 </>}
 <div className="rounded border bg-slate-50 p-4 text-sm"><p className="font-medium">Prices come from actual Joolan orders</p><p className="mt-2">Purchase: latest valid supplier-order price. Selling: latest valid billable customer-order price in the supplying warehouses, excluding VAT. Currencies come from each order. SKU master prices and selling tariffs are not used as defaults.</p><Link className="mt-2 inline-block text-blue-600 underline" href="/catalogue">Review order references, price dates and manual overrides in Catalogue</Link></div>
 <div className="space-y-2 text-sm"><label className="flex gap-2"><input type="checkbox" checked={mapping.poCostsVerified} onChange={e=>edit('poCostsVerified',e.target.checked)}/>I confirmed supplier prices are before VAT; line and header discounts are sequential percentages.</label><label className="flex gap-2"><input type="checkbox" checked={!!mapping.packRulesVerified} onChange={e=>edit('packRulesVerified',e.target.checked)}/>I confirmed Joolan purchase pack values are order multiples for each size/colour. MOQ and lead times remain separate rules.</label></div>
 <Button disabled={busy||!mapping.brands.length||!mapping.warehouses.length} onClick={()=>void action(async()=>{await budgetApi.save(mapping);setNotice('Financial mappings saved. Known inputs are valued; unresolved rows remain visible.');})}>Save financial mappings</Button>
 </div></details>
 <details className="rounded border p-4"><summary className="cursor-pointer font-medium">Joolan currency-code lookup</summary><div className="mt-3 space-y-3"><p className="text-sm">Observed codes: {options.observedCurrencyCodes.join(', ')||'none'}. This lookup downloads only the currency reference table and retains the completed export.</p>
 {options.currencies.length?<p className="text-sm">{options.currencies.map(c=>`${c.code||'(blank)'} → ${c.iso||'unresolved'} (${c.name})`).join(' · ')}</p>:<p className="text-sm text-amber-800">No currency reference was imported. Codes such as 01 and 02 are not assumed to be EUR.</p>}
 <label className="block max-w-md">Joolan API key<Input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)}/></label><Button disabled={busy||!key.trim()} onClick={()=>void action(async()=>{const result=await budgetApi.currencies(key);setKey('');setNotice(result.notice);})}>Fetch currency labels from Joolan</Button></div></details>
 </CardContent></Card>}
 </div>;
}
