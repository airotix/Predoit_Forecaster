"use client";
import Link from 'next/link';
import {LogOut,Settings,User} from 'lucide-react';
import {useAuth} from '@/components/auth/AuthProvider';
import {Button} from '@/components/ui/button';
import {DropdownMenu,DropdownMenuContent,DropdownMenuItem,DropdownMenuLabel,DropdownMenuSeparator,DropdownMenuTrigger} from '@/components/ui/dropdown-menu';

export default function AccountMenu(){
 const {account,user,logout,role}=useAuth();
 return <DropdownMenu><DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="User menu"><User className="h-5 w-5"/></Button></DropdownMenuTrigger><DropdownMenuContent align="end" className="w-56"><DropdownMenuLabel>{user?.name||account?.name||account?.username||'My account'}</DropdownMenuLabel><DropdownMenuLabel className="text-xs font-normal capitalize text-slate-500">Role: {role}</DropdownMenuLabel><DropdownMenuSeparator/><DropdownMenuItem asChild><Link href="/settings"><Settings className="mr-2 h-4 w-4"/>Settings</Link></DropdownMenuItem><DropdownMenuSeparator/><DropdownMenuItem onClick={()=>void logout()} className="text-rose-600"><LogOut className="mr-2 h-4 w-4"/>Log out</DropdownMenuItem></DropdownMenuContent></DropdownMenu>;
}
