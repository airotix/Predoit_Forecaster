"use client";
import { useCallback,useEffect,useState } from "react";
import { apiClient } from "@/lib/api/client";
import { useSeasonStore } from "@/store/seasonStore";
import { useDataRefresh } from "@/hooks/useDataRefresh";
import Link from 'next/link';
import {Database,ArrowUpRight} from 'lucide-react';
interface Lineage{source?:string;seasonId?:string;cutoff?:string;forecastStart?:string;forecastEnd?:string;sourceImportedAt?:string;inputsChanged?:boolean;historyChanged?:boolean;sourceGenerationChanged?:boolean;operatingScopeChanged?:boolean;engine?:string;projectionDefinition?:string;uncertaintyDefinition?:string;assortment?:{newVariants:number;analogueVariants:number;bookedOnlyVariants:number};qualitySummary?:{calibratedVariants:number;uncalibratedVariants:number;confidencePolicy:string};}
export default function RunStatus(){
 const {activeSeason}=useSeasonStore();const [text,setText]=useState("");const [runDetails,setRunDetails]=useState<Lineage|null>(null);
 const activeSeasonId=activeSeason?.id;
 const load=useCallback(async()=>{
  try{
   const [run,source]=await Promise.all([apiClient.get<Lineage>('/pipeline/lineage'),apiClient.get<{forecastSource:string;importedAt?:string}>('/joolan/summary')]);
   setRunDetails(run);
   if(!run.cutoff){setText('No forecast has been published. Complete the fresh Joolan setup to run one.');return;}
   const mismatch=run.operatingScopeChanged||run.sourceGenerationChanged||run.inputsChanged||run.historyChanged||(activeSeasonId&&run.seasonId!==activeSeasonId)||(source.forecastSource!==run.source)||((run.source==='joolan'||run.source==='combined')&&run.sourceImportedAt!==source.importedAt);
   setText(`${mismatch?'Selected inputs differ from these results. Refresh forecasts. ':''}Published source: ${run.source}. History through ${run.cutoff}; forecast ${run.forecastStart} to ${run.forecastEnd}.`);
  }catch{setRunDetails(null);setText('Cannot verify the published forecast source. Check the backend connection.');}
 },[activeSeasonId]);
 useEffect(()=>{void load();},[load]);useDataRefresh(load);
 return text?<div role="status" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/70 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/60"><div className="flex min-w-0 items-center gap-2 text-xs text-slate-500"><Database className="h-3.5 w-3.5 shrink-0 text-blue-500"/><div><p className="leading-relaxed">{text}</p>{runDetails?.engine==='calendar-validation-v2'?<details className="mt-2"><summary className="cursor-pointer font-medium text-blue-600">How these forecasts work</summary><div className="mt-2 space-y-2 leading-5"><p>Season projections include eligible bookings without adding them twice. Original statistical predictions are retained separately. Booking dates and delivery requirements use separate date fields.</p><p>Confidence reflects earlier held-out errors, not a probability. Monthly scenario ranges need calibration evidence; adding monthly ranges does not give a guaranteed season interval.</p>{runDetails.assortment&&runDetails.assortment.newVariants>0&&<p>{runDetails.assortment.newVariants.toLocaleString()} newly observed variants need assortment review, including {runDetails.assortment.bookedOnlyVariants.toLocaleString()} with known-bookings-only projections.</p>}{runDetails.qualitySummary&&<p>{runDetails.qualitySummary.uncalibratedVariants.toLocaleString()} variants have no earlier calibration predictions and retain low confidence.</p>}</div></details>:runDetails?.cutoff&&<p className="mt-2 text-amber-700">These results predate the latest engine corrections. Run a fresh forecast to apply them.</p>}</div></div><Link href="/setup" className="flex shrink-0 items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400">View source<ArrowUpRight className="h-3 w-3"/></Link></div>:null;
}
