"use client";
import {CalendarCheckIcon,CaretDownIcon,SpinnerGapIcon} from '@phosphor-icons/react';
import {useState} from 'react';
import {useSeasonStore} from '@/store/seasonStore';

/** Choose which saved planning season the workspace uses (moved here from the old top bar). */
export default function SeasonSwitcher({disabled=false}:{disabled?:boolean}){
 const {activeSeason,seasons,setActiveSeason,error}=useSeasonStore();
 const [pending,setPending]=useState('');
 const choose=(id:string)=>{const season=seasons.find(s=>s.id===id);if(!season||season.id===activeSeason?.id)return;setPending(id);setActiveSeason(season);setTimeout(()=>setPending(''),1500);};
 const range=activeSeason?`${activeSeason.startDate} to ${activeSeason.endDate}${activeSeason.currency?` · ${activeSeason.currency}`:''}`:'';
 return <section aria-labelledby="season-switcher-title" className="flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-line bg-card px-6 py-5 shadow-card">
  <div className="flex min-w-0 items-center gap-3.5">
   <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-brand-700"><CalendarCheckIcon weight="fill" className="h-[22px] w-[22px]"/></span>
   <span className="flex min-w-0 flex-col gap-[3px]">
    <span id="season-switcher-title" className="text-base font-bold">Planning season{activeSeason?`: ${activeSeason.name}`:''}</span>
    <span className="text-[13px] leading-[1.45] text-fg-3">{error?'Connection unavailable. Saved seasons cannot be loaded.':activeSeason?range:seasons.length?'Choose the season the workspace plans for.':'No saved seasons yet. Run a forecast below to create one.'}</span>
   </span>
  </div>
  <label className="relative flex min-w-[220px] flex-[0_1_280px] items-center">
   <select aria-label="Select planning season" value={activeSeason?.id||''} disabled={disabled||!seasons.length} onChange={e=>choose(e.target.value)}
    className="h-[52px] w-full appearance-none rounded-[14px] border-[1.5px] border-border-strong bg-card pl-4 pr-11 text-[15px] font-semibold text-fg-1 outline-none [color-scheme:light_dark] focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:cursor-not-allowed disabled:opacity-60">
    {!activeSeason&&<option value="">{seasons.length?'Select season':'No saved seasons'}</option>}
    {seasons.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
   </select>
   {pending?<SpinnerGapIcon className="pointer-events-none absolute right-4 h-4 w-4 animate-spin text-fg-3"/>:<CaretDownIcon weight="bold" className="pointer-events-none absolute right-4 h-4 w-4 text-fg-3"/>}
  </label>
 </section>;
}
