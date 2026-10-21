"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowsClockwiseIcon,BarcodeIcon,FloppyDiskIcon,MagnifyingGlassIcon,ReceiptIcon,StorefrontIcon,TagIcon,ToggleRightIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import ArticleCatalogue,{CatalogueSKU} from '@/components/catalogue/ArticleCatalogue';
import type {CatalogueStatus} from '@/components/catalogue/StatusControl';
import {useDataRefresh} from '@/hooks/useDataRefresh';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,SelectField,StatTile,TextField} from '@/components/ui/brand';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from '@/components/ui/sheet';
import {apiClient} from '@/lib/api/client';
type SKU=CatalogueSKU;
interface Catalogue{rows:SKU[];total:number;currency:string;brands:string[];summary:{skus:number;purchaseKnown:number;sellingKnown:number};orderPriceImport?:{cutoff:string;purchaseMatched?:number;sellingMatched?:number;purchaseMissing?:number;sellingMissing?:number}|null;}
interface Edit{sku:string;purchase?:number|null;selling?:number|null;}
interface Details{product:Record<string,unknown>;sku:Record<string,unknown>;inventory:Record<string,unknown>[];inventoryAsOf:string|null;status?:CatalogueStatus|null;statusHistory?:{level:string;id:string;active:boolean|null;reason:string;changedAt:string}[];}
export default function CataloguePage(){
 const [data,setData]=useState<Catalogue|null>(null);const [currency,setCurrency]=useState('EUR');const [search,setSearch]=useState('');const [query,setQuery]=useState('');const [brand,setBrand]=useState('');const [status,setStatus]=useState('');const [statusReason,setStatusReason]=useState('');const [page,setPage]=useState(0);
 const [edits,setEdits]=useState<Record<string,Edit>>({});const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');const sequence=useRef({version:0});
 const [selected,setSelected]=useState<SKU|null>(null);const [details,setDetails]=useState<Details|null>(null);const [detailError,setDetailError]=useState('');
 const dirty=Object.keys(edits).length>0;
 useEffect(()=>{const timer=setTimeout(()=>{setQuery(search);setPage(0);},350);return()=>clearTimeout(timer);},[search]);
 const load=useCallback(async()=>{const version=++sequence.current.version;setLoading(true);setError('');try{const result=await apiClient.get<Catalogue>('/catalogue',{currency,search:query,brand,status,offset:page*20,limit:20,grouped:true});if(version===sequence.current.version)setData(result);}catch(e){if(version===sequence.current.version)setError(e instanceof Error?e.message:'Catalogue could not be loaded.');}finally{if(version===sequence.current.version)setLoading(false);}},[currency,query,brand,status,page]);
 useEffect(()=>{const token=sequence.current;void load();return()=>{token.version++;};},[load]);
 useDataRefresh(useCallback(()=>{if(dirty){setNotice('Catalogue data changed. Your unsaved price edits remain visible; save or discard them before reloading.');return;}if(!busy)void load();},[load,dirty,busy]));
 useEffect(()=>{if(!selected)return;let alive=true;setDetails(null);setDetailError('');apiClient.get<Details>(`/catalogue/sku/${encodeURIComponent(selected.sku)}`).then(v=>{if(alive)setDetails(v);}).catch(e=>{if(alive)setDetailError(e instanceof Error?e.message:'Could not load SKU details.');});return()=>{alive=false;};},[selected]);
 function edit(row:SKU,field:'purchase'|'selling',value:string){setEdits(v=>({...v,[row.sku]:{...v[row.sku],sku:row.sku,[field]:value===''?null:Number(value)}}));setNotice('');}
 const valid=Object.values(edits).every(r=>['purchase','selling'].every(field=>{const value=r[field as 'purchase'|'selling'];return value==null||Number.isFinite(value)&&value>=0;}));
 async function save(){setBusy(true);setError('');try{const result=await apiClient.put<{saved:number;notice:string}>('/catalogue/prices',{currency,rows:Object.values(edits)});setEdits({});setNotice(result.notice);await load();}catch(e){setError(e instanceof Error?e.message:'Could not save prices.');}finally{setBusy(false);}}
 async function reset(row:SKU,side:'purchase'|'selling'){if(dirty){setError('Save or discard your price edits before restoring an order price.');return;}setBusy(true);setError('');try{const result=await apiClient.post<{notice:string}>('/catalogue/prices/reset',{currency,rows:[{sku:row.sku,side}]});setNotice(result.notice);await load();}catch(e){setError(e instanceof Error?e.message:'Could not restore the order price.');}finally{setBusy(false);}}
 async function changeStatus(level:'article'|'sku',id:string,active:boolean|null){if(dirty||busy||loading)return;setBusy(true);setError('');try{const result=await apiClient.put<{notice:string}>('/catalogue/status',{updates:[{level,id,active,reason:statusReason}]});setNotice(result.notice);await load();}catch(e){setError(e instanceof Error?e.message:'Could not save status.');}finally{setBusy(false);}}
 const value=(row:SKU,field:'purchase'|'selling')=>edits[row.sku]&&field in edits[row.sku]?edits[row.sku][field]??'':row[field]??'';
 return <AppShell>
 <PageHeader eyebrow="Permanent product master" title="SKU catalogue" description="Browse articles, then colours and sizes. Purchase and selling prices are saved for each SKU."
  actions={<BrandButton variant="outline" disabled={loading||busy||dirty} onClick={()=>void load()}><ArrowsClockwiseIcon className={loading?'animate-spin':''}/>Refresh from saved Joolan export</BrandButton>}/>
 <Notice>Prices are per unit, net of discounts and excluding VAT, in {currency}. Saved catalogue prices become defaults for new forecasts and the <Link href="/budget" className="font-bold text-brand-700 hover:text-brand-800">Budget Tracker</Link>. Budget edits remain separate draft assumptions. Save changes here to keep them for future seasons.</Notice>
 <div className="flex flex-wrap gap-5">
  <section className="flex flex-[1_1_440px] flex-col gap-3.5 rounded-3xl border border-line bg-card p-6 shadow-card">
   <div className="flex items-start gap-3.5"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success-50"><ToggleRightIcon weight="fill" className="h-5 w-5 text-success-600"/></span><div className="flex flex-col gap-1"><span className="text-[15px] font-bold">Article and size statuses start from the Joolan Actif flags.</span><span className="text-pretty text-[13px] leading-relaxed text-fg-2">Change an article or individual SKU to Active or Inactive. Status changes save immediately and persist across exports. Use Joolan status restores the source value. Inactive items keep their history and stock, but new purchasing is blocked.</span></div></div>
   <label className="flex flex-col gap-1.5 text-xs font-semibold text-fg-3">Reason for status changes (optional)<TextField className="max-w-[560px] font-normal" maxLength={500} disabled={busy||dirty} value={statusReason} onChange={e=>setStatusReason(e.target.value)} placeholder="For example: discontinued by supplier"/></label>
   {dirty&&<span className="text-xs text-brand-800">Save or discard price edits before changing status.</span>}
  </section>
  {data?.orderPriceImport&&<section className="relative flex flex-[1_1_440px] items-start gap-3.5 overflow-hidden rounded-3xl bg-champagne p-6">
   <span aria-hidden className="absolute -bottom-[90px] -right-[70px] h-60 w-60 rounded-full bg-[radial-gradient(circle,var(--glow),rgba(245,130,32,0)_70%)]"/>
   <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-card"><ReceiptIcon weight="fill" className="h-5 w-5 text-brand-700"/></span>
   <p className="relative text-pretty text-[13px] leading-[1.65] text-fg-1">Automatic defaults use the latest valid supplier and customer orders through {data.orderPriceImport.cutoff}. Selling prices are B2B prices to retailers, excluding VAT. Exact colour / size matches are preferred; broader matches are used only when prices agree. Missing or conflicting evidence stays unknown. Manual prices are protected. Refresh uses the saved export; fetch recent orders in Season Setup.</p>
  </section>}
 </div>
 {data&&<div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">{([['Exported SKUs',data.summary.skus,BarcodeIcon],['Purchase prices saved',data.summary.purchaseKnown,TagIcon],['Selling prices saved',data.summary.sellingKnown,StorefrontIcon]] as const).map(([label,n,TileIcon])=><StatTile key={label} label={label} value={Number(n).toLocaleString()} icon={TileIcon}/>)}</div>}
 {error&&<Notice tone="danger">{error}</Notice>}{notice&&<Notice tone="success">{notice}</Notice>}
 <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-card">
  <div className="flex flex-wrap gap-2.5 border-b border-line px-5 py-[18px]">
   <div className="relative flex flex-[1_1_280px] items-center"><MagnifyingGlassIcon className="absolute left-3.5 h-4 w-4 text-fg-3"/><TextField aria-label="Search catalogue" disabled={dirty||busy} className="w-full pl-10" placeholder="Find SKU, article, colour or size…" value={search} onChange={e=>setSearch(e.target.value)}/></div>
   <SelectField aria-label="Catalogue brand" value={brand} disabled={dirty||busy} onChange={e=>{setBrand(e.target.value);setPage(0);}}><option value="">All brands</option>{data?.brands.map(b=><option key={b}>{b}</option>)}</SelectField>
   <SelectField aria-label="Catalogue status filter" value={status} disabled={dirty||busy} onChange={e=>{setStatus(e.target.value);setPage(0);}}><option value="">All statuses</option><option value="active">Active variants</option><option value="inactive">Inactive variants</option><option value="unknown">Unknown status</option></SelectField>
   <SelectField aria-label="Price currency" value={currency} disabled={dirty||busy} onChange={e=>{setCurrency(e.target.value);setPage(0);}}>{['EUR','USD','GBP','CHF','CAD','AUD','PKR'].map(c=><option key={c}>{c}</option>)}</SelectField>
  </div>
  {loading?<p role="status" className="p-10 text-center text-sm text-fg-3">Loading catalogue. The first import can take a few minutes for the full SKU database.</p>:<ArticleCatalogue rows={data?.rows||[]} busy={busy} statusDisabled={busy||dirty||loading} value={value} edit={edit} edited={sku=>!!edits[sku]} select={setSelected} reset={(row,side)=>void reset(row,side)} changeStatus={(level,id,active)=>void changeStatus(level,id,active)}/>}
  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3.5 text-[13px] text-fg-3"><span>{data?.total.toLocaleString()||0} matching articles (full colour / size breakdown) · page {page+1}</span><div className="flex gap-2"><BrandButton size="sm" variant="outline" disabled={loading||dirty||busy||!page} onClick={()=>setPage(p=>p-1)}>Previous</BrandButton><BrandButton size="sm" variant="outline" disabled={loading||dirty||busy||(page+1)*20>=(data?.total||0)} onClick={()=>setPage(p=>p+1)}>Next</BrandButton></div></div>
 </section>
 <footer className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 rounded-[20px] border border-line bg-card py-3.5 pl-[22px] pr-4 shadow-lift">
  <p className="flex flex-wrap items-center gap-2.5 text-sm"><span className="font-display text-lg font-bold">{Object.keys(edits).length}</span>SKU prices edited{!valid&&<span className="font-semibold text-danger">Enter valid nonnegative prices.</span>}</p>
  <div className="flex gap-2"><BrandButton variant="outline" disabled={busy||!dirty} onClick={()=>setEdits({})}>Discard edits</BrandButton><BrandButton disabled={busy||loading||!dirty||!valid} onClick={()=>void save()}><FloppyDiskIcon/>{busy?'Saving…':'Save catalogue prices'}</BrandButton></div>
 </footer>
 <Sheet open={!!selected} onOpenChange={open=>{if(!open)setSelected(null);}}><SheetContent className="flex w-full flex-col gap-0 overflow-y-auto border-line bg-card p-0 sm:max-w-[640px]">
  <SheetHeader className="sticky top-0 z-[1] gap-1.5 space-y-0 border-b border-line bg-card px-7 py-6 pr-14 text-left"><SheetTitle className="text-[22px] font-extrabold tracking-[-0.02em]">{selected?.reference} · {selected?.color} / {selected?.size}</SheetTitle><SheetDescription className="text-[13px] leading-normal text-fg-3">SKU {selected?.sku} · {selected?.name}. Fields from the latest saved Joolan export.</SheetDescription></SheetHeader>
  <div className="flex flex-col gap-4 px-7 pb-8 pt-6">
   {detailError&&<Notice tone="danger">{detailError}</Notice>}{!details&&!detailError&&<p className="text-sm text-fg-3">Loading SKU details…</p>}
   {details&&<>
    {details.statusHistory&&details.statusHistory.length>0&&<section className="rounded-[18px] border border-line px-5 py-[18px]"><h3 className="text-[15px] font-bold">Local status history</h3><ul className="mt-2.5 flex flex-col gap-2.5 text-xs">{details.statusHistory.map((entry,i)=><li key={i}><p>{entry.level} {entry.id}: {entry.active==null?'Restored Joolan status':entry.active?'Active':'Inactive'}</p><p className="mt-[3px] text-fg-3">{new Date(entry.changedAt).toLocaleString()} {entry.reason&&`- ${entry.reason}`}</p></li>)}</ul></section>}
    <p className="text-xs text-fg-3">Inventory snapshot: {details.inventoryAsOf||'Unknown'}. Missing warehouse records are not zero stock.</p>
    {[['Product details',details.product],['SKU details',details.sku],...details.inventory.map((r,i)=>[`Warehouse stock ${i+1}`,r])].map(([title,fields],i)=><section key={i} className="rounded-[18px] border border-line px-5 py-[18px]"><h3 className="text-[15px] font-bold">{String(title)}</h3><dl className="mt-3 flex flex-col gap-2 text-[13px]">{Object.entries(fields as Record<string,unknown>).map(([name,v])=><div key={name} className="grid grid-cols-2 gap-3"><dt className="break-words font-mono text-xs text-fg-3">{name}</dt><dd className="break-words">{v==null?'—':typeof v==='object'?JSON.stringify(v):String(v)}</dd></div>)}</dl></section>)}
   </>}
  </div>
 </SheetContent></Sheet>
 </AppShell>;
}
