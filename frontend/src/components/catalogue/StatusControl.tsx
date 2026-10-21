"use client";
import {Pill,SelectField} from '@/components/ui/brand';

export interface CatalogueStatus {
 articleJoolan:boolean|null;skuJoolan:boolean|null;articleOverride:boolean|null;skuOverride:boolean|null;
 articleActive:boolean|null;skuActive:boolean|null;active:boolean|null;purchasingBlocked:boolean;reason:string;
 articleUpdatedAt:string|null;skuUpdatedAt:string|null;sourceRun:string|null;
}
export type StatusChange=(level:'article'|'sku',id:string,active:boolean|null)=>void;
export const statusLabel=(active:boolean|null|undefined)=>active==null?'Unknown':active?'Active':'Inactive';

export function StatusBadge({active}:{active:boolean|null|undefined}){
 return <Pill tone={active==null?'brand':active?'success':'neutral'}>{statusLabel(active)}</Pill>;
}

export default function StatusControl({level,id,status,disabled,onChange}:{level:'article'|'sku';id:string;status?:CatalogueStatus|null;disabled:boolean;onChange:StatusChange}){
 const raw=level==='article'?status?.articleJoolan:status?.skuJoolan;
 const override=level==='article'?status?.articleOverride:status?.skuOverride;
 return <div className="flex flex-col gap-1.5">
  <label className="flex flex-col gap-1.5 text-xs font-semibold text-fg-2">{level==='article'?'Article status':'SKU status'}
   <SelectField aria-label={`${level} ${id} status`} strong={level==='article'} wrapperClassName={level==='article'?'min-w-[240px]':'w-[230px]'} className={level==='article'?'h-10 text-[13px]':'h-[38px] text-[13px] font-normal'} disabled={disabled} value={override==null?'joolan':override?'active':'inactive'} onChange={e=>onChange(level,id,e.target.value==='joolan'?null:e.target.value==='active')}>
    <option value="joolan">Use Joolan: {statusLabel(raw)}</option><option value="active">Active — local override</option><option value="inactive">Inactive — no purchasing</option>
   </SelectField>
  </label>
  <p className="text-[11px] text-fg-3">Joolan: {statusLabel(raw)}{override!=null?' · local override saved':''}</p>
  {level==='sku'&&status?.articleActive===false&&<p className="max-w-[220px] text-[11px] leading-[1.45] text-brand-800">The whole article is inactive. Activate the article first to allow purchasing.</p>}
 </div>;
}
