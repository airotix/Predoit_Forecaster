"use client";

import React from "react";
import Link from "next/link";
import { Alert } from "@/types";
import { useSeasonStore } from "@/store/seasonStore";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  DollarSign,
  TrendingDown,
  Users,
  Package,
  X,
} from "lucide-react";

interface AlertBannerProps {
  className?: string;
}

const alertIcons: Record<Alert["type"], React.ElementType> = {
  budget_overrun: DollarSign,
  margin_miss: TrendingDown,
  coverage_risk: Users,
  stockout_risk: Package,
};

const alertColors: Record<Alert["severity"], string> = {
  warning:
    "bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-950/50 dark:border-amber-800 dark:text-amber-200",
  danger:
    "bg-rose-50 border-rose-200 text-rose-800 dark:bg-rose-950/50 dark:border-rose-800 dark:text-rose-200",
};

export default function AlertBanner({ className }: AlertBannerProps) {
  const { alerts, dismissAlert } = useSeasonStore();
  const visibleAlerts = alerts.filter((a) => !a.dismissed);

  if (visibleAlerts.length === 0) {
    return null;
  }

  return (
    <div className={cn("space-y-2", className)}>
      {visibleAlerts.map((alert) => {
        const Icon = alertIcons[alert.type] || AlertTriangle;
        return (
          <div
            key={alert.id}
            className={cn(
              "flex items-center justify-between gap-4 rounded-lg border px-4 py-3",
              alertColors[alert.severity]
            )}
          >
            <div className="flex items-center gap-3">
              <Icon className="h-5 w-5 shrink-0" />
              <div>
                <p className="font-medium text-sm">{alert.title}</p>
                <p className="text-sm opacity-80">{alert.message}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {alert.link && (
                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="border-current/20 hover:bg-current/10"
                >
                  <Link href={alert.link}>View</Link>
                </Button>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 hover:bg-current/10"
                onClick={() => dismissAlert(alert.id)}
                aria-label="Dismiss alert"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
