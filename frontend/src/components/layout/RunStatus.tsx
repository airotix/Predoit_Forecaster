"use client";
import { useCallback,useEffect,useState } from "react";
import { apiClient } from "@/lib/api/client";
import { useSeasonStore } from "@/store/seasonStore";
import { useDataRefresh } from "@/hooks/useDataRefresh";
import Link from 'next/link';
import {ArrowUpRightIcon,CaretDownIcon,CaretUpIcon,DatabaseIcon} from '@phosphor-icons/react';
interface Lineage{source?:string;seasonId?:string;cutoff?:string;forecastStart?:string;forecastEnd?:string;sourceImportedAt?:string;inputsChanged?:boolean;historyChanged?:boolean;sourceGenerationChanged?:boolean;operatingScopeChanged?:boolean;engine?:string;projectionDefinition?:string;uncertaintyDefinition?:string;assortment?:{newVariants:number;analogueVariants:number;bookedOnlyVariants:number};qualitySummary?:{calibratedVariants:number;uncalibratedVariants:number;confidencePolicy:string};}
export default function RunStatus(){
 const {activeSeason}=useSeasonStore();const [text,setText]=useState("");const [runDetails,setRunDetails]=useState<Lineage|null>(null);const [open,setOpen]=useState(false);
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
 if(!text)return null;
 const explained=runDetails?.engine==='calendar-validation-v2';
 return <div role="status" className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-line bg-card px-[18px] py-3.5">
  <div className="flex min-w-0 flex-[1_1_420px] items-start gap-3">
   <DatabaseIcon className="mt-px h-[18px] w-[18px] shrink-0 text-brand"/>
   <div className="min-w-0">
    <p className="text-sm leading-relaxed text-fg-2">{text}</p>
    {explained?<>
     <button type="button" aria-expanded={open} onClick={()=>setOpen(v=>!v)} className="mt-1 flex items-center gap-1.5 text-[13px] font-bold text-brand-700">How these forecasts work{open?<CaretUpIcon weight="bold" className="h-3 w-3"/>:<CaretDownIcon weight="bold" className="h-3 w-3"/>}</button>
     {open&&<div className="mt-3 flex max-w-[860px] flex-col gap-2 text-pretty text-[13px] leading-[1.65] text-fg-2">
      <p>Season projections include eligible bookings without adding them twice. Original statistical predictions are retained separately. Booking dates and delivery requirements use separate date fields.</p>
      <p>Confidence reflects earlier held-out errors, not a probability. Monthly scenario ranges need calibration evidence; adding monthly ranges does not give a guaranteed season interval.</p>
      {runDetails?.assortment&&runDetails.assortment.newVariants>0&&<p>{runDetails.assortment.newVariants.toLocaleString()} newly observed variants need assortment review, including {runDetails.assortment.bookedOnlyVariants.toLocaleString()} with known-bookings-only projections.</p>}
      {runDetails?.qualitySummary&&<p>{runDetails.qualitySummary.uncalibratedVariants.toLocaleString()} variants have no earlier calibration predictions and retain low confidence.</p>}
     </div>}
    </>:runDetails?.cutoff&&<p className="mt-1 text-[13px] font-medium text-brand-800">These results predate the latest engine corrections. Run a fresh forecast to apply them.</p>}
   </div>
  </div>
  <Link href="/setup" className="flex items-center gap-1 whitespace-nowrap text-sm font-bold text-brand-700">View source<ArrowUpRightIcon className="h-3.5 w-3.5"/></Link>
 </div>;
}
