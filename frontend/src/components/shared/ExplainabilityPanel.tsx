"use client";
import {useState} from "react";
import {ExplainabilityData} from "@/types";
import {useSeasonStore} from "@/store/seasonStore";
interface Props{data:ExplainabilityData;totalUnits:number;skuName?:string;collapsible?:boolean;defaultExpanded?:boolean;className?:string;}
export default function ExplainabilityPanel({data,totalUnits,skuName,collapsible=true,defaultExpanded=false,className=""}:Props){
 const [expanded,setExpanded]=useState(defaultExpanded);const {activeScenario}=useSeasonStore();
 return <section className={`rounded-lg border p-4 ${className}`}>
  <button className="text-sm font-medium" onClick={()=>setExpanded(!expanded)} aria-expanded={!collapsible||expanded}>Quantity context {skuName?`— ${skuName}`:""}</button>
  {(!collapsible||expanded)&&<div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
   <p>Selected quantity: {totalUnits.toLocaleString()} units ({activeScenario}). Purchase quantities subtract available stock and incoming units from forecast demand; manual edits replace the proposed purchase quantity.</p>
   <p>Recorded undelivered order balance: {data.confirmedOrders.units.toLocaleString()} units. This balance is shown as context; delivery dates are needed to allocate it to the planning period.</p>
   <p>The engine compares forecasts using earlier months only. Conservative and optimistic scenarios use observed validation errors; they are not fixed percentage multipliers or calibrated service levels.</p>
   <p>Historical customer reach: {(data.keySignals.diffusionRate*100).toFixed(1)}%. Depth per customer: {data.keySignals.depthPerCustomer.toFixed(1)} units.</p>
   <p>Customer visits, customer clusters and future customer-specific reorders are not modeled. Missing source months are assumed to contain no orders; verify that the import covers the complete period.</p>
  </div>}
 </section>;
}
