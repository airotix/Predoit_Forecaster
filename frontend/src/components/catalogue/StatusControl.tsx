"use client";

export interface CatalogueStatus {
 articleJoolan:boolean|null;skuJoolan:boolean|null;articleOverride:boolean|null;skuOverride:boolean|null;
 articleActive:boolean|null;skuActive:boolean|null;active:boolean|null;purchasingBlocked:boolean;reason:string;
 articleUpdatedAt:string|null;skuUpdatedAt:string|null;sourceRun:string|null;
}
export type StatusChange=(level:'article'|'sku',id:string,active:boolean|null)=>void;
export const statusLabel=(active:boolean|null|undefined)=>active==null?'Unknown':active?'Active':'Inactive';

export function StatusBadge({active}:{active:boolean|null|undefined}){
 return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${active==null?'bg-amber-50 text-amber-800':active?'bg-emerald-50 text-emerald-800':'bg-slate-200 text-slate-700'}`}>{statusLabel(active)}</span>;
}

export default function StatusControl({level,id,status,disabled,onChange}:{level:'article'|'sku';id:string;status?:CatalogueStatus|null;disabled:boolean;onChange:StatusChange}){
 const raw=level==='article'?status?.articleJoolan:status?.skuJoolan;
 const override=level==='article'?status?.articleOverride:status?.skuOverride;
 return <div className="space-y-1.5"><label className="block text-xs font-medium text-slate-600">{level==='article'?'Article status':'SKU status'}
 <select aria-label={`${level} ${id} status`} className="mt-1 block rounded-lg border bg-white px-2 py-2 text-sm disabled:opacity-50" disabled={disabled} value={override==null?'joolan':override?'active':'inactive'} onChange={e=>onChange(level,id,e.target.value==='joolan'?null:e.target.value==='active')}>
  <option value="joolan">Use Joolan: {statusLabel(raw)}</option><option value="active">Active — local override</option><option value="inactive">Inactive — no purchasing</option>
 </select></label><p className="text-[11px] text-slate-500">Joolan: {statusLabel(raw)}{override!=null?' · local override saved':''}</p>
 {level==='sku'&&status?.articleActive===false&&<p className="max-w-48 text-[11px] text-amber-700">The whole article is inactive. Activate the article first to allow purchasing.</p>}
 </div>;
}
