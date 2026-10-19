import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricTrend } from "@/types";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

interface KPICardProps {
    title: string;
    metric: MetricTrend;
    icon: React.ReactNode;
    formatValue?: (value: number) => string;
}

export default function KPICard({ title, metric, icon, formatValue }: KPICardProps) {
    const isUp = metric.trend === "up";
    const isDown = metric.trend === "down";

    // Determine trend coloring (good/bad context depends on the metric, keeping it green=up, red=down for demo)
    const trendColor = isUp ? "text-emerald-500" : isDown ? "text-rose-500" : "text-slate-500";
    const TrendIcon = isUp ? ArrowUpRight : isDown ? ArrowDownRight : Minus;

    return (
        <Card className="shadow-sm border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400">
                    {title}
                </CardTitle>
                <div className="h-4 w-4 text-slate-400 dark:text-slate-500">
                    {icon}
                </div>
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-50">
                    {formatValue ? formatValue(metric.value) : metric.value.toLocaleString()}
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center">
                    <span className={`inline-flex items-center font-medium mr-1.5 ${trendColor}`}>
                        <TrendIcon className="mr-0.5 h-3 w-3" />
                        {metric.percentage}%
                    </span>
                    vs last season
                </p>
                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5" aria-hidden="true">
                    Sample trend
                </p>
            </CardContent>
        </Card>
    );
}
