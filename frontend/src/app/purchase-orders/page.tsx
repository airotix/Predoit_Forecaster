"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {ArrowUpRightIcon,ArrowsClockwiseIcon,FilePlusIcon} from '@phosphor-icons/react';
import AppShell from '@/components/layout/AppShell';
import {ScenarioSwitcher} from '@/components/shared';
import {BrandButton} from '@/components/ui/brand-button';
import {Notice,PageHeader,SelectField} from '@/components/ui/brand';
import POEditor from '@/components/purchase-orders/POEditor';
import {useSeasonStore} from '@/store/seasonStore';
import {budgetApi,type BuyingSimulation} from '@/lib/api/budget';
import {purchaseOrdersApi,type POSummary,type PurchaseOrder} from '@/lib/api/purchaseOrders';
import {cn} from '@/lib/utils';

const STATUS:Record<POSummary['status'],{label:string;className:string}>={
 draft:{label:'Draft',className:'bg-soft text-fg-2'},
 pending_validation:{label:'Awaiting validation',className:'bg-brand-50 text-brand-800'},
 validated:{label:'Validated',className:'bg-success-50 text-success-600'},
 cancelled:{label:'Cancelled',className:'bg-danger-soft text-danger'},
};

export default function PurchaseOrders(){
 const {activeSeason,activeScenario}=useSeasonStore();
 const seasonId=activeSeason?.id;
 const [orders,setOrders]=useState<POSummary[]>([]),[suppliers,setSuppliers]=useState<string[]>([]);
 const [draft,setDraft]=useState<BuyingSimulation|null>(null),[order,setOrder]=useState<PurchaseOrder|null>(null);
 const [mode,setMode]=useState<'all'|'fitting'|'selected'>('selected');
 const [loading,setLoading]=useState(true),[detailLoading,setDetailLoading]=useState(false),[creating,setCreating]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [poDirty,setPoDirty]=useState(false);
 const request=useRef({version:0}),detailRequest=useRef({version:0}),context=useRef({seasonId,scenario:activeScenario});context.current={seasonId,scenario:activeScenario};
 const load=useCallback(async()=>{const version=++request.current.version;setError('');setLoading(true);setDraft(null);
  if(!seasonId){setLoading(false);return;}
  try{const list=await purchaseOrdersApi.list(seasonId,activeScenario);if(version!==request.current.version)return;setOrders(list.orders);setSuppliers(list.suppliers);
   const current=await budgetApi.draft(activeScenario);if(version===request.current.version){setDraft(current);const id=new URLSearchParams(window.location.search).get('po');if(id&&list.orders.some(row=>row.id===id)){const detail=await purchaseOrdersApi.read(id);if(version===request.current.version)setOrder(detail);}}
  }catch(e){if(version===request.current.version)setError(e instanceof Error?e.message:'Could not load purchase orders.');}finally{if(version===request.current.version)setLoading(false);}
 },[seasonId,activeScenario]);
 useEffect(()=>{const token=request.current,detailToken=detailRequest.current;setOrder(null);setOrders([]);setNotice('');setPoDirty(false);setDetailLoading(false);detailToken.version++;void load();return()=>{token.version++;detailToken.version++;};},[load]);
 async function open(id:string){if(poDirty)return;const version=++detailRequest.current.version;setDetailLoading(true);setError('');try{const result=await purchaseOrdersApi.read(id);if(version===detailRequest.current.version)setOrder(result);}catch(e){if(version===detailRequest.current.version)setError(e instanceof Error?e.message:'Could not open PO.');}finally{if(version===detailRequest.current.version)setDetailLoading(false);}}
 async function create(){if(!draft||!seasonId)return;const version=request.current.version;setCreating(true);setError('');try{const result=await purchaseOrdersApi.create(draft,mode);if(version!==request.current.version)return;setNotice(result.notice);const list=await purchaseOrdersApi.list(seasonId,activeScenario);if(version!==request.current.version)return;setOrders(list.orders);const id=result.created[0]||result.existing[0];if(id)await open(id);}catch(e){if(version===request.current.version)setError(e instanceof Error?e.message:'Could not create purchase orders.');}finally{setCreating(false);}}
 function saved(doc:PurchaseOrder){if(context.current.seasonId!==doc.seasonId||context.current.scenario!==doc.scenario)return;setOrder(doc);setPoDirty(false);setOrders(prev=>prev.map(row=>row.id===doc.id?{...row,supplier:doc.supplier,status:doc.status,version:doc.version,updatedAt:doc.updatedAt,totals:doc.totals}:row));}
 const draftRows=draft?.rows.filter(row=>row.quantity!=null&&row.quantity>0&&(mode==='all'||mode==='selected'&&draft.draft?.selected.includes(row.id)||mode==='fitting'&&draft.articlePlan.articles.some(article=>article.reference===row.reference&&article.status==='included')))||[];
 return <AppShell>
 <PageHeader eyebrow="Supplier purchasing" title="Purchase orders" description="Turn your saved Budget Tracker quantities into editable supplier PO drafts." actions={<ScenarioSwitcher/>}/>
 <section className="flex flex-col gap-[18px] rounded-[32px] border border-line bg-card p-6 shadow-card sm:px-8 sm:py-7">
  <div className="flex flex-wrap justify-between gap-3">
   <div className="flex flex-col gap-1"><h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-[-0.02em]"><FilePlusIcon className="h-[22px] w-[22px] shrink-0 text-brand"/>Create from Budget Tracker</h2><p className="text-sm text-fg-3">{activeSeason?.name||'Select a planning season'} · {activeScenario}{draft?` · saved budget v${draft.draft?.version||0}`:''}</p></div>
   <Link href="/budget" className="flex items-center gap-1.5 self-start text-sm font-bold text-brand-700 hover:text-brand-800">Open Budget Tracker<ArrowUpRightIcon className="h-4 w-4"/></Link>
  </div>
  <div className="flex flex-wrap items-end gap-2.5">
   <label className="flex w-full flex-col gap-2 text-[13px] font-semibold text-fg-2 sm:w-auto">Quantities to import<SelectField strong aria-label="PO quantity selection" wrapperClassName="w-full" className="sm:min-w-[320px]" disabled={creating} value={mode} onChange={e=>setMode(e.target.value as typeof mode)}><option value="all">All positive budget draft quantities</option><option value="fitting">Only articles fitting the buying budget</option><option value="selected">Only articles selected for review</option></SelectField></label>
   <BrandButton disabled={loading||creating||poDirty||!draft?.draft?.version||draft.draft.stale||!draftRows.length} onClick={()=>void create()}><FilePlusIcon/>{creating?'Creating supplier drafts…':'Create supplier POs'}</BrandButton>
   <BrandButton variant="outline" disabled={loading||creating||poDirty} onClick={()=>void load()}><ArrowsClockwiseIcon className={loading?'animate-spin':''}/>Refresh source</BrandButton>
  </div>
  <p className="text-[13px] text-fg-2"><strong className="font-mono">{draftRows.length.toLocaleString()} variants · {draftRows.reduce((n,row)=>n+(row.quantity||0),0).toLocaleString()} units</strong> in this selection. One draft per supplier; quantities already imported for this forecast and scenario are skipped.</p>
  {draft&&(!draft.draft?.version||draft.draft.stale)&&<Notice tone="brand">Save & recalculate the current Budget Tracker draft first. Only saved quantities and prices are copied.</Notice>}
  <p className="text-xs leading-[1.55] text-fg-3">All-quantity import also includes articles outside the budget allowance. Their financial warnings stay visible. PO edits remain separate from the buying plan; nothing is sent to Joolan or suppliers.</p>
 </section>
 {loading&&<p role="status" className="flex items-center gap-2 text-sm text-fg-3"><ArrowsClockwiseIcon className="h-4 w-4 animate-spin"/>Loading saved POs and the current buying plan…</p>}
 {error&&<Notice tone="danger">{error}</Notice>}
 {notice&&<Notice tone="success">{notice}</Notice>}
 <div className="flex flex-wrap items-start gap-5">
  <aside className="min-w-[260px] flex-[1_1_100%] overflow-hidden rounded-3xl border border-line bg-card shadow-card lg:flex-[0_1_290px]">
   <div className="flex flex-col gap-0.5 border-b border-line px-[18px] pb-3.5 pt-[18px]"><h2 className="text-base font-bold">Saved purchase orders</h2><p className="text-xs text-fg-3">{orders.length} POs · current season and scenario</p></div>
   <div className="flex max-h-[70vh] flex-col gap-1 overflow-auto p-2">
    {orders.map(row=>{const active=order?.id===row.id;const status=STATUS[row.status];return <button key={row.id} type="button" disabled={creating||poDirty} onClick={()=>void open(row.id)} aria-current={active||undefined} className={cn('flex w-full flex-col gap-1.5 rounded-2xl p-3.5 text-left text-fg-1 transition-colors disabled:cursor-not-allowed',active?'bg-brand-soft':'hover:bg-page')}>
     <span className="flex w-full items-center justify-between gap-2"><span className={cn('font-mono text-[13px] font-bold',active?'text-brand-800':'text-fg-1')}>{row.number}</span>{status&&<span className={cn('whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold',status.className)}>{status.label}</span>}</span>
     <span className={cn('w-full truncate text-sm font-semibold',row.supplier?'text-fg-1':'text-brand-800')}>{row.supplier||'Supplier needs assignment'}</span>
     <span className="text-xs text-fg-3">{row.status==='cancelled'?'Cancelled':`${row.totals.units??'Unknown'} units`} · {row.totals.articles} articles · v{row.version}</span>
     <span className="font-mono text-[13px] font-bold">{row.totals.purchaseCost==null?'Cost incomplete':new Intl.NumberFormat('en-GB',{style:'currency',currency:row.currency}).format(row.totals.purchaseCost)}</span>
    </button>;})}
    {!orders.length&&!loading&&<p className="p-4 text-sm leading-relaxed text-fg-3">No supplier POs yet. Save the Budget Tracker draft, then create your first supplier orders.</p>}
   </div>
  </aside>
  <div className="flex min-w-0 flex-[1_1_640px] flex-col gap-[18px]">
   {detailLoading?<p role="status" className="flex items-center gap-2 rounded-3xl border border-line bg-card p-6 text-sm text-fg-3"><ArrowsClockwiseIcon className="h-4 w-4 animate-spin"/>Opening purchase order…</p>
   :order?<POEditor key={`${order.id}-${order.version}`} order={order} suppliers={suppliers} onSaved={saved} onDirtyChange={setPoDirty}/>
   :<div className="flex flex-col items-center gap-2.5 rounded-3xl border-[1.5px] border-dashed border-line px-6 py-14 text-center"><FilePlusIcon className="h-[34px] w-[34px] text-brand"/><h2 className="text-lg font-bold">Your supplier orders, ready to work on</h2><p className="max-w-[520px] text-pretty text-sm leading-[1.55] text-fg-3">Create PO drafts above or open a saved PO. Review each article by colour and size, edit quantities and prices, then save and download the supplier CSV.</p></div>}
  </div>
 </div>
 </AppShell>;
}
