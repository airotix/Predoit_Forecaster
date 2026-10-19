"use client";

import React, { useMemo } from "react";
import {
    useReactTable,
    getCoreRowModel,
    flexRender,
    createColumnHelper,
} from "@tanstack/react-table";
import { ForecastMatrixValue } from "@/types";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface StockOrdersTableProps {
    sizes: string[];
    colors: string[];
    matrix: Record<string, Record<string, ForecastMatrixValue>>;
}

export default function StockOrdersTable({ sizes, colors, matrix }: StockOrdersTableProps) {
    // Aggregate data across all colors for the multi-row view breakdown
    const aggregatedData = useMemo(() => {
        const data: Record<string, { forecast: number; stock: number; orders: number }> = {};
        sizes.forEach(size => {
            data[size] = { forecast: 0, stock: 0, orders: 0 };
        });

        colors.forEach(color => {
            sizes.forEach(size => {
                const cell = matrix[color]?.[size];
                if (cell) {
                    data[size].forecast += cell.forecast;
                    data[size].stock += cell.stock;
                    data[size].orders += cell.orders;
                }
            });
        });

        return [
            { metric: "Forecast", ...data },
            { metric: "Stock", ...data },
            { metric: "Customer Orders", ...data },
        ];
    }, [sizes, colors, matrix]);

    const columns = useMemo(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const columnHelper = createColumnHelper<any>();
        const cols = [
            columnHelper.accessor("metric", {
                header: () => <div className="font-bold text-left min-w-[150px]">Metric</div>,
                cell: (info) => (
                    <div className="font-semibold text-slate-600 dark:text-slate-400">
                        {info.getValue()}
                    </div>
                )
            })
        ];

        sizes.forEach(size => {
            cols.push(
                columnHelper.accessor(size, {
                    header: () => <div className="text-center font-bold">{size}</div>,
                    cell: (info) => {
                        const rowData = info.row.original;
                        const sizeData = rowData[size] as { forecast: number; stock: number; orders: number };
                        const isForecastRow = rowData.metric === "Forecast";

                        // Reapply risk tracking logic for aggregated row
                        let styleClass = "";

                        if (isForecastRow) {
                            // Comparing aggregated forecast vs aggregated stock
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                            const aggStock = (aggregatedData[1] as any)[size] as { forecast: number; stock: number; orders: number };
                            const stockVal = aggStock ? aggStock.stock : 0;
                            const forecastVal = sizeData.forecast;

                            if (forecastVal > stockVal * 1.5) {
                                styleClass = "text-rose-600 dark:text-rose-400 font-bold bg-rose-50/50 dark:bg-rose-950/20";
                            } else if (forecastVal > stockVal) {
                                styleClass = "text-yellow-600 dark:text-yellow-500 font-semibold bg-yellow-50/50 dark:bg-yellow-900/10";
                            } else {
                                styleClass = "text-emerald-600 dark:text-emerald-400 font-medium bg-emerald-50/50 dark:bg-emerald-950/10";
                            }
                        }

                        return (
                            <div className={`p-2 rounded text-center tabular-nums transition-colors ${styleClass || "text-slate-700 dark:text-slate-300"}`}>
                                {isForecastRow ? sizeData.forecast : (rowData.metric === "Stock" ? sizeData.stock : sizeData.orders)}
                            </div>
                        );
                    }
                })
            );
        });

        return cols;
    }, [sizes, aggregatedData]);

    const table = useReactTable({
        data: aggregatedData,
        columns,
        getCoreRowModel: getCoreRowModel(),
    });

    return (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <h3 className="font-semibold text-sm text-slate-800 dark:text-slate-200">Aggregated Multi-Row Data View</h3>
            </div>
            <div className="overflow-x-auto">
                <Table>
                    <TableHeader>
                        {table.getHeaderGroups().map((headerGroup) => (
                            <TableRow key={headerGroup.id} className="bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-50 dark:hover:bg-slate-900/50">
                                {headerGroup.headers.map((header) => (
                                    <TableHead key={header.id} className="h-10 text-slate-500 dark:text-slate-400">
                                        {flexRender(
                                            header.column.columnDef.header,
                                            header.getContext()
                                        )}
                                    </TableHead>
                                ))}
                            </TableRow>
                        ))}
                    </TableHeader>
                    <TableBody>
                        {table.getRowModel().rows.map((row) => (
                            <TableRow key={row.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/30">
                                {row.getVisibleCells().map((cell) => (
                                    <TableCell key={cell.id} className="p-2 sm:p-3">
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </TableCell>
                                ))}
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
