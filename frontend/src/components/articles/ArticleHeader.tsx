"use client";

import React, { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Building2, ShoppingBag, Check, ChevronsUpDown, Calendar, Tag, DollarSign, Percent } from "lucide-react";
import { useDashboardStore } from "@/store/dashboardStore";
import { cn } from "@/lib/utils";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command";

interface ArticleHeaderProps {
    id: string;
    supplier: string;
    customer: string;
    model: string;
    family: string;
    theme?: string;
    season?: string;
    price?: number;
    cost?: number;
}

export default function ArticleHeader({
    id,
    supplier,
    customer,
    model,
    family,
    theme = "—",
    season = "—",
    price = 0,
    cost = 0,
}: ArticleHeaderProps) {
    const { articles, setSelectedArticleId } = useDashboardStore();
    const [open, setOpen] = useState(false);
    const marginRate = price > 0 ? ((price - cost) / price) * 100 : 0;

    return (
        <div className="flex flex-col gap-4 pb-6 border-b border-slate-200 dark:border-slate-800 transition-opacity duration-200">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <div className="flex flex-wrap items-center gap-3 mb-2">
                        <Popover open={open} onOpenChange={setOpen}>
                            <PopoverTrigger asChild>
                                <button
                                    role="combobox"
                                    aria-expanded={open}
                                    aria-controls="article-selector-options"
                                    className="flex items-center justify-between text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50 hover:bg-slate-100 dark:hover:bg-slate-800/50 px-2 py-1 -ml-2 rounded-md transition-colors duration-150"
                                    style={{ minWidth: "200px" }}
                                >
                                    <span className="font-mono">{id}</span>
                                    <ChevronsUpDown className="ml-2 h-5 w-5 opacity-50 shrink-0" />
                                </button>
                            </PopoverTrigger>
                            <PopoverContent id="article-selector-options" className="w-[320px] p-0" align="start">
                                <Command>
                                    <CommandInput placeholder="Search by SKU, supplier, model..." />
                                    <CommandList>
                                        <CommandEmpty>No match.</CommandEmpty>
                                        <CommandGroup>
                                            {articles.map((article) => (
                                                <CommandItem
                                                    key={article.id}
                                                    value={`${article.id} ${article.supplier} ${article.model}`}
                                                    onSelect={() => {
                                                        setSelectedArticleId(article.id);
                                                        setOpen(false);
                                                    }}
                                                >
                                                    <Check className={cn("mr-2 h-4 w-4", id === article.id ? "opacity-100" : "opacity-0")} />
                                                    <span className="font-mono text-sm">{article.id}</span>
                                                    <span className="ml-2 text-xs text-slate-400 truncate">{article.supplier} · {article.model}</span>
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </CommandList>
                                </Command>
                            </PopoverContent>
                        </Popover>
                        <Badge variant="secondary" className="rounded-md text-xs text-blue-700 bg-blue-100 dark:bg-blue-900/40 dark:text-blue-400 border border-blue-200 dark:border-blue-800">
                            {family}
                        </Badge>
                        <Badge variant="outline" className="border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-xs">
                            {model}
                        </Badge>
                        {theme && theme !== "—" && (
                            <Badge variant="outline" className="border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400 text-xs">
                                <Tag className="mr-1 h-3 w-3" />
                                {theme}
                            </Badge>
                        )}
                        {season && season !== "All" && season !== "—" && (
                            <Badge variant="outline" className="border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-xs">
                                <Calendar className="mr-1 h-3 w-3" />
                                {season}
                            </Badge>
                        )}
                    </div>
                </div>
                <div className="flex flex-wrap gap-3">
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white dark:bg-slate-950 dark:border-slate-800 shadow-sm text-sm transition-colors duration-150">
                        <Building2 className="h-4 w-4 text-emerald-600 dark:text-emerald-500 shrink-0" />
                        <span className="font-medium text-slate-700 dark:text-slate-300">{supplier}</span>
                        <span className="text-slate-400 text-xs uppercase tracking-wider">Supplier</span>
                    </div>
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white dark:bg-slate-950 dark:border-slate-800 shadow-sm text-sm transition-colors duration-150">
                        <ShoppingBag className="h-4 w-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
                        <span className="font-medium text-slate-700 dark:text-slate-300">{customer}</span>
                        <span className="text-slate-400 text-xs uppercase tracking-wider">Customer</span>
                    </div>
                    {price > 0 && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white dark:bg-slate-950 dark:border-slate-800 shadow-sm text-sm transition-colors duration-150">
                            <DollarSign className="h-4 w-4 text-emerald-600 dark:text-emerald-500 shrink-0" />
                            <span className="font-medium text-slate-700 dark:text-slate-300">
                                {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(price)}
                            </span>
                            <span className="text-slate-400 text-xs">Price</span>
                        </div>
                    )}
                    {cost > 0 && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white dark:bg-slate-950 dark:border-slate-800 shadow-sm text-sm transition-colors duration-150">
                            <Percent className="h-4 w-4 text-slate-500 shrink-0" />
                            <span className="font-medium text-slate-700 dark:text-slate-300">
                                {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(cost)}
                            </span>
                            <span className="text-slate-400 text-xs">Cost · {marginRate.toFixed(0)}% margin</span>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
