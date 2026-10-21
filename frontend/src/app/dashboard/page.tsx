"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowsClockwiseIcon,
  ArrowUpRightIcon,
  ChartBarIcon,
  ClockCounterClockwiseIcon,
  ClockIcon,
  InfoIcon,
  LockSimpleIcon,
  PackageIcon,
  PercentIcon,
  TrendDownIcon,
  TrendUpIcon,
  TruckIcon,
  UserIcon,
  UsersThreeIcon,
  WalletIcon,
  WarningIcon,
  XIcon,
  type Icon,
} from "@phosphor-icons/react";
import AppShell from "@/components/layout/AppShell";
import { BrandButton } from "@/components/ui/brand-button";
import { useSeasonStore } from "@/store/seasonStore";
import { cn } from "@/lib/utils";
import { Alert, DashboardKPI } from "@/types";
import { fetchDashboard, fetchAudit, type AuditEntry } from "@/lib/api/forecast";
import { useDataRefresh } from "@/hooks/useDataRefresh";

interface DashboardEntryCard {
  title: string;
  value: string;
  subtext: string;
  href: string;
  icon: Icon;
  tone: "green" | "purple" | "orange";
}

const KPI_LINKS: Record<string, string> = {
  "Total Forecast Units": "/projection",
  "Undelivered Order Balance": "/customers",
  "Budget Usage": "/budget",
  "Gross Margin": "/budget",
  "Customer Activity": "/customers",
  "Risk Items": "/products",
};

const KPI_ICONS: Record<string, Icon> = {
  "Total Forecast Units": TrendUpIcon,
  "Undelivered Order Balance": TruckIcon,
  "Budget Usage": WalletIcon,
  "Gross Margin": PercentIcon,
  "Customer Activity": UsersThreeIcon,
  "Risk Items": WarningIcon,
};

const ENTRY_TONES: Record<DashboardEntryCard["tone"], string> = {
  green: "bg-success-50 text-success-600",
  purple: "bg-plum-50 text-plum-600",
  orange: "bg-brand-50 text-brand-700",
};

const ALERT_ICONS: Record<Alert["type"], Icon> = {
  margin_miss: TrendDownIcon,
  budget_overrun: WalletIcon,
  coverage_risk: UsersThreeIcon,
  stockout_risk: PackageIcon,
};

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

function activityStyle(action: string): { icon: Icon; className: string; weight: "fill" | "regular" } {
  if (action.includes("lock")) return { icon: LockSimpleIcon, className: "bg-brand-50 text-brand-700", weight: "fill" };
  if (action.includes("override")) return { icon: PackageIcon, className: "bg-plum-50 text-plum-600", weight: "regular" };
  return { icon: UserIcon, className: "bg-soft text-fg-2", weight: "regular" };
}

function TrendChip({ kpi }: { kpi: DashboardKPI }) {
  if (!kpi.trend || kpi.trend === "neutral" || kpi.trendValue === undefined) return null;
  const up = kpi.trend === "up";
  const TrendIcon = up ? TrendUpIcon : TrendDownIcon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-[3px] text-xs font-bold", up ? "bg-success-50 text-success-600" : "bg-danger-soft text-danger")}>
      <TrendIcon weight="bold" className="h-3 w-3" />
      {Math.abs(kpi.trendValue)}%
    </span>
  );
}

