"use client";

import React, { useMemo } from "react";
import { useTheme } from "next-themes";
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Legend,
} from "recharts";
import { ArticleData } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, BarChart2 } from "lucide-react";

const CHART_COLORS_LIGHT = {
    grid: "#e2e8f0",
    tick: "#64748b",
    tooltipBorder: "#e2e8f0",
    tooltipBg: "#ffffff",
    line: "#3b82f6",
    barForecast: "#3b82f6",
    barStock: "#94a3b8",
    barOrders: "#14b8a6",
};
const CHART_COLORS_DARK = {
    grid: "#334155",
    tick: "#94a3b8",
    tooltipBorder: "#475569",
    tooltipBg: "#1e293b",
    line: "#60a5fa",
    barForecast: "#60a5fa",
    barStock: "#64748b",
    barOrders: "#2dd4bf",
};

interface ForecastChartsProps {
    article: ArticleData;
}

export default function ForecastCharts({ article }: ForecastChartsProps) {
    const { resolvedTheme } = useTheme();
    const isDark = resolvedTheme === "dark";
    const colors = isDark ? CHART_COLORS_DARK : CHART_COLORS_LIGHT;
    // Aggregate matrix data for size distribution chart
    const sizeData = useMemo(() => {
        return article.sizes.map((size) => {
            let totalForecast = 0;
            let totalStock = 0;
            let totalOrders = 0;

            article.colors.forEach((color) => {
                const cell = article.matrix[color]?.[size];
                if (cell) {
                    totalForecast += cell.forecast;
                    totalStock += cell.stock;
                    totalOrders += cell.orders;
                }
            });

            return {
                name: size,
                Forecast: totalForecast,
                Stock: totalStock,
                Orders: totalOrders,
            };
        });
    }, [article.matrix, article.sizes, article.colors]);

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Demand Forecast Trend */}
            <Card className="shadow-sm border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
                <CardHeader className="flex flex-row items-center gap-2 pb-2">
                    <TrendingUp className="h-5 w-5 text-blue-500" />
                    <CardTitle className="text-base font-semibold">Demand Forecast Trend</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-[300px] w-full mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart
                                data={article.demandTrend}
                                margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={colors.grid} />
                                <XAxis
                                    dataKey="date"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: colors.tick, fontSize: 12 }}
                                    dy={10}
                                />
                                <YAxis
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: colors.tick, fontSize: 12 }}
                                    dx={-10}
                                />
                                <Tooltip
                                    contentStyle={{
                                        borderRadius: "8px",
                                        border: `1px solid ${colors.tooltipBorder}`,
                                        backgroundColor: colors.tooltipBg,
                                        boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
                                    }}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="value"
                                    name="Projected Demand"
                                    stroke={colors.line}
                                    strokeWidth={3}
                                    dot={{ r: 4, strokeWidth: 2 }}
                                    activeDot={{ r: 6, strokeWidth: 0 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </CardContent>
            </Card>

            {/* Size Distribution */}
            <Card className="shadow-sm border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950">
                <CardHeader className="flex flex-row items-center gap-2 pb-2">
                    <BarChart2 className="h-5 w-5 text-indigo-500" />
                    <CardTitle className="text-base font-semibold">Size Distribution</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="h-[300px] w-full mt-4">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                data={sizeData}
                                margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={colors.grid} />
                                <XAxis
                                    dataKey="name"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: colors.tick, fontSize: 12, fontWeight: 500 }}
                                    dy={10}
                                />
                                <YAxis
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: colors.tick, fontSize: 12 }}
                                    dx={-10}
                                />
                                <Tooltip
                                    cursor={{ fill: "transparent" }}
                                    contentStyle={{
                                        borderRadius: "8px",
                                        border: `1px solid ${colors.tooltipBorder}`,
                                        backgroundColor: colors.tooltipBg,
                                        boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
                                    }}
                                />
                                <Legend iconType="circle" wrapperStyle={{ paddingTop: "20px" }} />
                                <Bar dataKey="Forecast" fill={colors.barForecast} radius={[4, 4, 0, 0]} maxBarSize={40} />
                                <Bar dataKey="Stock" fill={colors.barStock} radius={[4, 4, 0, 0]} maxBarSize={40} />
                                <Bar dataKey="Orders" fill={colors.barOrders} radius={[4, 4, 0, 0]} maxBarSize={40} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
