"use client";

import React from "react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface DemandSplitBarProps {
  confirmed: number;
  probableReorders: number;
  nonVisitedProjection: number;
  total?: number;
  showLabels?: boolean;
  showTooltips?: boolean;
  height?: "sm" | "md" | "lg";
  className?: string;
}

export default function DemandSplitBar({
  confirmed,
  probableReorders,
  nonVisitedProjection,
  total: providedTotal,
  showLabels = false,
  showTooltips = true,
  height = "md",
  className,
}: DemandSplitBarProps) {
  const total = providedTotal || confirmed + probableReorders + nonVisitedProjection;

  const confirmedPercent = total > 0 ? (confirmed / total) * 100 : 0;
  const reordersPercent = total > 0 ? (probableReorders / total) * 100 : 0;
  const projectedPercent = total > 0 ? (nonVisitedProjection / total) * 100 : 0;

  const heightClasses = {
    sm: "h-2",
    md: "h-3",
    lg: "h-4",
  };

  const segments = [
    {
      label: "Recorded orders included",
      value: confirmed,
      percent: confirmedPercent,
      color: "bg-emerald-500 dark:bg-emerald-600",
    },
    {
      label: "Projected quantity",
      value: probableReorders,
      percent: reordersPercent,
      color: "bg-blue-500 dark:bg-blue-600",
    },
    {
      label: "Other projection",
      value: nonVisitedProjection,
      percent: projectedPercent,
      color: "bg-slate-400 dark:bg-slate-500",
    },
  ];

  const Bar = (
    <div
      className={cn(
        "flex w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800",
        heightClasses[height],
        className
      )}
    >
      {segments.map((segment, idx) => (
        <div
          key={segment.label}
          className={cn(
            segment.color,
            "transition-all duration-300",
            idx === 0 && "rounded-l-full",
            idx === segments.length - 1 && "rounded-r-full"
          )}
          style={{ width: `${segment.percent}%` }}
        />
      ))}
    </div>
  );

  return (
    <div className="space-y-2">
      {showTooltips ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>{Bar}</TooltipTrigger>
            <TooltipContent className="p-3">
              <div className="space-y-1.5 text-xs">
                {segments.map((segment) => (
                  <div key={segment.label} className="flex items-center gap-2">
                    <div className={cn("h-2.5 w-2.5 rounded-sm", segment.color)} />
                    <span className="text-slate-600 dark:text-slate-400">
                      {segment.label}:
                    </span>
                    <span className="font-semibold">
                      {segment.value.toLocaleString()} ({segment.percent.toFixed(1)}%)
                    </span>
                  </div>
                ))}
                <div className="border-t border-slate-200 dark:border-slate-700 pt-1.5 mt-1.5">
                  <span className="font-semibold">Total: {total.toLocaleString()}</span>
                </div>
              </div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ) : (
        Bar
      )}

      {showLabels && (
        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
          {segments.map((segment) => (
            <div key={segment.label} className="flex items-center gap-1.5">
              <div className={cn("h-2 w-2 rounded-sm", segment.color)} />
              <span>
                {segment.label}: {segment.value.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
