"use client";

import React, { useRef } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { useVirtualizer } from "@tanstack/react-virtual";
import { PackageOpen } from "lucide-react";

export default function ArticleTabs() {
    const { articles, selectedArticleId, setSelectedArticleId, filters } = useDashboardStore();
    const showSku = Boolean(filters.searchQuery?.trim());
    const parentRef = useRef<HTMLDivElement>(null);

    // Virtualizer for horizontal tabs
    const rowVirtualizer = useVirtualizer({
        count: articles.length,
        getScrollElement: () => parentRef.current,
        estimateSize: () => 140, // approximate width of a tab
        horizontal: true,
    });

    if (articles.length === 0) {
        return (
            <div className="flex h-20 items-center justify-center rounded-lg border border-dashed border-slate-300 dark:border-slate-800">
                <div className="flex items-center text-slate-500">
                    <PackageOpen className="mr-2 h-4 w-4 opacity-50" />
                    <span className="text-sm font-medium">No articles match your filters</span>
                </div>
            </div>
        );
    }

    const tabPanelId = "article-detail-panel";

    return (
        <div className="relative border-b border-t border-slate-200 bg-white/50 backdrop-blur-sm dark:border-slate-800 dark:bg-slate-950/50 transition-opacity duration-200" role="tablist" aria-label="Articles">
            <div
                ref={parentRef}
                className="flex w-full overflow-x-auto hide-scrollbar scroll-smooth overscroll-x-contain"
                style={{ height: "52px" }}
            >
                <div
                    className="relative flex items-end h-full"
                    style={{ width: `${rowVirtualizer.getTotalSize()}px` }}
                >
                    {rowVirtualizer.getVirtualItems().map((virtualItem) => {
                        const article = articles[virtualItem.index];
                        const isSelected = selectedArticleId === article.id;
                        const tabId = `article-tab-${article.id}`;

                        return (
                            <button
                                key={virtualItem.key}
                                id={tabId}
                                role="tab"
                                aria-selected={isSelected}
                                aria-controls={tabPanelId}
                                tabIndex={isSelected ? 0 : -1}
                                className={`absolute top-0 bottom-0 px-4 flex items-center justify-center whitespace-nowrap text-sm font-medium transition-all duration-200 ease-out hover:bg-slate-50/80 dark:hover:bg-slate-800/50 truncate focus-visible:outline-none focus-visible:bg-slate-100 ${isSelected
                                        ? "text-blue-600 border-b-2 border-blue-600 dark:text-blue-400 dark:border-blue-400 bg-blue-50/30 dark:bg-blue-900/10"
                                        : "text-slate-600 dark:text-slate-400 border-b-2 border-transparent"
                                    }`}
                                style={{
                                    width: `${virtualItem.size}px`,
                                    transform: `translateX(${virtualItem.start}px)`,
                                }}
                                onClick={() => setSelectedArticleId(article.id)}
                                title={showSku ? `${article.id} · ${article.model}` : `${article.supplier} · ${article.model} (${article.id})`}
                            >
                                <div className="flex gap-2 items-center truncate max-w-full w-full">
                                    {showSku ? (
                                        <>
                                            <span className="font-semibold">{article.id}</span>
                                            <span className="text-xs opacity-70 truncate hidden sm:inline-block">{article.model}</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="font-semibold truncate">{article.supplier}</span>
                                            <span className="text-slate-400 dark:text-slate-500">·</span>
                                            <span className="text-xs opacity-80 truncate">{article.model}</span>
                                        </>
                                    )}
                                </div>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