export default function DashboardPage() {
  const { activeSeason, alerts, setAlerts, dismissAlert, setFinancialSummary } = useSeasonStore();
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
        link: KPI_LINKS[k.label] || '/dashboard',
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
          icon: UsersThreeIcon,
          tone: "green",
        },
        {
          title: "Product KPIs",
          value: `${dashboard.totalSKUs}`,
          subtext: "active SKUs",
          href: "/products",
          icon: ChartBarIcon,
          tone: "purple",
        },
        {
          title: "Budget Tracker",
          value: dashboard.financialComplete ? `${activeSeason?.currency || "EUR"} ${(fs.totalPurchaseCost / 1000).toFixed(0)}K` : "Inputs required",
          subtext: dashboard.financialComplete ? `of ${activeSeason?.currency || "EUR"} ${(fs.budgetTotal / 1000).toFixed(0)}K` : "Supply costs, prices and inventory",
          href: "/budget",
          icon: WalletIcon,
          tone: "orange",
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

  const [hero, ...restKpis] = kpis;
  const visibleAlerts = alerts.filter((a) => !a.dismissed);

  return (
    <AppShell>
      {!isLoading && !financialComplete && (
        <div role="status" className="flex items-start gap-3 rounded-2xl border border-brand-200 bg-brand-50 px-[18px] py-3.5">
          <InfoIcon weight="fill" className="mt-0.5 h-[18px] w-[18px] shrink-0 text-brand-700" />
          <p className="text-sm leading-relaxed text-fg-1">Quantity forecasts are available. Financial planning requires actual stock and costs; add them in Setup and refresh.</p>
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold uppercase tracking-[0.12em] text-brand">Workspace</span>
          <h1 className="font-display text-[40px] font-extrabold leading-[1.08] tracking-[-0.02em]">Season Dashboard</h1>
          <p className="text-base text-fg-2">
            {activeSeason ? activeSeason.name : "No season selected"} — Command center for your active season
          </p>
        </div>
        <BrandButton variant="outline" onClick={loadData}>
          <ArrowsClockwiseIcon />
          Refresh
        </BrandButton>
      </div>

      {visibleAlerts.map((alert) => {
        const AlertIcon = ALERT_ICONS[alert.type] || WarningIcon;
        return (
          <div key={alert.id} role="alert" className="flex items-center gap-3.5 rounded-[18px] border border-brand-200 bg-card py-3.5 pl-4 pr-3.5">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50">
              <AlertIcon weight="fill" className="h-[19px] w-[19px] text-brand-700" />
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
              <span className="text-[15px] font-bold">{alert.title}</span>
              <span className="text-[13px] leading-[1.45] text-fg-2">{alert.message}</span>
            </span>
            {alert.link && (
              <Link href={alert.link} className="flex h-9 items-center rounded-full border-[1.5px] border-border-strong bg-card px-4 text-[13px] font-bold text-fg-1 hover:border-brand">View</Link>
            )}
            <button type="button" aria-label="Dismiss alert" onClick={() => dismissAlert(alert.id)} className="flex h-9 w-9 items-center justify-center rounded-[10px] text-fg-3 hover:bg-soft hover:text-fg-1">
              <XIcon className="h-4 w-4" />
            </button>
          </div>
        );
      })}

      <div className="flex flex-wrap gap-5">
        {isLoading || !hero ? (
          <div className={cn("min-h-[260px] flex-[2_1_520px] rounded-[32px] bg-champagne", isLoading && "animate-pulse")}>
            {!isLoading && <p className="p-9 text-sm text-fg-2">No forecast figures are available yet. Publish a forecast in Season Setup.</p>}
          </div>
        ) : (
          <Link
            href={hero.link || "/projection"}
            className="relative flex min-h-[260px] flex-[2_1_520px] flex-col justify-between gap-8 overflow-hidden rounded-[32px] bg-champagne p-9 text-fg-1 transition-transform duration-200 ease-[cubic-bezier(.22,1,.36,1)] hover:-translate-y-0.5"
          >
            <span aria-hidden className="absolute -right-20 -top-20 h-80 w-80 rounded-full bg-[radial-gradient(circle,var(--glow),rgba(245,130,32,0)_70%)]" />
            <span className="relative flex w-full items-center justify-between">
              <span className="text-sm font-semibold text-brand-800">{hero.label}</span>
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-card">
                <ArrowUpRightIcon className="h-[17px] w-[17px] text-fg-1" />
              </span>
            </span>
            <span className="relative flex flex-wrap items-baseline gap-3.5">
              <span className="font-display text-[56px] font-bold leading-none tracking-[-0.04em] sm:text-[80px]">{hero.value}</span>
              <span className="text-lg text-fg-2">{hero.subLabel}</span>
            </span>
          </Link>
        )}
        <div className="flex flex-[1_1_300px] flex-col gap-3">
          {(isLoading ? [] : entryCards).map((card) => {
            const CardIcon = card.icon;
            return (
              <Link
                key={card.href}
                href={card.href}
                className="flex flex-1 items-center gap-3.5 rounded-3xl border border-line bg-card p-[18px] text-fg-1 shadow-card transition-all hover:border-brand-200 hover:shadow-lift"
              >
                <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px]", ENTRY_TONES[card.tone])}>
                  <CardIcon weight="fill" className="h-[21px] w-[21px]" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                  <span className="text-[15px] font-bold">{card.title}</span>
                  <span className="text-[13px] leading-[1.45] text-fg-2">
                    <strong className="text-fg-1">{card.value}</strong> {card.subtext}
                  </span>
                </span>
                <ArrowUpRightIcon className="h-4 w-4 text-fg-3" />
              </Link>
            );
          })}
          {isLoading && [0, 1, 2].map((i) => <div key={i} className="min-h-[80px] flex-1 animate-pulse rounded-3xl bg-soft" />)}
        </div>
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {isLoading
          ? Array.from({ length: 5 }).map((_, idx) => <div key={idx} className="h-[138px] animate-pulse rounded-3xl bg-soft" />)
          : restKpis.map((kpi) => {
              const KpiIcon = KPI_ICONS[kpi.label] || ChartBarIcon;
              return (
                <Link
                  key={kpi.label}
                  href={kpi.link || "#"}
                  className="flex flex-col gap-2.5 rounded-3xl border border-line bg-card p-[22px] text-left text-fg-1 shadow-card transition-all hover:-translate-y-px hover:shadow-lift"
                >
                  <span className="flex w-full items-center justify-between">
                    <span className="text-[13px] font-semibold text-fg-2">{kpi.label}</span>
                    <KpiIcon className="h-[18px] w-[18px] text-fg-3" />
                  </span>
                  <span className="flex flex-wrap items-center gap-2.5">
                    <span className="font-display text-[32px] font-bold tracking-[-0.02em]">{kpi.value}</span>
                    <TrendChip kpi={kpi} />
                  </span>
                  <span className="text-[13px] text-fg-3">{kpi.subLabel}</span>
                </Link>
              );
            })}
      </div>

      <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-card">
        <div className="flex items-center justify-between border-b border-line px-[26px] py-[22px]">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-bold">Recent Activity</h2>
            <p className="text-[13px] text-fg-3">Chronological log of decisions made during this session</p>
          </div>
        </div>
        {isLoading ? (
          <div className="flex flex-col">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-4 border-t border-line px-[26px] py-4 first:border-t-0">
                <div className="h-[38px] w-[38px] animate-pulse rounded-full bg-soft" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-3/4 animate-pulse rounded bg-soft" />
                  <div className="h-3 w-1/3 animate-pulse rounded bg-soft" />
                </div>
              </div>
            ))}
          </div>
        ) : auditEntries.length === 0 ? (
          <div className="flex flex-col items-center gap-2.5 px-[26px] py-10 text-center">
            <ClockCounterClockwiseIcon className="h-7 w-7 text-fg-4" />
            <span className="text-sm text-fg-3">No activity yet. Actions like overrides and locks will appear here.</span>
          </div>
        ) : (
          <div className="flex flex-col">
          {auditEntries.map((entry) => {
            const style = activityStyle(entry.action);
            const ActivityIcon = style.icon;
            return (
              <div key={entry.id} className="flex items-center gap-4 border-t border-line px-[26px] py-4 first:border-t-0">
                <span className={cn("flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full", style.className)}>
                  <ActivityIcon weight={style.weight} className="h-[17px] w-[17px]" />
                </span>
                <div className="min-w-0 flex-1 text-sm leading-normal">
                  {entry.entity_id && (
                    <>
                      <Link href={`/recommendations?sku=${entry.entity_id}`} className="font-mono text-[13px] font-bold text-brand-700 hover:underline">
                        {entry.entity_name || entry.entity_id}
                      </Link>
                      <span className="text-fg-3"> — </span>
                    </>
                  )}
                  <span>{entry.action}</span>
                  {entry.details && <span className="text-fg-3"> ({entry.details})</span>}
                  <div className="mt-0.5 text-xs text-fg-3">by {entry.user}</div>
                </div>
                <span className="flex items-center gap-[5px] whitespace-nowrap text-[13px] text-fg-3">
                  <ClockIcon className="h-[13px] w-[13px]" />
                  {formatTimeAgo(entry.timestamp)}
                </span>
              </div>
            );
          })}
          </div>
        )}
      </section>
    </AppShell>
  );
}
