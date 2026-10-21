"use client";
import type {InputHTMLAttributes,ReactNode} from 'react';
import {CheckIcon} from '@phosphor-icons/react';
import {cn} from '@/lib/utils';

/** Native checkbox (kept for keyboard and screen readers) drawn as the mockup's rounded orange box. */
export default function CheckboxField({children,className,boxClassName,...props}:Omit<InputHTMLAttributes<HTMLInputElement>,'type'>&{children:ReactNode;boxClassName?:string}){
 return <label className={cn('flex cursor-pointer items-start gap-3 text-sm leading-normal text-fg-1 has-[:disabled]:cursor-not-allowed',className)}>
  <input type="checkbox" className="peer sr-only" {...props}/>
  <span aria-hidden className={cn('flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[7px] border-[1.5px] border-border-strong bg-transparent transition-colors peer-checked:border-brand peer-checked:bg-brand peer-focus-visible:shadow-[0_0_0_3px_rgba(245,130,32,0.35)] peer-disabled:opacity-50 [&>svg]:opacity-0 peer-checked:[&>svg]:opacity-100',boxClassName)}><CheckIcon weight="bold" className="h-3 w-3 text-white"/></span>
  <span className="min-w-0">{children}</span>
 </label>;
}
