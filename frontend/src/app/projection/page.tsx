"use client";
import ActivityBadge from '@/components/shared/ArticleActivity';

import React, { useEffect, useState, useCallback, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { ScenarioSwitcher, DemandSplitBar, ConfidenceBadge } from "@/components/shared";
import { BrandButton } from "@/components/ui/brand-button";
import { Notice, PageHeader, TextField } from "@/components/ui/brand";
import { useSeasonStore } from "@/store/seasonStore";
import { cn } from "@/lib/utils";
import {
  CaretDownIcon,
  CaretRightIcon,
  ChartPieSliceIcon,
  MagnifyingGlassIcon,
  QuestionIcon,
} from "@phosphor-icons/react";
import { ConfidenceLevel } from "@/types";
import { SKUDetailedProjection } from "@/types/stockMatrix";
import { SKUStockMatrix } from "@/components/forecast/SKUStockMatrix";
import { fetchProjections, fetchProjectionDetail, type ProjectionRow } from "@/lib/api/forecast";
import { useDataRefresh } from "@/hooks/useDataRefresh";

const ROW_GRID = "grid grid-cols-[minmax(220px,1fr)_120px_140px_110px_110px_110px_56px] gap-4";
const CONFIDENCE_DOT: Record<ConfidenceLevel, string> = { high: "bg-success-400", medium: "bg-brand", low: "bg-danger" };

export default function ProjectionPage() {
  const { activeScenario, activeSeason } = useSeasonStore();
  const [projections, setProjections] = useState<ProjectionRow[]>([]);
  const [detailedCache, setDetailedCache] = useState<Map<string, SKUDetailedProjection>>(new Map());
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [error,setError]=useState('');
  const [detailErrors,setDetailErrors]=useState<Record<string,string>>({});
  const request=useRef({version:0});

  const loadProjections = useCallback(async () => {
    const version=++request.current.version;
    setIsLoading(true);
    setError('');setDetailedCache(new Map());setExpandedRows(new Set());setDetailErrors({});
    try {
      const data = await fetchProjections();
      if(version!==request.current.version)return;
      setProjections(data);
      setDetailedCache(new Map());
    } catch (err) {
      if(version===request.current.version){setProjections([]);setError(err instanceof Error?err.message:'Could not load projections.');}
    } finally {
      if(version===request.current.version)setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjections();
    const token=request.current;
    return ()=>{token.version++;};
  }, [loadProjections,activeSeason?.id,activeScenario]);

  useDataRefresh(loadProjections);

  const toggleRow = async (skuId: string) => {
    const version=request.current.version;
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(skuId)) {
        next.delete(skuId);
      } else {
        next.add(skuId);
      }
      return next;
    });

    const reference = skuId.replace("SKU-", "");
    if (!detailedCache.has(skuId)) {
      try {
        const detail = await fetchProjectionDetail(reference,activeScenario);
        if(version!==request.current.version)return;
        setDetailedCache((prev) => {
          const next = new Map(prev);
          next.set(skuId, detail as SKUDetailedProjection);
          return next;
        });
      } catch (err) {
        if(version===request.current.version)setDetailErrors(prev=>({...prev,[skuId]:err instanceof Error?err.message:'Could not load article detail.'}));
      }
    }
  };

  const filteredProjections = projections.filter(
    (p) =>
      p.skuId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.skuName.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalDemand = projections.reduce(
    (acc, p) => {
      const scenario = p.scenarios[activeScenario];
      return {
        confirmed: acc.confirmed + scenario.confirmed,
        reorders: acc.reorders + scenario.probableReorders,
        nonVisited: acc.nonVisited + scenario.nonVisitedProjection,
        total: acc.total + scenario.total,
      };
    },
    { confirmed: 0, reorders: 0, nonVisited: 0, total: 0 }
  );

  const confidenceDistribution = projections.reduce(
    (acc, p) => {
      const level = p.confidence as ConfidenceLevel;
      if (acc[level] !== undefined) acc[level]++;
      return acc;
    },
    { high: 0, medium: 0, low: 0 } as Record<ConfidenceLevel, number>
  );

  const share = (value: number) =>
    totalDemand.total > 0 && (
      <span className="ml-1 font-sans text-sm font-medium text-fg-3">
        ({Math.round((value / totalDemand.total) * 100)}%)
      </span>
    );

  return (
    <AppShell>
      <PageHeader
        eyebrow="Forecasting"
        title="Demand Projection"
        description="AI-powered demand forecasting across scenarios"
        actions={<ScenarioSwitcher />}
      />

      {error&&<Notice tone="danger"><span className="flex flex-wrap items-center justify-between gap-3"><span>{error}</span><BrandButton variant="outline" size="sm" onClick={()=>void loadProjections()}>Retry</BrandButton></span></Notice>}
      <Notice tone="info" role="note">{projections[0]?.projectionBasis==='season_bookings'?'Recorded orders use booking dates within the planning season. Each monthly projection covers at least the known bookings, with the statistical forecast retained separately. Planned deliveries determine purchasing needs on a separate date basis.':'This older publication uses recorded open balances across source history; refresh the forecast to apply season booking reconciliation.'} Additional demand is statistical; separate reorder and non-visited customer models are not yet available.</Notice>

      <div className="flex flex-wrap gap-5">
        {/* Total Demand Summary */}
        <section className="relative flex min-w-0 flex-[2_1_560px] flex-col gap-6 overflow-hidden rounded-[32px] bg-champagne p-6 sm:p-8">
          <span aria-hidden className="absolute -right-[60px] -top-[110px] h-80 w-80 rounded-full bg-[radial-gradient(circle,var(--glow),rgba(245,130,32,0)_70%)]" />
          <div className="relative flex flex-col gap-1.5">
            <h2 className="text-lg font-bold">Total Projected Units</h2>
            <p className="text-sm text-brand-800">
              Breakdown by demand source for the {activeScenario} scenario
            </p>
          </div>
          <div className="relative flex flex-wrap items-baseline gap-2.5">
            <span className="font-display text-[56px] font-bold leading-none tracking-[-0.04em] sm:text-[72px]">
              {totalDemand.total.toLocaleString()}
            </span>
            <span className="text-lg text-fg-2">units</span>
          </div>

          <div className="relative">
            <DemandSplitBar
              confirmed={totalDemand.confirmed}
              probableReorders={totalDemand.reorders}
              nonVisitedProjection={totalDemand.nonVisited}
              height="lg"
              showLabels
              className="bg-card"
            />
          </div>

          <div className="relative grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-4 border-t border-brand-200 pt-5">
            <div className="flex flex-col gap-1">
              <p className="text-[13px] text-fg-2">Recorded orders included</p>
              <p className="font-display text-[26px] font-bold text-success-600">
                {totalDemand.confirmed.toLocaleString()}
                {share(totalDemand.confirmed)}
              </p>
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-[13px] text-fg-2">Additional forecast</p>
              <p className="font-display text-[26px] font-bold text-brand-700">
                {totalDemand.reorders.toLocaleString()}
                {share(totalDemand.reorders)}
              </p>
            </div>
            <div className="flex flex-col gap-1">
              <p className="text-[13px] text-fg-2">Unmodeled customer demand</p>
              <p className="font-display text-[26px] font-bold text-fg-2">
                Not modeled
                {share(totalDemand.nonVisited)}
              </p>
            </div>
          </div>
        </section>

        <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-5">
          {/* Confidence Distribution */}
          <section className="flex flex-col gap-3.5 rounded-3xl border border-line bg-card p-6 shadow-card">
            <h2 className="flex items-center gap-2 text-base font-bold">
              <ChartPieSliceIcon className="h-[18px] w-[18px] text-fg-2" />
              Confidence Distribution
            </h2>
            {projections.length > 0 && (
              <div aria-hidden className="flex h-3 gap-[3px] overflow-hidden rounded-full">
                {(["high", "medium", "low"] as const).map((level) =>
                  confidenceDistribution[level] > 0 ? (
                    <div key={level} className={CONFIDENCE_DOT[level]} style={{ width: `${(confidenceDistribution[level] / projections.length) * 100}%` }} />
                  ) : null
                )}
              </div>
            )}
            {(["high", "medium", "low"] as const).map((level) => {
              const count = confidenceDistribution[level];
              const total = projections.length || 1;
              return (
                <div key={level} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div className={cn("h-3 w-3 rounded-full", CONFIDENCE_DOT[level])} />
                    <span className="capitalize">{level}</span>
                  </div>
                  <div className="font-bold">
                    {count}
                    <span className="ml-1 font-normal text-fg-3">
                      ({Math.round((count / total) * 100)}%)
                    </span>
                  </div>
                </div>
              );
            })}
            <p className="border-t border-line pt-3 text-xs leading-[1.55] text-fg-3">
              Confidence reflects available history, not a measured accuracy percentage. Low-confidence articles need human review.
            </p>
          </section>

          <section className="flex flex-1 items-start gap-3 rounded-3xl bg-plum-50 px-6 py-[22px]">
            <QuestionIcon weight="fill" className="mt-px h-5 w-5 shrink-0 text-plum-600" />
            <div className="text-sm leading-[1.55]">
              <p className="font-bold">Understanding Projections</p>
              <p className="mt-1 text-fg-2">
                Open an article to compare its saved Joolan stock balances with
                forecast demand and purchasing needs, by colour and size.
              </p>
            </div>
          </section>
        </div>
      </div>

      {/* Main Table */}
      <section className="min-w-0 overflow-hidden rounded-3xl border border-line bg-card shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-[22px]">
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-bold">Per-SKU Projection</h2>
            {!isLoading && (
              <p className="text-[13px] text-fg-3">
                {filteredProjections.length.toLocaleString()} articles · click a row to open its colour and size matrix
              </p>
            )}
          </div>
          <div className="relative flex w-full items-center sm:w-[260px]">
            <MagnifyingGlassIcon className="pointer-events-none absolute left-3.5 h-4 w-4 text-fg-3" />
            <TextField
              aria-label="Search SKUs"
              placeholder="Search SKUs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          {isLoading ? (
            <div className="space-y-3 p-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded-2xl bg-soft" />
              ))}
            </div>
          ) : (
            <div className="min-w-[900px]">
              {/* Header */}
              <div className={cn(ROW_GRID, "border-b border-line bg-page px-6 py-3 text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3")}>
                <div>SKU</div>
                <div className="text-right">{projections[0]?.projectionBasis==='season_bookings'?'Season bookings':'Open order balance'}</div>
                <div className="text-right">Additional forecast</div>
                <div className="text-right">Non-visited</div>
                <div className="text-right">Total</div>
                <div className="text-center">Confidence</div>
                <div></div>
              </div>

              {/* Rows */}
              {filteredProjections.map((projection) => {
                const scenario = projection.scenarios[activeScenario];
                const isExpanded = expandedRows.has(projection.skuId);
                const detailedData = detailedCache.get(projection.skuId);

                return (
                  <div key={projection.skuId} className="border-b border-line last:border-b-0">
                    <div
                      className={cn(
                        ROW_GRID,
                        "cursor-pointer items-center px-6 py-3.5 transition-colors hover:bg-page",
                        isExpanded && "bg-page"
                      )}
                      onClick={() => toggleRow(projection.skuId)}
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px]", isExpanded ? "bg-brand text-white" : "bg-soft text-fg-2")}>
                          {isExpanded ? (
                            <CaretDownIcon weight="bold" className="h-[13px] w-[13px]" />
                          ) : (
                            <CaretRightIcon weight="bold" className="h-[13px] w-[13px]" />
                          )}
                        </span>
                        <div className="flex min-w-0 flex-col gap-0.5">
                          <p className="truncate font-mono text-sm font-bold">{projection.skuId}</p><ActivityBadge activity={projection.activity}/>
                          <p className="truncate text-xs text-fg-3">{projection.category}</p>
                        </div>
                      </div>
                      <div className="text-right font-mono text-sm font-semibold text-success-600">
                        {scenario.confirmed.toLocaleString()}
                      </div>
                      <div className="text-right font-mono text-sm font-semibold text-brand-700">
                        {scenario.probableReorders.toLocaleString()}
                      </div>
                      <div className="text-right font-mono text-sm font-semibold text-fg-3">
                        —
                      </div>
                      <div className="text-right font-mono text-[15px] font-bold">
                        {scenario.total.toLocaleString()}
                      </div>
                      <div className="flex justify-center">
                        <ConfidenceBadge level={projection.confidence} size="sm" />
                      </div>
                      <div className="flex justify-center">
                        <button
                          type="button"
                          aria-label="Explain projection"
                          aria-expanded={isExpanded}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleRow(projection.skuId);
                          }}
                          className="flex h-8 w-8 items-center justify-center rounded-[10px] hover:bg-soft"
                        >
                          <QuestionIcon className="h-[18px] w-[18px] text-plum-600" />
                        </button>
                      </div>
                    </div>

                    {/* Expandable Detailed Stock Matrix */}
                    {isExpanded&&!detailedData&&<p role={detailErrors[projection.skuId]?'alert':'status'} className={cn("border-t border-line bg-page px-6 py-4 text-sm",detailErrors[projection.skuId]?"text-danger":"text-fg-3")}>{detailErrors[projection.skuId]||'Loading colour and size details…'}</p>}
                    {isExpanded && detailedData && (
                      <div className="border-t border-line bg-page px-6 pb-6 pt-5">
                        <SKUStockMatrix data={detailedData} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>
    </AppShell>
  );
}
