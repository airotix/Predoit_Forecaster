"use client";

import React, { useMemo } from "react";
import {
    useReactTable,
    getCoreRowModel,
    flexRender,
    createColumnHelper,
} from "@tanstack/react-table";
import { ArticleData } from "@/types";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface DetailedStockMatrixProps {
    article: ArticleData;
}

export default function DetailedStockMatrix({ article }: DetailedStockMatrixProps) {
    const { sizes, colors, matrix } = article;

    // Transform data into flat grouped rows for TanStack Table
    // For each color we need 4 rows: Produit, Fournisseur, CltNegoce, LeStock
    const tableData = useMemo(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const data: any[] = [];

        // Global Totals Trackers
        const globalTotals = {
            product: Array(sizes.length).fill(0),
            fournisseur: Array(sizes.length).fill(0),
            cltNegoce: Array(sizes.length).fill(0),
            leStock: Array(sizes.length).fill(0),
            totalProduct: 0,
            totalFournisseur: 0,
            totalCltNegoce: 0,
            totalLeStock: 0,
        };

        colors.forEach((color) => {
            // Initialize row objects
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const rowProduit: any = { color, metricType: "Total de Produit", isFirst: true, isLast: false, rowTotal: 0 };
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const rowFournisseur: any = { color, metricType: "Total de Fournisseur", isFirst: false, isLast: false, rowTotal: 0 };
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const rowCltNegoce: any = { color, metricType: "Total de CltNegoce", isFirst: false, isLast: false, rowTotal: 0 };
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const rowLeStock: any = { color, metricType: "Total de LeStock", isFirst: false, isLast: true, rowTotal: 0 };

            let colorProductTotal = 0;
            let colorFournisseurTotal = 0;
            let colorCltNegoceTotal = 0;
            let colorLeStockTotal = 0;

            sizes.forEach((size, sizeIndex) => {
                const cell = matrix[color]?.[size];
                // Using "forecast" as "Produit"
                // Using "stock" as "Fournisseur" 
                // Using "orders" as "CltNegoce"
                // "LeStock" represents the calculated variance or stock pool

                // Simulating the reference image metrics
                const produit = cell ? cell.forecast : 0;
                const fournisseur = cell ? cell.stock : 0;
                const cltNegoce = cell ? cell.orders : 0;

                // Exact calculation format to mimic LeStock logic: Produit + Fournisseur - CltNegoce
                const leStock = produit + fournisseur - cltNegoce;

                rowProduit[size] = produit;
                rowFournisseur[size] = fournisseur;
                rowCltNegoce[size] = cltNegoce;
                rowLeStock[size] = leStock;

                colorProductTotal += produit;
                colorFournisseurTotal += fournisseur;
                colorCltNegoceTotal += cltNegoce;
                colorLeStockTotal += leStock;

                // Global columns
                globalTotals.product[sizeIndex] += produit;
                globalTotals.fournisseur[sizeIndex] += fournisseur;
                globalTotals.cltNegoce[sizeIndex] += cltNegoce;
                globalTotals.leStock[sizeIndex] += leStock;
            });

            rowProduit.rowTotal = colorProductTotal;
            rowFournisseur.rowTotal = colorFournisseurTotal;
            rowCltNegoce.rowTotal = colorCltNegoceTotal;
            rowLeStock.rowTotal = colorLeStockTotal;

            globalTotals.totalProduct += colorProductTotal;
            globalTotals.totalFournisseur += colorFournisseurTotal;
            globalTotals.totalCltNegoce += colorCltNegoceTotal;
            globalTotals.totalLeStock += colorLeStockTotal;

            data.push(rowProduit, rowFournisseur, rowCltNegoce, rowLeStock);
        });

        return data;
    }, [colors, sizes, matrix]);

    const columns = useMemo(() => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const columnHelper = createColumnHelper<any>();
        const cols = [
            columnHelper.accessor("color", {
                header: () => <div className="font-semibold text-slate-700 dark:text-slate-300">Color</div>,
                cell: (info) => {
                    const rowData = info.row.original;
                    if (rowData.isFirst) {
                        return (
                            <div className="font-semibold text-slate-800 dark:text-slate-200">
                                {info.getValue()}
                            </div>
                        );
                    }
                    return null; // Don't repeat the color name on the sub-rows
                }
            }),
            columnHelper.accessor("metricType", {
                header: () => (
                    <div
                        className="font-semibold text-slate-700 dark:text-slate-300"
                        title="Produit = Forecast · Fournisseur = Stock · CltNegoce = Orders · LeStock = Projected stock (Forecast + Stock − Orders)"
                    >
                        Data
                    </div>
                ),
                cell: (info) => {
                    const val = info.getValue() as string;
                    // Apply exact text coloring as reference image
                    let colorClass = "text-slate-600 dark:text-slate-400";
                    if (val === "Total de Fournisseur") colorClass = "text-[#66c166] font-medium"; // Reference image Green
                    if (val === "Total de CltNegoce") colorClass = "text-[#e85bff] font-medium"; // Reference image Bright Pink
                    if (val === "Total de LeStock") colorClass = "text-[#ff2e2e] font-medium"; // Reference image Red

                    return <div className={colorClass}>{val}</div>;
                }
            })
        ];

        sizes.forEach(size => {
            cols.push(
                columnHelper.accessor(size, {
                    header: () => <div className="text-center font-semibold">{size}</div>,
                    cell: (info) => {
                        const val = info.getValue() as number;
                        const rowData = info.row.original;

                        // Apply exact text coloring to the cells too
                        let colorClass = "text-slate-800 dark:text-slate-200";
                        if (rowData.metricType === "Total de Fournisseur") colorClass = "text-[#66c166] font-medium";
                        if (rowData.metricType === "Total de CltNegoce") colorClass = "text-[#e85bff] font-medium";
                        if (rowData.metricType === "Total de LeStock") colorClass = "text-[#ff2e2e] font-bold";

                        return <div className={`text-center py-1 ${colorClass}`}>{val}</div>;
                    }
                })
            );
        });

        cols.push(
            columnHelper.accessor("rowTotal", {
                header: () => <div className="text-center font-bold">Total</div>,
                cell: (info) => {
                    const val = info.getValue() as number;
                    const rowData = info.row.original;
                    let colorClass = "text-slate-900 font-bold dark:text-slate-50";
                    if (rowData.metricType === "Total de Fournisseur") colorClass = "text-[#66c166] font-semibold";
                    if (rowData.metricType === "Total de CltNegoce") colorClass = "text-[#e85bff] font-semibold";
                    if (rowData.metricType === "Total de LeStock") colorClass = "text-[#ff2e2e] font-bold";

                    return <div className={`text-center py-1 ${colorClass}`}>{val}</div>;
                }
            })
        );

        return cols;
    }, [sizes]);

    const table = useReactTable({
        data: tableData,
        columns,
        getCoreRowModel: getCoreRowModel(),
    });

    const legendItems = [
        { label: "Forecast (Produit)", short: "F", colorClass: "text-slate-700 dark:text-slate-300" },
        { label: "Stock (Fournisseur)", short: "S", colorClass: "text-[#66c166]" },
        { label: "Orders (CltNegoce)", short: "O", colorClass: "text-[#e85bff]" },
        { label: "Projected stock (LeStock = F + S − O)", short: "P", colorClass: "text-[#ff2e2e]" },
    ];

    return (
        <div className="mt-4 space-y-2">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400" role="group" aria-label="Table legend">
                {legendItems.map((item) => (
                    <span key={item.short} className={`flex items-center gap-1.5 ${item.colorClass}`}>
                        <span className="font-semibold" aria-hidden="true">{item.short}</span>
                        <span>{item.label}</span>
                    </span>
                ))}
            </div>
            <div className="bg-white dark:bg-slate-950 overflow-x-auto text-[13px] border-t-2 border-slate-800 dark:border-slate-300">
            <Table className="border-collapse table-fixed w-full min-w-[800px]">
                <TableHeader>
                    {table.getHeaderGroups().map((headerGroup) => (
                        <TableRow key={headerGroup.id} className="border-b-2 border-slate-800 dark:border-slate-300 hover:bg-transparent">
                            {headerGroup.headers.map((header, i) => (
                                <TableHead
                                    key={header.id}
                                    className={`h-9 border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 p-2 
                    ${i === 0 ? 'w-[120px]' : ''} 
                    ${i === 1 ? 'w-[160px]' : ''}
                    ${i > 1 ? 'w-[60px]' : ''}
                  `}
                                >
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
                    {table.getRowModel().rows.map((row) => {
                        const rowData = row.original;
                        return (
                            <TableRow
                                key={row.id}
                                className={`hover:bg-slate-50/50 dark:hover:bg-slate-900/50 
                  ${rowData.isLast ? 'border-b-2 border-slate-800 dark:border-slate-300' : 'border-none'}
                `}
                            >
                                {row.getVisibleCells().map((cell, i) => (
                                    <TableCell
                                        key={cell.id}
                                        className={`p-1 px-2 border-r border-slate-300 dark:border-slate-700 
                      ${i === 0 && !rowData.isFirst ? 'border-b-0 border-t-0' : 'border-b border-t'} 
                      ${i === 0 ? 'border-l border-slate-300 dark:border-slate-700 align-top pt-2' : ''}
                    `}
                                    >
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </TableCell>
                                ))}
                            </TableRow>
                        );
                    })}
                </TableBody>
            </Table>
            </div>
        </div>
    );
}
