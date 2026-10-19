"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { AlertBanner } from "@/components/shared";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useSeasonStore } from "@/store/seasonStore";
import { cn } from "@/lib/utils";
import {
  Users,
  Package,
  Wallet,
  TrendingUp,
  BarChart3,
  RefreshCw,
  ArrowRight,
  Clock,
  User,
  Lock,
} from "lucide-react";
import { DashboardKPI } from "@/types";
import { fetchDashboard, fetchAudit, type AuditEntry } from "@/lib/api/forecast";
import { useDataRefresh } from "@/hooks/useDataRefresh";

interface DashboardEntryCard {
  title: string;
  value: string;
  subtext: string;
  href: string;
  icon: React.ElementType;
  color: string;
}

function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

export default function DashboardPage() {
  const { activeSeason, setAlerts, setFinancialSummary } = useSeasonStore();
  const [financialComplete,setFinancialComplete]=useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [kpis, setKpis] = useState<DashboardKPI[]>([]);
  const [entryCards, setEntryCards] = useState<DashboardEntryCard[]>([]);
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [dashboard, audit] = await Promise.all([
        fetchDashboard(),
        fetchAudit(10),
      ]);

      setFinancialComplete(dashboard.financialComplete);
      const mappedKpis: DashboardKPI[] = dashboard.kpis.filter(k=>dashboard.financialComplete||!["Budget Usage","Gross Margin"].includes(k.label)).map((k) => ({
        label: k.label,
        value: k.value,
        subLabel: k.subLabel,
        trend: k.trend,
        trendValue: k.trendValue,
        link: ({'Total Forecast Units':'/projection','Undelivered Order Balance':'/customers','Budget Usage':'/budget','Gross Margin':'/budget','Customer Activity':'/customers','Risk Items':'/products'} as Record<string,string>)[k.label] || '/dashboard',
      }));
      setKpis(mappedKpis);

      const fs = dashboard.financialSummary;
      setFinancialSummary(dashboard.financialComplete ? {
        budgetUsed: fs.budgetTotal > 0 ? Math.round(fs.budgetUsed / fs.budgetTotal * 100) : 0,
        budgetTotal: fs.budgetTotal,
        margin: fs.margin,
        targetMargin: fs.targetMargin,
        coverage: fs.coverage,
        totalPurchaseCost: fs.totalPurchaseCost,
        expectedTurnover: fs.expectedTurnover,
      } : null);

      setEntryCards([
        {
          title: "Customer Activity",
          value: `${fs.coverage}%`,
          subtext: "ordered in latest 6 data months",
          href: "/customers",
          icon: Users,
          color: "text-blue-500",
        },
        {
          title: "Product KPIs",
          value: `${dashboard.totalSKUs}`,
          subtext: "active SKUs",
          href: "/products",
          icon: BarChart3,
          color: "text-emerald-500",
        },
        {
          title: "Budget Tracker",
          value: dashboard.financialComplete ? `${activeSeason?.currency || "EUR"} ${(fs.totalPurchaseCost / 1000).toFixed(0)}K` : "Inputs required",
          subtext: dashboard.financialComplete ? `of ${activeSeason?.currency || "EUR"} ${(fs.budgetTotal / 1000).toFixed(0)}K` : "Supply costs, prices and inventory",
          href: "/budget",
          icon: Wallet,
          color: "text-amber-500",
        },
      ]);

      setAlerts([]);
      if (dashboard.financialComplete && fs.margin < fs.targetMargin) {
        setAlerts([{
          id: "margin-alert",
          type: "margin_miss",
          title: "Margin Below Target",
          message: `Current margin ${fs.margin}% is below target ${fs.targetMargin}%`,
          severity: "warning",
          link: "/budget",
          dismissed: false,
        }]);
      }

      setAuditEntries(audit);
    } catch (err) {
      console.error("Failed to load dashboard:", err);
    } finally {
      setIsLoading(false);
    }
  }, [setAlerts, setFinancialSummary, activeSeason?.currency]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useDataRefresh(loadData);

  return (
    <AppShell>
      <div className="space-y-6">
        {!financialComplete&&<p role="status" className="rounded border p-4 text-amber-700">Quantity forecasts are available. Financial planning requires actual stock and costs; add them in Setup and refresh.</p>}
        {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Season Dashboard</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              {activeSeason ? activeSeason.name : "No season selected"} — Command center for your active season
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>

        {/* Alert Strip */}
        <AlertBanner />

        {/* KPI Cards */}
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, idx) => (
                <Card key={idx}><CardContent className="p-6"><div className="h-16 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" /></CardContent></Card>
              ))
            : kpis.map((kpi, idx) => (
                <Link key={idx} href={kpi.link || "#"}>
                  <Card className="hover:border-blue-300 transition-colors cursor-pointer h-full">
                    <CardHeader className="pb-2">
                      <CardDescription className="text-xs">{kpi.label}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{kpi.value}</div>
                      <p className="text-xs text-slate-500 mt-1">{kpi.subLabel}</p>
                      {kpi.trend && kpi.trend !== "neutral" && kpi.trendValue !== undefined && (
                        <div
                          className={cn(
                            "flex items-center gap-1 text-xs mt-2",
                            kpi.trend === "up" ? "text-emerald-600" : "text-rose-600"
                          )}
                        >
                          <TrendingUp
                            className={cn("h-3 w-3", kpi.trend === "down" && "rotate-180")}
                          />
                          <span>{Math.abs(kpi.trendValue)}%</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </Link>
              ))}
        </div>

        {/* Entry Point Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          {entryCards.map((card) => {
            const Icon = card.icon;
            return (
              <Link key={card.href} href={card.href}>
                <Card className="hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group">
                  <CardContent className="flex items-center justify-between p-6">
                    <div className="flex items-center gap-4">
                      <div
                        className={cn(
                          "flex h-12 w-12 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-900",
                          card.color
                        )}
                      >
                        <Icon className="h-6 w-6" />
                      </div>
                      <div>
                        <h3 className="font-semibold">{card.title}</h3>
                        <p className="text-sm text-slate-500">
                          <span className="font-bold text-slate-900 dark:text-slate-100">
                            {card.value}
                          </span>{" "}
                          {card.subtext}
                        </p>
                      </div>
                    </div>
                    <ArrowRight className="h-5 w-5 text-slate-400 group-hover:text-blue-500 transition-colors" />
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>

        {/* Recent Activity Feed */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Recent Activity</CardTitle>
            <CardDescription>
              Chronological log of decisions made during this session
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-4">
                    <div className="h-8 w-8 rounded-full bg-slate-100 dark:bg-slate-800 animate-pulse" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-3/4 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
                      <div className="h-3 w-1/2 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
                    </div>
                  </div>
                ))}
              </div>
            ) : auditEntries.length === 0 ? (
              <p className="text-sm text-slate-500 py-4 text-center">No activity yet. Actions like overrides and locks will appear here.</p>
            ) : (
              <div className="space-y-4">
                {auditEntries.map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-start gap-4 pb-4 border-b border-slate-100 dark:border-slate-800 last:border-0 last:pb-0"
                  >
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-900 shrink-0">
                      {entry.action.includes("lock") ? (
                        <Lock className="h-4 w-4 text-amber-500" />
                      ) : entry.action.includes("override") ? (
                        <Package className="h-4 w-4 text-blue-500" />
                      ) : (
                        <User className="h-4 w-4 text-slate-500" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm">
                        {entry.entity_id && (
                          <Link
                            href={`/recommendations?sku=${entry.entity_id}`}
                            className="font-medium text-blue-600 hover:underline"
                          >
                            {entry.entity_name || entry.entity_id}
                          </Link>
                        )}
                        {entry.entity_id && " — "}
                        <span className="text-slate-700 dark:text-slate-300">
                          {entry.action}
                        </span>
                        {entry.details && (
                          <span className="text-slate-500"> ({entry.details})</span>
                        )}
                      </p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                        <span>by {entry.user}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatTimeAgo(entry.timestamp)}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
