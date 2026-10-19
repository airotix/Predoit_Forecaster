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

interface ForecastMatrixProps {
    sizes: string[];
    colors: string[];
    matrix: Record<string, Record<string, ForecastMatrixValue>>;
}

export default function ForecastMatrix({ sizes, colors, matrix }: ForecastMatrixProps) {
    // Determine cell color based on risk rule
    const getCellColorClass = (cell: ForecastMatrixValue | undefined) => {
        if (!cell) return "bg-slate-50 dark:bg-slate-900 text-slate-300";

        // Risk Highlighting Rules
        // Green = safe
        // Yellow = low stock
        // Red = forecast risk
        if (cell.forecast > cell.stock * 1.5) {
            return "bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 font-semibold"; // Critical
        }
        if (cell.forecast > cell.stock) {
            return "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-500 font-medium"; // Warning
        }
        return "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400"; // Safe (Green)
    };

    const tableData = useMemo(() => {
        return colors.map((color) => ({
            color,
            ...matrix[color],
        }));
    }, [colors, matrix]);

    const columns = useMemo(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
const columnHelper = createColumnHelper<any>();
        const cols = [
            columnHelper.accessor("color", {
                header: () => <div className="font-bold text-left min-w-[100px]">Color \ Size</div>,
                cell: (info) => (
                    <div className="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-2">
                        <div
                            className="w-3 h-3 rounded-full border border-slate-300 shadow-sm"
                            style={{ backgroundColor: info.getValue().toLowerCase() }}
                        />
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
                        const val = info.getValue() as ForecastMatrixValue;
                        const styleClass = getCellColorClass(val);
                        return (
                            <div className={`p-2 rounded-md text-center tabular-nums transition-colors ${styleClass}`}>
                                {val ? val.forecast : "-"}
                            </div>
                        );
                    }
                })
            );
        });

        return cols;
    }, [sizes]);

    const table = useReactTable({
        data: tableData,
        columns,
        getCoreRowModel: getCoreRowModel(),
    });

    return (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                <h3 className="font-semibold text-sm text-slate-800 dark:text-slate-200">Forecast Matrix (Quantities)</h3>
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
            <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 flex gap-4 text-xs">
                <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded bg-emerald-100 dark:bg-emerald-950/50" />Safe (Stock ≥ Forecast)</div>
                <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded bg-yellow-100 dark:bg-yellow-900/50" />Warning (Stock &lt; Forecast)</div>
                <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded bg-rose-100 dark:bg-rose-950/50" />Critical (Stock ≪ Forecast)</div>
            </div>
        </div>
    );
}
