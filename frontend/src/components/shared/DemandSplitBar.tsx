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
      color: "bg-success-400",
    },
    {
      label: "Projected quantity",
      value: probableReorders,
      percent: reordersPercent,
      color: "bg-brand",
    },
    {
      label: "Other projection",
      value: nonVisitedProjection,
      percent: projectedPercent,
      color: "bg-fg-4",
    },
  ];

  const Bar = (
    <div
      className={cn(
        "flex w-full overflow-hidden rounded-full bg-soft",
        heightClasses[height],
        className
      )}
    >
      {segments.map((segment) => (
        <div
          key={segment.label}
          className={cn(segment.color, "transition-all duration-300")}
          style={{ width: `${segment.percent}%` }}
        />
      ))}
    </div>
  );

  return (
    <div className="flex flex-col gap-2.5">
      {showTooltips ? (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>{Bar}</TooltipTrigger>
            <TooltipContent className="p-3">
              <div className="space-y-1.5 text-xs">
                {segments.map((segment) => (
                  <div key={segment.label} className="flex items-center gap-2">
                    <div className={cn("h-2.5 w-2.5 rounded-sm", segment.color)} />
                    <span className="text-fg-2">
                      {segment.label}:
                    </span>
                    <span className="font-semibold">
                      {segment.value.toLocaleString()} ({segment.percent.toFixed(1)}%)
                    </span>
                  </div>
                ))}
                <div className="mt-1.5 border-t border-line pt-1.5">
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
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-fg-2">
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
