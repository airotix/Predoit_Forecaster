"use client";
/** Shared building blocks of the redesigned pages (Preduit mockups). */
import * as React from "react";
import {CaretDownIcon,CheckCircleIcon,InfoIcon,WarningCircleIcon,type Icon} from "@phosphor-icons/react";
import {cn} from "@/lib/utils";

export function PageHeader({eyebrow,title,description,actions,className}:{eyebrow:string;title:React.ReactNode;description?:React.ReactNode;actions?:React.ReactNode;className?:string}){
 return <div className={cn("flex flex-wrap items-end justify-between gap-4",className)}>
  <div className="flex min-w-0 flex-col gap-2">
   <span className="text-xs font-bold uppercase tracking-[0.12em] text-brand">{eyebrow}</span>
   <h1 className="font-display text-[32px] font-extrabold leading-[1.08] tracking-[-0.02em] sm:text-[40px]">{title}</h1>
   {description&&<p className="max-w-[760px] text-pretty text-base leading-relaxed text-fg-2">{description}</p>}
  </div>
  {actions&&<div className="flex flex-wrap items-center gap-3">{actions}</div>}
 </div>;
}

type Tone="info"|"brand"|"danger"|"success";
const TONES:Record<Tone,{box:string;icon:string;Icon:Icon;weight:"fill"|"regular"}>={
 info:{box:"border border-line bg-card text-fg-2",icon:"text-plum-600",Icon:InfoIcon,weight:"regular"},
 brand:{box:"border border-brand-200 bg-brand-50 text-fg-1",icon:"text-brand-700",Icon:InfoIcon,weight:"fill"},
 danger:{box:"bg-danger-soft text-fg-1",icon:"text-danger",Icon:WarningCircleIcon,weight:"fill"},
 success:{box:"bg-success-50 text-fg-1",icon:"text-success-600",Icon:CheckCircleIcon,weight:"fill"},
};

/** Rounded status/notice strip. role defaults to alert for danger, status otherwise. */
export function Notice({tone="info",icon,children,className,role}:{tone?:Tone;icon?:Icon;children:React.ReactNode;className?:string;role?:string}){
 const t=TONES[tone];const NoticeIcon=icon||t.Icon;
 return <div role={role??(tone==="danger"?"alert":"status")} className={cn("flex items-start gap-3 rounded-2xl px-[18px] py-3.5 text-sm leading-relaxed",t.box,className)}>
  <NoticeIcon weight={t.weight} className={cn("mt-0.5 h-[18px] w-[18px] shrink-0",t.icon)}/>
  <div className="min-w-0 flex-1 text-pretty">{children}</div>
 </div>;
}

export function StatTile({label,value,icon:TileIcon,sub,className}:{label:string;value:React.ReactNode;icon?:Icon;sub?:React.ReactNode;className?:string}){
 return <section className={cn("flex flex-col gap-2.5 rounded-3xl border border-line bg-card p-[22px] shadow-card",className)}>
  <div className="flex items-center justify-between gap-3"><span className="text-[13px] font-semibold text-fg-2">{label}</span>{TileIcon&&<TileIcon className="h-[18px] w-[18px] shrink-0 text-fg-3"/>}</div>
  <span className="font-display text-[32px] font-bold tracking-[-0.02em]">{value}</span>
  {sub&&<span className="text-[13px] text-fg-3">{sub}</span>}
 </section>;
}

/** Native select with the mockup's border, radius and caret. */
export const SelectField=React.forwardRef<HTMLSelectElement,React.SelectHTMLAttributes<HTMLSelectElement>&{strong?:boolean;wrapperClassName?:string}>(
 ({className,wrapperClassName,strong=false,children,...props},ref)=><span className={cn("relative inline-flex items-center",wrapperClassName)}>
  <select ref={ref} className={cn("h-11 w-full cursor-pointer appearance-none rounded-xl border-[1.5px] bg-card pl-3.5 pr-9 text-sm font-semibold text-fg-1 outline-none [color-scheme:light_dark] focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:cursor-not-allowed disabled:opacity-60",strong?"border-border-strong":"border-line",className)} {...props}>{children}</select>
  <CaretDownIcon weight="bold" className="pointer-events-none absolute right-3.5 h-3 w-3 text-fg-3"/>
 </span>);
SelectField.displayName="SelectField";

/** Text/number input with the mockup's 1.5px border and orange focus ring. */
export const TextField=React.forwardRef<HTMLInputElement,React.InputHTMLAttributes<HTMLInputElement>&{strong?:boolean}>(
 ({className,strong=true,...props},ref)=><input ref={ref} className={cn("h-11 rounded-xl border-[1.5px] bg-card px-3.5 text-sm text-fg-1 outline-none [color-scheme:light_dark] placeholder:text-fg-3 focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] disabled:cursor-not-allowed disabled:opacity-60",strong?"border-border-strong":"border-line",className)} {...props}/>);
TextField.displayName="TextField";

export function Pill({tone="neutral",children,className}:{tone?:"neutral"|"success"|"brand"|"danger"|"plum";children:React.ReactNode;className?:string}){
 const tones={neutral:"bg-soft text-fg-2",success:"bg-success-50 text-success-600",brand:"bg-brand-50 text-brand-800",danger:"bg-danger-soft text-danger",plum:"bg-plum-50 text-plum-600"};
 return <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-[3px] text-xs font-bold",tones[tone],className)}>{children}</span>;
}
