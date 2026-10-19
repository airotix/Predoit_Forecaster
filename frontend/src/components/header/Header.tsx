"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import SeasonSelector from "./SeasonSelector";
import FilterPanel from "@/components/filters/FilterPanel";
import { ModeToggle } from "@/components/mode-toggle";
import { Search, LayoutDashboard, UserCircle2, Package } from "lucide-react";
import { useDashboardStore } from "@/store/dashboardStore";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";
import { Button } from "@/components/ui/button";
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";

const SEARCH_DEBOUNCE_MS = 350;

export default function Header() {
    const pathname = usePathname();
    const { filters, setSearchQuery } = useDashboardStore();
    const [searchInput, setSearchInput] = useState(filters.searchQuery ?? "");
    const [searchSheetOpen, setSearchSheetOpen] = useState(false);
    const isDashboard = pathname === "/";
    const isCustomers = pathname === "/customers";

    useEffect(() => {
        setSearchInput(filters.searchQuery ?? "");
    }, [filters.searchQuery]);

    const debouncedSetSearch = useDebouncedCallback(setSearchQuery, SEARCH_DEBOUNCE_MS);

    const searchInputEl = (
        <>
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-500 pointer-events-none" />
            <input
                type="search"
                placeholder="Search SKUs, Suppliers..."
                className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 pl-9 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-50"
                value={searchInput}
                onChange={(e) => {
                    const v = e.target.value;
                    setSearchInput(v);
                    debouncedSetSearch(v);
                }}
                aria-label="Search SKUs and suppliers"
            />
        </>
    );

    return (
        <header className="sticky top-0 z-40 w-full border-b bg-white dark:bg-slate-950 shadow-sm" suppressHydrationWarning>
            <div className="container mx-auto flex h-16 items-center justify-between px-4 md:px-6" suppressHydrationWarning>
                <div className="flex items-center gap-4" suppressHydrationWarning>
                    <Link href="/" className="flex items-center gap-2 rounded-md hover:opacity-90 transition-opacity shrink-0">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white" suppressHydrationWarning>
                            <LayoutDashboard size={18} />
                        </div>
                        <h1 className="text-xl font-bold tracking-tight hidden sm:block">AI Forecasting Dashboard</h1>
                    </Link>
                    <nav className="flex items-center gap-0.5 border border-slate-200 dark:border-slate-800 rounded-lg p-0.5 bg-slate-50 dark:bg-slate-900/50" aria-label="Main navigation">
                        <Link
                            href="/"
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors shrink-0 ${isDashboard
                                ? "bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm border border-slate-200 dark:border-slate-700"
                                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-white/50 dark:hover:bg-slate-800/50"
                                }`}
                        >
                            <Package className="h-4 w-4" />
                            <span className="hidden sm:inline">Dashboard</span>
                        </Link>
                        <Link
                            href="/customers"
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors shrink-0 ${isCustomers
                                ? "bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm border border-slate-200 dark:border-slate-700"
                                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-white/50 dark:hover:bg-slate-800/50"
                                }`}
                        >
                            <UserCircle2 className="h-4 w-4" />
                            <span className="hidden sm:inline">Customers</span>
                        </Link>
                    </nav>
                </div>

                <div className="flex flex-1 items-center justify-end space-x-4 ml-6" suppressHydrationWarning>
                    {isDashboard && (
                        <>
                            <SeasonSelector />
                            <div className="relative w-full max-w-sm hidden md:flex items-center" suppressHydrationWarning>
                                {searchInputEl}
                            </div>
                            <Sheet open={searchSheetOpen} onOpenChange={setSearchSheetOpen}>
                                <SheetTrigger asChild>
                                    <Button variant="outline" size="icon" className="h-10 w-10 md:hidden shrink-0" aria-label="Open search">
                                        <Search className="h-4 w-4" />
                                    </Button>
                                </SheetTrigger>
                                <SheetContent side="top" className="pt-6">
                                    <SheetHeader className="mb-4">
                                        <SheetTitle>Search</SheetTitle>
                                    </SheetHeader>
                                    <div className="relative">
                                        <Input
                                            type="search"
                                            placeholder="Search SKUs, Suppliers..."
                                            className="pl-9 h-11 text-base"
                                            value={searchInput}
                                            onChange={(e) => {
                                                const v = e.target.value;
                                                setSearchInput(v);
                                                debouncedSetSearch(v);
                                            }}
                                            autoFocus
                                            aria-label="Search SKUs and suppliers"
                                        />
                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
                                    </div>
                                </SheetContent>
                            </Sheet>
                            <FilterPanel />
                        </>
                    )}
                    <ModeToggle />
                </div>
            </div>
        </header>
    );
}
