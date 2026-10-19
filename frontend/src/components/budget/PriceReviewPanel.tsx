"use client";
import {useState} from 'react';
import {Input} from '@/components/ui/input';
import {Button} from '@/components/ui/button';
import type {BuyingRow} from '@/lib/api/budget';

export default function PriceReviewPanel({rows,disabled,dirty,onConfirm}:{rows:BuyingRow[];disabled:boolean;dirty:boolean;onConfirm:(reviewer:string,reason:string)=>void}){
 const [reviewer,setReviewer]=useState('');
 const [reason,setReason]=useState('');
 const assumptions=rows.filter(r=>r.priceReviewRequired&&!r.priceReview);
 const incomplete=assumptions.some(r=>!r.supplier||r.orderUnitCost==null||r.orderUnitPrice==null||!r.quantity);
 return <section aria-label="Confirm edited prices" className="mt-4 rounded-lg border bg-white p-4">
  <h3 className="font-medium">Confirm supplier and edited prices</h3>
  <p className="mt-2 text-sm text-slate-600">{assumptions.length} selected variants need price confirmation. This records your acceptance of the saved supplier, purchase cost and selling price. It does not approve the budget or send a PO.</p>
  {assumptions.length>0&&<>
   <div className="mt-4 grid gap-3 md:grid-cols-[220px_minmax(0,1fr)]">
    <label className="text-xs text-slate-600">Reviewer name<Input aria-label="Price reviewer name" maxLength={120} disabled={disabled} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label>
    <label className="text-xs text-slate-600">Why these supplier prices are accepted<Input aria-label="Price review reason" maxLength={1000} placeholder="For example: agreed supplier update and confirmed wholesale selling price" disabled={disabled} value={reason} onChange={e=>setReason(e.target.value)}/></label>
   </div>
   <p className="mt-2 text-xs text-slate-500">Reviewer names are recorded locally and are not verified sign-in identities. Changing prices, supplier, currency or source/settings requires a new confirmation.</p>
   {dirty?<p className="mt-3 text-sm text-amber-800">Save & recalculate first so you confirm the exact saved prices.</p>:incomplete?<p className="mt-3 text-sm text-amber-800">Select a supplier and enter both prices for each line before confirming.</p>:null}
   <Button className="mt-3" variant="outline" disabled={disabled||dirty||incomplete||!reviewer.trim()||!reason.trim()} onClick={()=>onConfirm(reviewer.trim(),reason.trim())}>Confirm saved prices for {assumptions.length} variants</Button>
  </>}
  {rows.some(r=>r.priceReview)&&<p className="mt-3 text-xs text-slate-600">{rows.filter(r=>r.priceReview).length} selected variants have a current recorded price confirmation. Other financial checks still apply.</p>}
 </section>;
}
