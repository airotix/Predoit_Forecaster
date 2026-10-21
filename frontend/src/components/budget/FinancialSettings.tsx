"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import Link from 'next/link';
import {CaretDownIcon} from '@phosphor-icons/react';
import {BrandButton} from "@/components/ui/brand-button";
import {Notice,SelectField,TextField} from "@/components/ui/brand";
import {useSeasonStore} from "@/store/seasonStore";
import {useDataRefresh} from "@/hooks/useDataRefresh";
import {seasonsApi} from "@/lib/api/seasons";
import {budgetApi,type BudgetOptions,type BudgetSettings} from "@/lib/api/budget";
import CheckboxField from './CheckboxField';

const currencies=['EUR','USD','GBP','CHF','CAD','AUD','PKR'];
const fieldLabel="flex flex-col gap-2 text-[13px] font-semibold text-fg-2";
const panel="overflow-hidden rounded-[18px] border border-line";
const panelSummary="flex cursor-pointer list-none items-center justify-between gap-3 bg-page px-[18px] py-4 text-[15px] font-bold text-fg-1 [&::-webkit-details-marker]:hidden";
const caret="h-[13px] w-[13px] shrink-0 transition-transform";
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
 return <div className="flex flex-col gap-5">{error&&<Notice tone="danger">{error}</Notice>}{notice&&<Notice tone="success">{notice}</Notice>}{loading&&<p role="status" className="text-sm text-fg-3">Loading settings…</p>}
 {options&&mapping&&<div className="flex flex-col gap-5">
 <div className="flex flex-col gap-1.5"><h2 className="text-[22px] font-extrabold tracking-[-0.02em]">Season budget and financial settings</h2><p className="text-sm text-fg-2">{options.season.name} · {options.season.startDate} to {options.season.endDate}. Saving financial settings does not retrain the demand model.</p></div>
 <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3.5"><label className={fieldLabel}>Purchasing budget<TextField className="h-[46px] font-mono text-[15px]" type="number" min="0" step="0.01" value={limit} onChange={e=>setLimit(e.target.value)}/></label><label className={fieldLabel}>Target gross margin (%)<TextField className="h-[46px] font-mono text-[15px]" type="number" min="0" max="100" step="0.1" value={margin} onChange={e=>setMargin(e.target.value)}/></label><label className={fieldLabel}>Budget currency<SelectField strong wrapperClassName="w-full" className="h-[46px] text-[15px]" value={currency} onChange={e=>setCurrency(e.target.value)}>{currencies.map(c=><option key={c}>{c}</option>)}</SelectField></label></div>
 <div><BrandButton disabled={busy||limit===''||margin===''||!Number.isFinite(Number(limit))||!Number.isFinite(Number(margin))||Number(limit)<0||Number(margin)<0||Number(margin)>100} onClick={()=>void action(async()=>{
  const season=await seasonsApi.update(options.season.id,{budget:Number(limit),targetMargin:Number(margin),currency});await budgetApi.save({budgetConfigured:true});
  useSeasonStore.setState(s=>({activeSeason:season,seasons:s.seasons.map(v=>v.id===season.id?season:v)}));setNotice('Season budget saved. Draft totals update using the selected scenario.');
 })}>Save seasonal budget</BrandButton></div>
 <details open={mappingOpen} onToggle={e=>setMappingOpen(e.currentTarget.open)} className={`group/map ${panel}`}><summary className={panelSummary}>Map the Joolan price, brand and warehouse inputs<CaretDownIcon weight="bold" className={`${caret} group-open/map:rotate-180`}/></summary><div className="flex flex-col gap-3.5 p-[18px]">
 {options.operatingScope?<p className="rounded-[14px] bg-plum-50 px-4 py-3.5 text-sm leading-[1.55]">Current brands: {mapping.brands.join(', ')}. Normal supply: {mapping.warehouses.join(', ')}. Clearance, faulty and consignment stock stay separate. <Link className="font-bold text-brand-700 hover:text-brand-800" href="/scope">Manage Business Scope</Link></p>:<>
 {options.brands.includes('DAYTONA73')&&options.warehouses.includes('CENTRAL')&&<div className="flex flex-col items-start gap-2.5 rounded-[14px] border border-line px-4 py-3.5 text-sm leading-[1.55]"><p>For the Daytona 73 plan, you can start with DAYTONA73 and CENTRAL. Verify that CENTRAL supplies your customer orders.</p><BrandButton size="sm" variant="outline" disabled={busy} onClick={()=>{setMapping(v=>v?{...v,brands:['DAYTONA73'],warehouses:['CENTRAL']}:v);setNotice('DAYTONA73 / CENTRAL selected in the form. Review and save financial mappings to apply it.');}}>Select DAYTONA73 / CENTRAL</BrandButton></div>}
 <fieldset><legend className="mb-2.5 text-sm font-bold">Brands included in this budget</legend><div className="flex flex-wrap gap-x-5 gap-y-2.5">{options.brands.map(b=><CheckboxField key={b} className="font-mono text-[13px] font-semibold" checked={mapping.brands.includes(b)} onChange={e=>edit('brands',e.target.checked?[...mapping.brands,b]:mapping.brands.filter(v=>v!==b))}>{b}</CheckboxField>)}</div></fieldset>
 <fieldset><legend className="mb-2.5 text-sm font-bold">Supplying warehouses</legend><div className="flex flex-wrap gap-x-5 gap-y-2.5">{options.warehouses.map(w=><CheckboxField key={w} className="font-mono text-[13px] font-semibold" checked={mapping.warehouses.includes(w)} onChange={e=>edit('warehouses',e.target.checked?[...mapping.warehouses,w]:mapping.warehouses.filter(v=>v!==w))}>{w}</CheckboxField>)}</div><p className="mt-2.5 text-[13px] text-fg-3">Use supplying warehouses such as CENTRAL; defective, collection and retail stock require their own supply rules.</p></fieldset>
 </>}
 <div className="rounded-[14px] bg-soft px-4 py-3.5 text-sm leading-[1.55]"><p className="font-bold">Prices come from actual Joolan orders</p><p className="mt-1.5 text-fg-2">Purchase: latest valid supplier-order price. Selling: latest valid billable customer-order price in the supplying warehouses, excluding VAT. Currencies come from each order. SKU master prices and selling tariffs are not used as defaults.</p><Link className="mt-1.5 inline-block font-bold text-brand-700 hover:text-brand-800" href="/catalogue">Review order references, price dates and manual overrides in Catalogue</Link></div>
 <div className="flex flex-col gap-3"><CheckboxField checked={mapping.poCostsVerified} onChange={e=>edit('poCostsVerified',e.target.checked)}>I confirmed supplier prices are before VAT; line and header discounts are sequential percentages.</CheckboxField><CheckboxField checked={!!mapping.packRulesVerified} onChange={e=>edit('packRulesVerified',e.target.checked)}>I confirmed Joolan purchase pack values are order multiples for each size/colour. MOQ and lead times remain separate rules.</CheckboxField></div>
 <div><BrandButton variant="outline" disabled={busy||!mapping.brands.length||!mapping.warehouses.length} onClick={()=>void action(async()=>{await budgetApi.save(mapping);setNotice('Financial mappings saved. Known inputs are valued; unresolved rows remain visible.');})}>Save financial mappings</BrandButton></div>
 </div></details>
 <details className={`group/cur ${panel}`}><summary className={panelSummary}>Joolan currency-code lookup<CaretDownIcon weight="bold" className={`${caret} group-open/cur:rotate-180`}/></summary><div className="flex flex-col gap-3 p-[18px] text-sm leading-[1.55]"><p>Observed codes: {options.observedCurrencyCodes.join(', ')||'none'}. This lookup downloads only the currency reference table and retains the completed export.</p>
 {options.currencies.length?<p className="font-mono text-[13px] text-fg-2">{options.currencies.map(c=>`${c.code||'(blank)'} → ${c.iso||'unresolved'} (${c.name})`).join(' · ')}</p>:<p className="text-brand-800">No currency reference was imported. Codes such as 01 and 02 are not assumed to be EUR.</p>}
 <label className={`${fieldLabel} max-w-[440px]`}>Joolan API key<TextField type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)}/></label><div><BrandButton variant="outline" disabled={busy||!key.trim()} onClick={()=>void action(async()=>{const result=await budgetApi.currencies(key);setKey('');setNotice(result.notice);})}>Fetch currency labels from Joolan</BrandButton></div></div></details>
 </div>}
 </div>;
}
