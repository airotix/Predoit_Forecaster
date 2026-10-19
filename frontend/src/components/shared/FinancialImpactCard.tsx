"use client";

import React from "react";
import { FinancialImpact } from "@/types";
import { cn } from "@/lib/utils";
import { useSeasonStore } from "@/store/seasonStore";

interface FinancialImpactCardProps {
  impact: FinancialImpact;
  unitPrice: number;
  unitCost: number;
  totalQty: number;
  className?: string;
}

export default function FinancialImpactCard({
  impact,
  unitPrice,
  unitCost,
  totalQty,
  className,
}: FinancialImpactCardProps) {
  const { activeSeason } = useSeasonStore();
  const targetMargin = activeSeason?.targetMargin || 50;
  const isMarginGood = impact.marginPercent >= targetMargin;

  const formatCurrency = (value: number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: activeSeason?.currency || "EUR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);

  if(impact.complete===false)return <p className="rounded border p-4 text-sm text-amber-700">Financial impact needs actual inventory, selling prices and purchase costs.</p>;
  return (
    <div
      className={cn(
        "rounded-lg border p-4 space-y-3",
        isMarginGood
          ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-800 dark:bg-emerald-950/30"
          : "border-rose-200 bg-rose-50/50 dark:border-rose-800 dark:bg-rose-950/30",
        className
      )}
    >
      <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
        Financial Impact
      </h4>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-slate-500 dark:text-slate-400">Purchase cost:</p>
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            {formatCurrency(impact.purchaseCost)}
            <span className="text-xs font-normal text-slate-500 ml-1">
              ({totalQty} × {formatCurrency(unitCost)})
            </span>
          </p>
        </div>

        <div>
          <p className="text-slate-500 dark:text-slate-400">Expected turnover:</p>
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            {formatCurrency(impact.expectedTurnover)}
            <span className="text-xs font-normal text-slate-500 ml-1">
              ({totalQty} × {formatCurrency(unitPrice)})
            </span>
          </p>
        </div>

        <div>
          <p className="text-slate-500 dark:text-slate-400">Gross margin:</p>
          <p
            className={cn(
              "font-semibold",
              isMarginGood
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-rose-600 dark:text-rose-400"
            )}
          >
            {formatCurrency(impact.grossMargin)} ({impact.marginPercent.toFixed(1)}%)
          </p>
        </div>

        <div>
          <p className="text-slate-500 dark:text-slate-400">Budget impact:</p>
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            +{impact.budgetImpactPercent.toFixed(2)}%
            <span className="text-xs font-normal text-slate-500 ml-1">
              of season budget
            </span>
          </p>
        </div>
      </div>

      {!isMarginGood && (
        <div className="flex items-center gap-2 text-xs text-rose-600 dark:text-rose-400 pt-2 border-t border-rose-200 dark:border-rose-800">
          <span>⚠</span>
          <span>
            Margin ({impact.marginPercent.toFixed(1)}%) is below target ({targetMargin}%)
          </span>
        </div>
      )}
    </div>
  );
}
