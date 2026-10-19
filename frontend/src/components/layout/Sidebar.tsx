"use client";
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {PanelLeftClose,PanelLeftOpen,ArrowUpRight} from 'lucide-react';
import {useUIStore} from '@/store/uiStore';
import {Button} from '@/components/ui/button';
import {navigationForRole} from './navigation';
import {useAuth} from '@/components/auth/AuthProvider';
import {roleMeetsRequired} from '@/lib/auth/msalConfig';

export function NavigationLinks({collapsed=false,onNavigate}:{collapsed?:boolean;onNavigate?:()=>void}){
 const pathname=usePathname();const {role}=useAuth();const navigation=navigationForRole(role);
 return <nav aria-label="Main navigation" className="space-y-6">{Array.from(new Set(navigation.map(n=>n.group))).map(group=><div key={group} className="space-y-1">{!collapsed&&<p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-400">{group}</p>}{navigation.filter(n=>n.group===group).map(item=>{const active=pathname===item.href;const Icon=item.icon;return <Link key={item.href} href={item.href} onClick={onNavigate} aria-current={active?'page':undefined} aria-label={item.label} title={collapsed?item.label:item.description} className={`flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-colors ${collapsed?'justify-center':''} ${active?'bg-blue-600 text-white shadow-sm shadow-blue-600/15':'text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white'}`}><Icon className="h-[18px] w-[18px] shrink-0"/>{!collapsed&&<span>{item.label}</span>}</Link>;})}</div>)}</nav>;
}
export default function Sidebar(){
 const {sidebarCollapsed,toggleSidebar}=useUIStore();const {role}=useAuth();
 return <aside className={`fixed bottom-0 left-0 top-16 z-30 hidden flex-col border-r bg-white lg:flex dark:bg-slate-950 ${sidebarCollapsed?'w-20':'w-64'}`}>
 <div className="min-h-0 flex-1 overflow-y-auto px-3 py-6"><NavigationLinks collapsed={sidebarCollapsed}/></div>
 {!sidebarCollapsed&&roleMeetsRequired(role,'manager')&&<Link href="/setup" className="mx-4 mb-4 rounded-xl border bg-slate-50 p-3 text-xs text-slate-500 hover:border-blue-200 dark:bg-slate-900"><span className="flex items-center justify-between font-medium text-slate-700 dark:text-slate-200">Data & setup<ArrowUpRight className="h-3.5 w-3.5"/></span><span className="mt-1 block leading-relaxed">Manage your Joolan source and published forecast.</span></Link>}
 <div className="border-t p-3"><Button variant="ghost" className="w-full justify-center text-slate-500" onClick={toggleSidebar} aria-label={sidebarCollapsed?'Expand navigation':'Collapse navigation'}>{sidebarCollapsed?<PanelLeftOpen/>:<><PanelLeftClose/><span className="text-xs">Collapse navigation</span></>}</Button></div>
 </aside>;
}
