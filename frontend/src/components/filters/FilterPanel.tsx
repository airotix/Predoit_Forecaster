"use client";

import React, { useEffect, useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";
import { Filter, Search } from "lucide-react";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from "@/components/ui/sheet";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const SEARCH_DEBOUNCE_MS = 350;

export default function FilterPanel() {
    const { filters, setFilter, setSearchQuery, filterOptions } = useDashboardStore();
    const [isOpen, setIsOpen] = useState(false);
    const [searchInput, setSearchInput] = useState(filters.searchQuery ?? "");

    useEffect(() => {
        setSearchInput(filters.searchQuery ?? "");
    }, [filters.searchQuery]);

    const debouncedSetSearch = useDebouncedCallback(setSearchQuery, SEARCH_DEBOUNCE_MS);

    const options = {
        suppliers: filterOptions?.suppliers ?? [],
        families: filterOptions?.families ?? [],
        themes: filterOptions?.themes ?? [],
        models: filterOptions?.models ?? [],
        customers: filterOptions?.customers ?? [],
    };

    const activeFiltersCount = Object.entries(filters).filter(
        ([key, val]) => val !== "All" && val !== "" && key !== "searchQuery"
    ).length;

    const resetAll = () => {
        setFilter("supplier", "All");
        setFilter("family", "All");
        setFilter("theme", "All");
        setFilter("model", "All");
        setFilter("customer", "All");
        setSearchQuery("");
    };

    return (
        <Sheet open={isOpen} onOpenChange={setIsOpen}>
            <SheetTrigger asChild>
                <Button variant="outline" className="relative h-10 px-4 group">
                    <Filter className="mr-2 h-4 w-4 text-slate-500 group-hover:text-amber-500 transition-colors" />
                    More Filters
                    {activeFiltersCount > 0 && (
                        <span className="absolute -top-2 -right-2 flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] font-bold text-white shadow-sm ring-2 ring-white">
                            {activeFiltersCount}
                        </span>
                    )}
                </Button>
            </SheetTrigger>

            <SheetContent className="w-[400px] sm:w-[540px] overflow-y-auto">
                <SheetHeader>
                    <SheetTitle className="text-xl">Dashboard Filters</SheetTitle>
                    <SheetDescription>
                        Refine the forecast view by specific attributes.
                    </SheetDescription>
                </SheetHeader>

                <div className="grid gap-6 py-6">
                    <div className="space-y-2">
                        <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                            Article Search
                        </label>
                        <div className="relative">
                            <Search className="absolute left-2 top-2.5 h-4 w-4 text-slate-500" />
                            <Input
                                placeholder="Search SKU or name..."
                                value={searchInput}
                                onChange={(e) => {
                                    const v = e.target.value;
                                    setSearchInput(v);
                                    debouncedSetSearch(v);
                                }}
                                className="pl-8 bg-slate-50/50"
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium">Supplier</label>
                        <Select value={filters.supplier || "All"} onValueChange={(val) => setFilter("supplier", val)}>
                            <SelectTrigger className="w-full bg-slate-50/50">
                                <SelectValue placeholder="Select Supplier" />
                            </SelectTrigger>
                            <SelectContent>
                                {options.suppliers.map((opt: string) => (
                                    <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium">Customer</label>
                        <Select value={filters.customer || "All"} onValueChange={(val) => setFilter("customer", val)}>
                            <SelectTrigger className="w-full bg-slate-50/50">
                                <SelectValue placeholder="Select Customer" />
                            </SelectTrigger>
                            <SelectContent>
                                {options.customers.map((opt: string) => (
                                    <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <label className="text-sm font-medium">Family</label>
                            <Select value={filters.family || "All"} onValueChange={(val) => setFilter("family", val)}>
                                <SelectTrigger className="w-full bg-slate-50/50">
                                    <SelectValue placeholder="Select Family" />
                                </SelectTrigger>
                                <SelectContent>
                                    {options.families.map((opt: string) => (
                                        <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium">Theme</label>
                            <Select value={filters.theme || "All"} onValueChange={(val) => setFilter("theme", val)}>
                                <SelectTrigger className="w-full bg-slate-50/50">
                                    <SelectValue placeholder="Select Theme" />
                                </SelectTrigger>
                                <SelectContent>
                                    {options.themes.map((opt: string) => (
                                        <SelectItem key={opt || "—"} value={opt}>
                                            {opt === "" ? "—" : opt}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label className="text-sm font-medium">Model</label>
                        <Select value={filters.model || "All"} onValueChange={(val) => setFilter("model", val)}>
                            <SelectTrigger className="w-full bg-slate-50/50">
                                <SelectValue placeholder="Select Model" />
                            </SelectTrigger>
                            <SelectContent>
                                {options.models.map((opt: string) => (
                                    <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="pt-4 flex gap-4">
                        <Button className="w-full" onClick={() => setIsOpen(false)}>
                            Apply Filters
                        </Button>
                        <Button variant="outline" className="w-full" onClick={resetAll}>
                            Reset All
                        </Button>
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    );
}
