"use client";
// @refresh reset
import {useEffect,useState,type ReactNode} from 'react';
import Link from 'next/link';
import {usePathname,useRouter} from 'next/navigation';
import {ArrowLeft,ArrowRight,Search} from 'lucide-react';
import TopNav from './TopNav';
import Sidebar,{NavigationLinks} from './Sidebar';
import RunStatus from './RunStatus';
import {navigationForRole} from './navigation';
import {useAuth} from '@/components/auth/AuthProvider';
import {useUIStore} from '@/store/uiStore';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from '@/components/ui/sheet';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '@/components/ui/dialog';
import {Input} from '@/components/ui/input';
import {ModeToggle} from '@/components/mode-toggle';
export default function AppShell({children}:{children:ReactNode}){
 const {role}=useAuth();const navigation=navigationForRole(role);
 const {sidebarCollapsed}=useUIStore();const pathname=usePathname();const router=useRouter();
 const [mobile,setMobile]=useState(false);const [searchOpen,setSearchOpen]=useState(false);const [query,setQuery]=useState('');
 useEffect(()=>{const handler=(event:KeyboardEvent)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();setSearchOpen(v=>!v);}};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[]);
 const matches=navigation.filter(n=>`${n.label} ${n.group} ${n.description}`.toLowerCase().includes(query.toLowerCase()));
 const index=navigation.findIndex(n=>n.href===pathname);const previous=navigation[index-1],next=navigation[index+1];
 function navigate(href:string){setSearchOpen(false);setMobile(false);router.push(href);}
 return <div className="min-h-screen bg-slate-50/80 dark:bg-slate-950"><a href="#workspace-content" className="sr-only fixed left-4 top-4 z-[100] rounded-lg bg-blue-600 px-4 py-2 text-white focus:not-sr-only">Skip to page content</a>
 <TopNav onMenu={()=>setMobile(true)} onSearch={()=>{setQuery('');setSearchOpen(true);}}/><Sidebar/>
 <main id="workspace-content" tabIndex={-1} className={`min-w-0 pt-16 ${sidebarCollapsed?'lg:pl-20':'lg:pl-64'}`}><div className="app-content mx-auto min-h-[calc(100vh-4rem)] max-w-[1800px] px-4 py-6 sm:px-6 lg:px-8"><RunStatus/>{children}<nav aria-label="Continue planning" className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t pt-5 text-xs text-slate-500">{previous?<Link href={previous.href} className="flex items-center gap-2 rounded-lg p-2 hover:bg-white hover:text-blue-600 dark:hover:bg-slate-900"><ArrowLeft className="h-4 w-4"/><span>Back to {previous.label}</span></Link>:<span>Connect your data to begin planning</span>}{next&&<Link href={next.href} className="flex items-center gap-2 rounded-lg p-2 font-medium text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950"><span>Continue to {next.label}</span><ArrowRight className="h-4 w-4"/></Link>}</nav></div></main>
 <Sheet open={mobile} onOpenChange={setMobile}><SheetContent side="left" className="flex w-[300px] max-w-[90vw] flex-col p-0"><SheetHeader className="border-b p-5 text-left"><SheetTitle>Demand Planning</SheetTitle><SheetDescription>Choose a page in your planning workflow.</SheetDescription></SheetHeader><div className="min-h-0 flex-1 overflow-auto p-4"><NavigationLinks onNavigate={()=>setMobile(false)}/></div><div className="flex items-center justify-between border-t p-4 text-sm"><span>Appearance</span><ModeToggle/></div></SheetContent></Sheet>
 <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent className="max-w-xl"><DialogHeader><DialogTitle>Find a page</DialogTitle><DialogDescription>Search your planning tools, then choose where to go.</DialogDescription></DialogHeader><div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400"/><Input autoFocus aria-label="Search pages" className="pl-9" placeholder="Try budget, stock, orders or customers…" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&matches[0])navigate(matches[0].href);}}/></div><div className="max-h-[55vh] overflow-auto space-y-1">{matches.map(item=><button key={item.href} onClick={()=>navigate(item.href)} className="flex w-full items-center gap-3 rounded-xl p-3 text-left hover:bg-blue-50 dark:hover:bg-blue-950"><item.icon className="h-5 w-5 shrink-0 text-blue-600"/><div className="min-w-0 flex-1"><p className="text-sm font-medium">{item.label}</p><p className="mt-1 text-xs text-slate-500">{item.description}</p></div><ArrowRight className="h-4 w-4 text-slate-400"/></button>)}{!matches.length&&<p className="p-6 text-center text-sm text-slate-500">No pages match. Try another word.</p>}</div></DialogContent></Dialog>
 </div>;
}
