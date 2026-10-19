"use client";
import {useEffect} from 'react';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {LayoutDashboard,Menu,Search,Settings2} from 'lucide-react';
import {seasonsApi} from '@/lib/api/seasons';
import {useSeasonStore} from '@/store/seasonStore';
import {ModeToggle} from '@/components/mode-toggle';
import {Button} from '@/components/ui/button';
import {Select,SelectContent,SelectItem,SelectTrigger,SelectValue} from '@/components/ui/select';
import {navigation} from './navigation';
import AccountMenu from './AccountMenu';
export default function TopNav({onMenu,onSearch}:{onMenu:()=>void;onSearch:()=>void}){
 const {activeSeason,seasons,setActiveSeason,error}=useSeasonStore();const pathname=usePathname();const current=navigation.find(n=>n.href===pathname);
 useEffect(()=>{let alive=true;Promise.all([seasonsApi.list(),seasonsApi.active()]).then(([saved,active])=>{if(alive)useSeasonStore.setState({seasons:saved,activeSeason:active,error:null});}).catch(e=>{if(alive)useSeasonStore.setState({error:String(e)});});return()=>{alive=false;};},[]);
 return <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between gap-3 border-b bg-white/95 px-3 backdrop-blur-md sm:px-5 dark:bg-slate-950/95">
 <div className="flex min-w-0 items-center gap-3"><Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" onClick={onMenu}><Menu/></Button><Link href="/dashboard" aria-label="Demand Planning dashboard" className="flex shrink-0 items-center gap-2.5"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm"><LayoutDashboard className="h-5 w-5"/></span><span className="hidden text-sm font-semibold tracking-tight sm:block">Demand Planning</span></Link><div className="ml-5 hidden items-center gap-3 border-l pl-5 text-sm xl:flex"><span className="text-slate-400">{current?.group}</span><span className="font-medium">{current?.label}</span></div></div>
 <div className="flex items-center gap-2"><span className="hidden text-xs text-slate-400 xl:block">Planning season</span><Select value={activeSeason?.id||''} onValueChange={id=>{const season=seasons.find(s=>s.id===id);if(season)setActiveSeason(season);}}><SelectTrigger aria-label="Select planning season" className="h-9 w-[145px] rounded-lg bg-slate-50 text-xs sm:w-[240px] dark:bg-slate-900"><SelectValue placeholder={error?'Connection unavailable':'Select season'}/></SelectTrigger><SelectContent>{seasons.length?seasons.map(s=><SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>):<SelectItem value="none" disabled>No saved seasons</SelectItem>}</SelectContent></Select><Button variant="outline" onClick={onSearch} aria-label="Find a page" className="hidden h-9 text-slate-500 md:inline-flex"><Search/><span className="hidden lg:inline">Find a page</span><kbd className="hidden rounded border px-1.5 py-0.5 text-[10px] lg:inline">Ctrl K</kbd></Button><Button variant="ghost" size="icon" aria-label="Find a page" className="md:hidden" onClick={onSearch}><Search/></Button><span className="hidden sm:inline-flex"><ModeToggle/></span><Button asChild variant="ghost" size="icon" className="hidden xl:inline-flex"><Link href="/setup" aria-label="Open data settings"><Settings2/></Link></Button><AccountMenu/></div>
 </header>;
}
