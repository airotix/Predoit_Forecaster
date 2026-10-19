"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { Lock, Unlock } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface LockToggleProps {
  locked: boolean;
  onToggle: () => void;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  className?: string;
}

export default function LockToggle({
  locked,
  onToggle,
  disabled = false,
  size = "md",
  showLabel = false,
  className,
}: LockToggleProps) {
  const sizeClasses = {
    sm: "h-7 w-7",
    md: "h-9 w-9",
    lg: "h-11 w-11",
  };

  const iconSizes = {
    sm: "h-3.5 w-3.5",
    md: "h-4 w-4",
    lg: "h-5 w-5",
  };

  const button = (
    <Button
      variant={locked ? "default" : "outline"}
      size="icon"
      onClick={onToggle}
      disabled={disabled}
      className={cn(
        sizeClasses[size],
        locked
          ? "bg-amber-500 hover:bg-amber-600 text-white"
          : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100",
        showLabel && "w-auto px-3 gap-2",
        className
      )}
      aria-label={locked ? "Unlock SKU" : "Lock SKU"}
    >
      {locked ? (
        <Lock className={iconSizes[size]} />
      ) : (
        <Unlock className={iconSizes[size]} />
      )}
      {showLabel && <span className="text-sm font-medium">{locked ? "Locked" : "Lock"}</span>}
    </Button>
  );

  if (showLabel) {
    return button;
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{button}</TooltipTrigger>
        <TooltipContent>
          <p>{locked ? "Unlock SKU for editing" : "Lock SKU to freeze from AI recalculation"}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
