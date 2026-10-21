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
    className: "border-transparent bg-success-50 text-success-600",
  },
  medium: {
    label: "Medium",
    className: "border-transparent bg-brand-50 text-brand-800",
  },
  low: {
    label: "Low",
    className: "border-transparent bg-danger-soft text-danger",
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
        "rounded-full font-bold",
        config.className,
        size === "sm" ? "text-[10px] px-2 py-0" : "text-xs px-2.5 py-[3px]"
      )}
    >
      {showLabel ? config.label : (level ?? "m").charAt(0).toUpperCase()}
    </Badge>
  );
}
