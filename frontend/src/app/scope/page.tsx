"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {ArrowRightIcon,ArrowsClockwiseIcon,CaretDownIcon,CaretUpIcon,CheckIcon,FloppyDiskIcon,InfoIcon,LockSimpleIcon,TagSimpleIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,SelectField} from '@/components/ui/brand';
import {apiClient} from '@/lib/api/client';
import {cn} from '@/lib/utils';
type Role='primary'|'clearance'|'faulty'|'consignment'|'unclassified';
type Scope={brands:string[];warehouseRoles:Record<string,Role>;revision?:string;};
type Data={saved:boolean;scope:Scope;brands:{code:string;articles:number;skus:number}[];warehouses:string[];inventoryAsOf:string|null;notice:string;balanceNotice:string;balances:{warehouse:string;role:Role;records:number;physical:number|null;available:number|null;invalidRecords:number}[]};
const labels:Record<Role,string>={primary:'Primary supply',clearance:'End-of-life / clearance',faulty:'Faulty / standard sale blocked',consignment:'Customer consignment',unclassified:'Unclassified — needs mapping'};
const roleDot:Record<Role,string>={primary:'bg-success-400',clearance:'bg-brand',faulty:'bg-danger',consignment:'bg-plum-600',unclassified:'bg-fg-4'};
const known=['CENTRAL','DESTOCK_VD','DEFECTUEUX'];
const planning=['DAYTONA73','D73','IRON AND RESIN','IRON&RESIN'];
const GRID='grid grid-cols-[minmax(170px,1fr)_300px_190px_190px_160px] gap-4';

function Checkbox({checked,small=false}:{checked:boolean;small?:boolean}){
 return <span aria-hidden className={cn('flex shrink-0 items-center justify-center border-[1.5px]',small?'h-5 w-5 rounded-md':'h-6 w-6 rounded-lg',checked?'border-brand bg-brand':'border-border-strong bg-transparent')}>{checked&&<CheckIcon weight="bold" className={cn('text-white',small?'h-3 w-3':'h-3.5 w-3.5')}/>}</span>;
}

