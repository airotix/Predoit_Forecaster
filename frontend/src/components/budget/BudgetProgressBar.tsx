"use client";

import React from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertCircle, Wallet } from "lucide-react";

export default function BudgetProgressBar() {
    const { budgetData, isLoading } = useDashboardStore();

    if (isLoading || !budgetData) {
        return (
            <Card className="animate-pulse shadow-sm">
                <CardHeader className="pb-2">
                    <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-32" />
                </CardHeader>
                <CardContent>
                    <div className="h-2 bg-slate-200 dark:bg-slate-800 rounded w-full mb-2" />
                    <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-48" />
                </CardContent>
            </Card>
        );
    }

    const { seasonBudget, forecastSpend } = budgetData;
    const isOverBudget = forecastSpend > seasonBudget;
    const percentage = Math.min((forecastSpend / Math.max(seasonBudget, 1)) * 100, 100);

    const formatCurrency = (val: number) =>
        new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(val);

    return (
        <Card className={`shadow-sm border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 ${isOverBudget ? "ring-1 ring-rose-500" : ""}`}>
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 relative">
                <div className="flex items-center space-x-2">
                    <Wallet className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                    <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">
                        Season Budget vs Forecast
                    </CardTitle>
                </div>
                {isOverBudget && (
                    <Badge variant="destructive" className="bg-rose-500 hover:bg-rose-600 text-white flex items-center gap-1 shadow-sm absolute -top-3 -right-3">
                        <AlertCircle className="h-3 w-3" />
                        Over Budget
                    </Badge>
                )}
            </CardHeader>
            <CardContent>
                <div className="flex justify-between items-end mb-2">
                    <div>
                        <div className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
                            {formatCurrency(forecastSpend)}
                        </div>
                        <div className="text-xs font-medium text-slate-500">
                            Forecast Spend
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                            {formatCurrency(seasonBudget)}
                        </div>
                        <div className="text-xs text-slate-500">Total Budget</div>
                    </div>
                </div>

                <div className="relative pt-1">
                    {/* Custom progress implementation to easily control color changes without digging into shadcn defaults */}
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                        <div
                            className={`h-full transition-all duration-500 ease-in-out ${isOverBudget ? "bg-rose-500" : "bg-blue-600"}`}
                            style={{ width: `${percentage}%` }}
                        />
                    </div>
                    <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                        <span>0%</span>
                        <span>{isOverBudget ? `${Math.round((forecastSpend / seasonBudget) * 100)}%` : `${Math.round(percentage)}%`}</span>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
