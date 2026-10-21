"use client";
// @refresh reset
import {useEffect,useState,type ReactNode} from 'react';
import Link from 'next/link';
import {usePathname,useRouter} from 'next/navigation';
import {ArrowLeftIcon,ArrowRightIcon,ListIcon,MagnifyingGlassIcon,SidebarIcon,SidebarSimpleIcon} from '@phosphor-icons/react';
import Sidebar,{BrandMark,NavigationLinks} from './Sidebar';
import RunStatus from './RunStatus';
import {navigationForRole} from './navigation';
import {useAuth} from '@/components/auth/AuthProvider';
import {useUIStore} from '@/store/uiStore';
import {useSeasonStore} from '@/store/seasonStore';
import {seasonsApi} from '@/lib/api/seasons';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from '@/components/ui/sheet';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '@/components/ui/dialog';
import {ModeToggle} from '@/components/mode-toggle';

export default function AppShell({children}:{children:ReactNode}){
 const {role}=useAuth();const navigation=navigationForRole(role);
 const {sidebarCollapsed,toggleSidebar}=useUIStore();const pathname=usePathname();const router=useRouter();
 const [mobile,setMobile]=useState(false);const [searchOpen,setSearchOpen]=useState(false);const [query,setQuery]=useState('');
 useEffect(()=>{const handler=(event:KeyboardEvent)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();setQuery('');setSearchOpen(v=>!v);}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[]);
 // Saved seasons and the active season feed every page; load them once per shell mount.
 useEffect(()=>{let alive=true;Promise.all([seasonsApi.list(),seasonsApi.active()]).then(([saved,active])=>{if(alive)useSeasonStore.setState({seasons:saved,activeSeason:active,error:null});}).catch(e=>{if(alive)useSeasonStore.setState({error:String(e)});});return()=>{alive=false;};},[]);
 const matches=navigation.filter(n=>`${n.label} ${n.group} ${n.description}`.toLowerCase().includes(query.toLowerCase()));
 const index=navigation.findIndex(n=>n.href===pathname);const previous=navigation[index-1],next=navigation[index+1];
 function navigate(href:string){setSearchOpen(false);setMobile(false);router.push(href);}
 return <div className="flex min-h-screen bg-page text-fg-1">
  <a href="#workspace-content" className="sr-only fixed left-4 top-4 z-[100] rounded-lg bg-brand px-4 py-2 text-white focus:not-sr-only">Skip to page content</a>
  <Sidebar/>
  <div className="flex min-w-0 flex-1 flex-col">
   <header className="sticky top-0 z-20 flex h-[68px] items-center gap-3 border-b border-line bg-chrome px-4 backdrop-blur-[10px] lg:pl-5 lg:pr-8">
    <button type="button" aria-label="Open navigation" onClick={()=>setMobile(true)} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-fg-1 hover:bg-soft lg:hidden"><ListIcon className="h-[22px] w-[22px]"/></button>
    <button type="button" aria-label={sidebarCollapsed?'Expand navigation':'Collapse navigation'} title={sidebarCollapsed?'Expand navigation':'Collapse navigation'} onClick={toggleSidebar} className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-fg-3 hover:bg-soft hover:text-fg-1 lg:flex">{sidebarCollapsed?<SidebarIcon className="h-[19px] w-[19px]"/>:<SidebarSimpleIcon className="h-[19px] w-[19px]"/>}</button>
    <div className="flex-1"/>
    <ModeToggle/>
   </header>
   <main id="workspace-content" tabIndex={-1} className="app-content mx-auto flex w-full max-w-[1560px] flex-1 flex-col gap-7 px-4 pb-8 pt-5 outline-none lg:px-10 lg:pb-12 lg:pt-8">
    <nav aria-label="Continue planning" className="-mb-1 flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
     {previous?<Link href={previous.href} className="flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-sm text-fg-2 hover:bg-card hover:text-fg-1"><ArrowLeftIcon className="h-4 w-4"/>Back to {previous.label}</Link>:<span className="py-2.5 text-sm text-fg-3">Connect your data to begin planning</span>}
     {next&&<Link href={next.href} className="flex items-center gap-2 rounded-full bg-brand-soft px-4 py-2.5 text-sm font-bold text-brand-800 hover:bg-brand-200">Continue to {next.label}<ArrowRightIcon className="h-4 w-4"/></Link>}
    </nav>
    <RunStatus/>
    {children}
   </main>
  </div>
  <Sheet open={mobile} onOpenChange={setMobile}><SheetContent side="left" className="flex w-[300px] max-w-[90vw] flex-col gap-0 border-line bg-card p-0">
   <SheetHeader className="flex-row items-center gap-3 space-y-0 border-b border-line p-5 pr-12 text-left"><BrandMark/><div><SheetTitle className="font-display text-lg font-bold">Preduit</SheetTitle><SheetDescription className="mt-0.5 text-xs text-fg-3">Choose a page in your planning workflow.</SheetDescription></div></SheetHeader>
   <div className="min-h-0 flex-1 overflow-auto p-3"><NavigationLinks onNavigate={()=>setMobile(false)}/></div>
   <div className="flex items-center justify-between border-t border-line px-5 py-4 text-sm"><span>Appearance</span><ModeToggle/></div>
  </SheetContent></Sheet>
  <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent className="top-[12vh] max-w-[580px] translate-y-0 gap-0 rounded-[28px] border-line bg-card p-6 shadow-lift data-[state=closed]:slide-out-to-top-0 data-[state=open]:slide-in-from-top-0 sm:rounded-[28px]">
   <DialogHeader className="space-y-1 text-left"><DialogTitle className="text-[22px] font-extrabold tracking-[-0.02em]">Find a page</DialogTitle><DialogDescription className="text-sm text-fg-3">Search your planning tools, then choose where to go.</DialogDescription></DialogHeader>
   <div className="relative mt-[18px] flex items-center"><MagnifyingGlassIcon className="absolute left-4 h-[17px] w-[17px] text-fg-3"/><input autoFocus aria-label="Search pages" placeholder="Try budget, stock, orders or customers…" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&matches[0])navigate(matches[0].href);}} className="h-[50px] w-full rounded-[14px] border-[1.5px] border-border-strong bg-card pl-11 pr-4 text-[15px] text-fg-1 outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(245,130,32,0.35)]"/></div>
   <div className="mt-3 flex max-h-[52vh] flex-col gap-0.5 overflow-auto">
    {matches.map(item=>{const Icon=item.icon;return <button key={item.href} type="button" onClick={()=>navigate(item.href)} className="flex w-full items-center gap-3.5 rounded-2xl p-3 text-left text-fg-1 hover:bg-soft">
     <span className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand"><Icon weight={item.href===pathname?'fill':'regular'} className="h-[18px] w-[18px]"/></span>
     <span className="min-w-0 flex-1"><span className="block text-[15px] font-bold">{item.label}</span><span className="mt-0.5 block text-[13px] leading-[1.45] text-fg-3">{item.description}</span></span>
     <ArrowRightIcon className="h-4 w-4 text-fg-3"/></button>;})}
    {!matches.length&&<p className="p-6 text-center text-sm text-fg-3">No pages match. Try another word.</p>}
   </div>
  </DialogContent></Dialog>
 </div>;
}
