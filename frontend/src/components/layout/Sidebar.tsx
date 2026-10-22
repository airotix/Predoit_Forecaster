"use client";
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {ArrowUpRightIcon,ChartLineUpIcon,SignOutIcon} from '@phosphor-icons/react';
import {useUIStore} from '@/store/uiStore';
import {sidebarNavigationForRole,navigation as allNavigation} from './navigation';
import {useAuth} from '@/components/auth/AuthProvider';
import {roleMeetsRequired} from '@/lib/auth/msalConfig';
import {cn} from '@/lib/utils';

type NavItem=(typeof allNavigation)[number];

export function BrandMark({className}:{className?:string}){
 return <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] bg-brand shadow-brand',className)}><ChartLineUpIcon weight="bold" className="h-[22px] w-[22px] text-white"/></span>;
}

export function groupNavigation(items:NavItem[]){
 return Array.from(new Set(items.map(n=>n.group))).map(group=>({group,items:items.filter(n=>n.group===group)}));
}

export function NavItemLink({item,collapsed=false,onNavigate}:{item:NavItem;collapsed?:boolean;onNavigate?:()=>void}){
 const pathname=usePathname();const active=pathname===item.href;const Icon=item.icon;
 return <Link href={item.href} onClick={onNavigate} aria-current={active?'page':undefined} aria-label={collapsed?item.label:undefined} title={collapsed?item.label:item.description}
  className={cn('flex min-h-11 items-center gap-3 rounded-[14px] px-3 text-left text-sm transition-colors',collapsed&&'justify-center',
   active?'bg-brand-soft font-bold text-brand-800':'font-medium text-fg-2 hover:bg-soft hover:text-fg-1')}>
  <Icon weight={active?'fill':'regular'} className={cn('h-[19px] w-[19px] shrink-0',active&&'text-brand')}/>
  {!collapsed&&<><span className="flex-1">{item.label}</span>{active&&<span aria-hidden className="h-2 w-2 rounded-full bg-brand shadow-[0_0_0_4px_rgba(245,130,32,0.18)]"/>}</>}
 </Link>;
}

/** Grouped navigation used by the mobile drawer (settings included in its group). */
export function NavigationLinks({onNavigate}:{onNavigate?:()=>void}){
 const {role}=useAuth();
 return <nav aria-label="Main navigation" className="flex flex-col gap-3.5">{groupNavigation(sidebarNavigationForRole(role)).map(({group,items})=><div key={group} className="flex flex-col gap-0.5">
  <span className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-fg-4">{group}</span>
  {items.map(item=><NavItemLink key={item.href} item={item} onNavigate={onNavigate}/>)}
 </div>)}</nav>;
}

export function initials(name:string){
 const parts=name.replace(/@.*/,'').split(/[\s._-]+/).filter(Boolean);
 return ((parts[0]?.[0]||'')+(parts.length>1?parts[parts.length-1][0]:parts[0]?.[1]||'')).toUpperCase()||'U';
}

export default function Sidebar(){
 const {sidebarCollapsed}=useUIStore();const {role,user,account,logout}=useAuth();
 const collapsed=sidebarCollapsed;const items=sidebarNavigationForRole(role);
 const settings=items.find(n=>n.href==='/settings');
 const name=user?.name||account?.name||account?.username||'My account';
 return <aside className={cn('sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-card transition-[width] duration-200 ease-[cubic-bezier(.22,1,.36,1)] lg:flex',collapsed?'w-[84px]':'w-[272px]')}>
  <Link href="/dashboard" aria-label="Preduit dashboard" className={cn('flex items-center gap-3 px-[22px] pb-[18px] pt-[22px]',collapsed&&'justify-center')}>
   <BrandMark/>
   {!collapsed&&<span className="flex min-w-0 flex-col gap-px"><span className="font-display text-xl font-bold tracking-[-0.02em]">Preduit</span><span className="text-xs text-fg-3">Demand planning</span></span>}
  </Link>
  {!collapsed&&roleMeetsRequired(role,'manager')&&<Link href="/setup" className="mx-4 mb-2 flex flex-col gap-1.5 rounded-[18px] bg-champagne px-4 py-3.5 text-left text-fg-1 transition-shadow hover:shadow-[inset_0_0_0_1px_var(--orange-200)]">
   <span className="flex w-full items-center justify-between"><span className="text-[11px] font-bold uppercase tracking-[0.12em] text-brand-800">Data &amp; setup</span><ArrowUpRightIcon className="h-[15px] w-[15px] text-brand-800"/></span>
   <span className="text-[13px] leading-[1.45] text-fg-2">Manage your Joolan source and published forecast.</span>
  </Link>}
  <nav aria-label="Main navigation" className="flex min-h-0 flex-1 flex-col gap-3.5 overflow-y-auto overflow-x-hidden px-3 pb-3 pt-2">
   {groupNavigation(items.filter(n=>n.href!=='/settings')).map(({group,items:groupItems})=><div key={group} className="flex flex-col gap-0.5">
    {!collapsed&&<span className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-fg-4">{group}</span>}
    {groupItems.map(item=><NavItemLink key={item.href} item={item} collapsed={collapsed}/>)}
   </div>)}
  </nav>
  <div className="flex flex-col gap-1 border-t border-line p-3">
   {settings&&<NavItemLink item={settings} collapsed={collapsed}/>}
   <div className={cn('flex items-center gap-3 px-3 py-2',collapsed&&'justify-center')}>
    <span title={collapsed?`${name} (${role})`:undefined} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-plum-50 text-[13px] font-bold text-plum-600">{initials(name)}</span>
    {!collapsed&&<><span className="flex min-w-0 flex-1 flex-col"><span className="truncate text-sm font-semibold">{name}</span><span className="text-xs text-fg-3">Role: {role}</span></span>
     <button type="button" aria-label="Log out" title="Log out" onClick={()=>void logout()} className="flex h-8 w-8 items-center justify-center rounded-[10px] text-fg-3 hover:bg-danger-soft hover:text-danger"><SignOutIcon className="h-[18px] w-[18px]"/></button></>}
   </div>
  </div>
 </aside>;
}
