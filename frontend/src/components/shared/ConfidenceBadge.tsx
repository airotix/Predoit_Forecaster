"use client";

import React from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ConfidenceLevel } from "@/types";

interface ConfidenceBadgeProps {
  level: ConfidenceLevel;
  size?: "sm" | "md";
  showLabel?: boolean;
}

const confidenceConfig: Record<
  ConfidenceLevel,
  { label: string; className: string }
> = {
  high: {
    label: "High",
    className:
      "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800",
  },
  medium: {
    label: "Medium",
    className:
      "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  },
  low: {
    label: "Low",
    className:
      "bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-800",
  },
};

export default function ConfidenceBadge({
  level,
  size = "md",
  showLabel = true,
}: ConfidenceBadgeProps) {
  const config = confidenceConfig[level] ?? confidenceConfig.medium;

  return (
    <Badge
      variant="outline"
      className={cn(
        config.className,
        size === "sm" ? "text-[10px] px-1.5 py-0" : "text-xs px-2 py-0.5"
      )}
    >
      {showLabel ? config.label : (level ?? "m").charAt(0).toUpperCase()}
    </Badge>
  );
}