export default function ScopePage(){
 const [data,setData]=useState<Data|null>(null),[draft,setDraft]=useState<Scope|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');const [showOther,setShowOther]=useState(false);
 const dirty=!!draft&&!!data&&JSON.stringify(draft)!==JSON.stringify(data.scope);
 async function load(){setBusy(true);setError('');try{const result=await apiClient.get<Data>('/operating-scope');setData(result);setDraft(result.scope);}catch(e){setError(e instanceof Error?e.message:'Could not load the business scope.');}finally{setBusy(false);}}
 useEffect(()=>{void load();},[]);
 async function save(){if(!draft)return;setBusy(true);setError('');try{const result=await apiClient.put<{notice:string}>('/operating-scope',{brands:draft.brands,warehouseRoles:draft.warehouseRoles});setNotice(result.notice);await load();}catch(e){setError(e instanceof Error?e.message:'Could not save scope.');}finally{setBusy(false);}}
 const number=(n:number|null)=>n==null?'Unknown':n.toLocaleString();
 const toggleBrand=(code:string)=>{if(!draft||busy)return;setDraft({...draft,brands:draft.brands.includes(code)?draft.brands.filter(v=>v!==code):[...draft.brands,code]});};
 const stateLabel=dirty?'Unsaved changes':data?.saved?'Saved business scope':'Proposed scope — not yet applied';
 return <AppShell>
  <PageHeader eyebrow="Planning rules" title="Business scope & stock roles" description="Choose current brands and distinguish normal supply from clearance, faulty and customer-held inventory."
   actions={<BrandButton variant="outline" disabled={busy||dirty} onClick={()=>void load()}><ArrowsClockwiseIcon className={busy?'animate-spin':''}/>Refresh</BrandButton>}/>
  {error&&<Notice tone="danger">{error}</Notice>}
  {notice&&<Notice tone="success"><span className="flex flex-wrap items-center justify-between gap-3"><span className="flex-[1_1_320px]">{notice}</span><Link href="/setup" className="flex items-center gap-1.5 font-bold text-brand-700 hover:text-brand-800">Open Setup<ArrowRightIcon className="h-4 w-4"/></Link></span></Notice>}
  {busy&&!data&&<p role="status" className="text-sm text-fg-3">Loading business scope and recorded balances…</p>}
  {data&&draft&&<>
   <section className="flex flex-col gap-[22px] rounded-[32px] border border-line bg-card p-6 shadow-card sm:p-8">
    <div className="flex flex-col gap-1.5">
     <h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-0.02em]"><TagSimpleIcon className="h-[22px] w-[22px] text-brand"/>Current planning brands</h2>
     <p className="max-w-[820px] text-pretty text-sm leading-relaxed text-fg-2">Current planning includes DAYTONA73, D73, IRON AND RESIN and IRON&amp;RESIN as agreed. The codes remain separate; product records are not merged.</p>
    </div>
    <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
     {data.brands.filter(b=>planning.includes(b.code)).map(b=>{const on=draft.brands.includes(b.code);return <button key={b.code} type="button" role="checkbox" aria-checked={on} disabled={busy} onClick={()=>toggleBrand(b.code)}
      className={cn('flex flex-col gap-3.5 rounded-[20px] border-[1.5px] p-[18px] text-left text-fg-1 transition-all hover:border-brand disabled:opacity-60',on?'border-brand bg-brand-soft':'border-line bg-card')}>
      <Checkbox checked={on}/>
      <span className="flex flex-col gap-1"><span className="font-mono text-[15px] font-bold">{b.code}</span><span className="text-[13px] text-fg-3">{b.articles.toLocaleString()} articles · {b.skus.toLocaleString()} SKUs</span></span>
     </button>;})}
    </div>
    <div className="border-t border-line pt-1">
     <button type="button" aria-expanded={showOther} onClick={()=>setShowOther(v=>!v)} className="flex items-center gap-2 pb-1 pt-3 text-sm font-semibold text-fg-3 hover:text-fg-1">Other exported brands / historical scope{showOther?<CaretUpIcon weight="bold" className="h-3 w-3"/>:<CaretDownIcon weight="bold" className="h-3 w-3"/>}</button>
     {showOther&&<div className="flex flex-wrap gap-2.5 pt-3">{data.brands.filter(b=>!planning.includes(b.code)).map(b=>{const on=draft.brands.includes(b.code);return <button key={b.code} type="button" role="checkbox" aria-checked={on} disabled={busy} onClick={()=>toggleBrand(b.code)}
      className={cn('flex h-10 items-center gap-2.5 rounded-full border-[1.5px] pl-2.5 pr-3.5 text-[13px] font-semibold text-fg-1 disabled:opacity-60',on?'border-brand bg-brand-soft':'border-line bg-card')}><Checkbox checked={on} small/>{b.code}</button>;})}
      {!data.brands.some(b=>!planning.includes(b.code))&&<span className="text-[13px] text-fg-3">No other brands in the saved export.</span>}
     </div>}
    </div>
   </section>
   <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-card">
    <div className="flex flex-col gap-1 border-b border-line px-[26px] py-[22px]"><h2 className="text-xl font-bold">Warehouse classification</h2><p className="text-[13px] leading-[1.55] text-fg-3">CENTRAL, DESTOCK_VD and DEFECTUEUX use the client-confirmed roles. Identify consignment stores using the client’s exact codes.</p></div>
    <div className="overflow-x-auto"><div role="table" aria-label="Warehouse classification" className="min-w-[860px]">
     <div role="row" className={cn(GRID,'border-b border-line bg-page px-[26px] py-3 text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3')}><span role="columnheader">Warehouse</span><span role="columnheader">Role</span><span role="columnheader" className="text-right">Recorded physical units</span><span role="columnheader" className="text-right">Recorded available units</span><span role="columnheader" className="text-right">Records</span></div>
     {data.warehouses.map((w,i)=>{const balance=data.balances.find(b=>b.warehouse===w);const role=draft.warehouseRoles[w];const locked=known.includes(w.toUpperCase());
      return <div role="row" key={w} className={cn(GRID,'items-center px-[26px] py-3.5',i>0&&'border-t border-line',role==='unclassified'&&'bg-brand-50')}>
       <span role="cell" className="flex items-center gap-2.5 font-mono text-sm font-bold"><span className={cn('h-2.5 w-2.5 shrink-0 rounded-full',roleDot[role]||'bg-fg-4')}/>{w}{locked&&<LockSimpleIcon weight="fill" aria-label="Client-confirmed role" className="h-[13px] w-[13px] text-fg-3"/>}</span>
       <span role="cell"><SelectField aria-label={`${w} warehouse role`} wrapperClassName="w-full" className={cn('h-[42px] text-[13px]',role==='unclassified'&&'border-brand-200',locked&&'bg-soft')} disabled={busy||locked} value={role} onChange={e=>setDraft({...draft,warehouseRoles:{...draft.warehouseRoles,[w]:e.target.value as Role}})}>{Object.entries(labels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</SelectField></span>
       <span role="cell" className="text-right font-mono text-sm font-bold">{number(balance?.physical??null)}</span>
       <span role="cell" className={cn('text-right font-mono text-sm font-bold',balance?.available==null&&'text-fg-3')}>{number(balance?.available??null)}</span>
       <span role="cell" className="flex flex-col items-end gap-0.5 font-mono text-[13px] text-fg-3">{balance?.records.toLocaleString()||0}{!!balance?.invalidRecords&&<span className="text-right font-sans text-xs text-brand-800">{balance.invalidRecords} records need reconciliation</span>}</span>
      </div>;})}
    </div></div>
   </section>
   <div className="flex items-start gap-3.5 rounded-[20px] bg-soft px-[22px] py-5">
    <InfoIcon className="mt-0.5 h-[18px] w-[18px] shrink-0 text-plum-600"/>
    <div className="flex flex-col gap-2 text-pretty text-sm leading-relaxed text-fg-2"><p>{data.balanceNotice}</p><p>Balances reflect {data.saved?'saved':'proposed'} brands: {data.scope.brands.join(', ')}. Save and refresh to apply edits to this view. Snapshot: {data.inventoryAsOf?new Date(data.inventoryAsOf).toLocaleString():'unknown'}.</p><p>The wholesale forecast excludes orders recorded in clearance, faulty and classified consignment stores. Consignment sell-through requires its own verified sales mapping. Unclassified channels remain flagged for review.</p></div>
   </div>
   <footer className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-line bg-card py-3.5 pl-[22px] pr-4 shadow-lift">
    <p className="flex flex-wrap items-center gap-2.5 text-sm"><span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold',dirty||!data.saved?'bg-brand-50 text-brand-800':'bg-success-50 text-success-600')}><span className="h-[7px] w-[7px] rounded-full bg-current"/>{stateLabel}</span>Saving requires a new forecast before old insights can be used.</p>
    <BrandButton disabled={busy||!draft.brands.length||(!dirty&&data.saved)} onClick={()=>void save()}><FloppyDiskIcon/>Save business scope</BrandButton>
   </footer>
  </>}
 </AppShell>;
}
