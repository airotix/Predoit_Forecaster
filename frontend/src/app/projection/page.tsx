"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { ScenarioSwitcher, DemandSplitBar, ConfidenceBadge } from "@/components/shared";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useSeasonStore } from "@/store/seasonStore";
import { cn } from "@/lib/utils";
import {
  Search,
  HelpCircle,
  PieChart,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { ConfidenceLevel } from "@/types";
import { SKUDetailedProjection } from "@/types/stockMatrix";
import { SKUStockMatrix } from "@/components/forecast/SKUStockMatrix";
import { fetchProjections, fetchProjectionDetail, type ProjectionRow } from "@/lib/api/forecast";
import { useDataRefresh } from "@/hooks/useDataRefresh";

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

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Demand Projection</h1>
            <p className="text-slate-500 dark:text-slate-400 mt-1">
              AI-powered demand forecasting across scenarios
            </p>
          </div>
          <ScenarioSwitcher />
        </div>

        {error&&<p role="alert" className="rounded-lg border border-red-200 p-4 text-red-700">{error} <Button variant="outline" onClick={()=>void loadProjections()}>Retry</Button></p>}
        <p className="text-sm text-slate-500">{projections[0]?.projectionBasis==='season_bookings'?'Recorded orders use booking dates within the planning season. Each monthly projection covers at least the known bookings, with the statistical forecast retained separately. Planned deliveries determine purchasing needs on a separate date basis.':'This older publication uses recorded open balances across source history; refresh the forecast to apply season booking reconciliation.'} Additional demand is statistical; separate reorder and non-visited customer models are not yet available.</p>
        {/* Total Demand Summary */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Total Projected Units</CardTitle>
            <CardDescription>
              Breakdown by demand source for the {activeScenario} scenario
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-4xl font-bold">
              {totalDemand.total.toLocaleString()}
              <span className="text-lg font-normal text-slate-500 ml-2">units</span>
            </div>

            <DemandSplitBar
              confirmed={totalDemand.confirmed}
              probableReorders={totalDemand.reorders}
              nonVisitedProjection={totalDemand.nonVisited}
              height="lg"
              showLabels
            />

            <div className="grid gap-4 pt-4 sm:grid-cols-3 border-t border-slate-200 dark:border-slate-800">
              <div>
                <p className="text-sm text-slate-500">Recorded orders included</p>
                <p className="text-xl font-semibold text-emerald-600">
                  {totalDemand.confirmed.toLocaleString()}
                  {totalDemand.total > 0 && (
                    <span className="text-sm font-normal text-slate-500 ml-1">
                      ({Math.round((totalDemand.confirmed / totalDemand.total) * 100)}%)
                    </span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm text-slate-500">Additional forecast</p>
                <p className="text-xl font-semibold text-blue-600">
                  {totalDemand.reorders.toLocaleString()}
                  {totalDemand.total > 0 && (
                    <span className="text-sm font-normal text-slate-500 ml-1">
                      ({Math.round((totalDemand.reorders / totalDemand.total) * 100)}%)
                    </span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm text-slate-500">Unmodeled customer demand</p>
                <p className="text-xl font-semibold text-slate-600">
                  Not modeled
                  {totalDemand.total > 0 && (
                    <span className="text-sm font-normal text-slate-500 ml-1">
                      ({Math.round((totalDemand.nonVisited / totalDemand.total) * 100)}%)
                    </span>
                  )}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Content Grid */}
        <div className="grid items-start gap-6 2xl:grid-cols-[minmax(0,1fr)_280px]">
          {/* Main Table */}
          <Card className="min-w-0 overflow-hidden">
            <CardHeader className="pb-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <CardTitle className="text-lg">Per-SKU Projection</CardTitle>
                <div className="relative w-64">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <Input
                    placeholder="Search SKUs..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="h-16 bg-slate-100 dark:bg-slate-800 rounded animate-pulse" />
                  ))}
                </div>
              ) : (
                <div className="min-w-[880px] border rounded-lg divide-y divide-slate-200 dark:divide-slate-800">
                  {/* Header */}
                  <div className="grid grid-cols-[1fr_100px_100px_100px_100px_80px_60px] gap-4 px-4 py-3 bg-slate-50 dark:bg-slate-900 text-xs font-medium text-slate-500 uppercase tracking-wide">
                    <div>SKU</div>
                    <div className="text-right">Order balance</div>
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
                      <div key={projection.skuId}>
                        <div
                          className={cn(
                            "grid grid-cols-[1fr_100px_100px_100px_100px_80px_60px] gap-4 px-4 py-3 items-center hover:bg-slate-50 dark:hover:bg-slate-900 transition-colors cursor-pointer",
                            isExpanded && "bg-slate-50 dark:bg-slate-900"
                          )}
                          onClick={() => toggleRow(projection.skuId)}
                        >
                          <div className="flex items-center gap-2">
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-slate-400 shrink-0" />
                            )}
                            <div>
                              <p className="font-medium text-sm">{projection.skuId}</p>
                              <p className="text-xs text-slate-500">{projection.category}</p>
                            </div>
                          </div>
                          <div className="text-right text-sm font-medium text-emerald-600">
                            {scenario.confirmed.toLocaleString()}
                          </div>
                          <div className="text-right text-sm font-medium text-blue-600">
                            {scenario.probableReorders.toLocaleString()}
                          </div>
                          <div className="text-right text-sm font-medium text-slate-600">
                            —
                          </div>
                          <div className="text-right text-sm font-bold">
                            {scenario.total.toLocaleString()}
                          </div>
                          <div className="flex justify-center">
                            <ConfidenceBadge level={projection.confidence} size="sm" />
                          </div>
                          <div>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleRow(projection.skuId);
                              }}
                              className="h-8 w-8 p-0"
                            >
                              <HelpCircle className="h-4 w-4 text-blue-500" />
                            </Button>
                          </div>
                        </div>

                        {/* Expandable Detailed Stock Matrix */}
                        {isExpanded&&!detailedData&&<p role={detailErrors[projection.skuId]?'alert':'status'} className="p-4 text-sm">{detailErrors[projection.skuId]||'Loading colour and size details…'}</p>}
                        {isExpanded && detailedData && (
                          <div className="p-4 bg-slate-50/50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-800">
                            <SKUStockMatrix data={detailedData} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Confidence Distribution Sidebar */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  <PieChart className="h-4 w-4" />
                  Confidence Distribution
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(["high", "medium", "low"] as const).map((level) => {
                  const count = confidenceDistribution[level];
                  const total = projections.length || 1;
                  const colors = { high: "bg-emerald-500", medium: "bg-amber-500", low: "bg-rose-500" };
                  return (
                    <div key={level} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={cn("h-3 w-3 rounded-full", colors[level])} />
                        <span className="text-sm capitalize">{level}</span>
                      </div>
                      <div className="text-sm font-medium">
                        {count}
                        <span className="text-slate-500 ml-1">
                          ({Math.round((count / total) * 100)}%)
                        </span>
                      </div>
                    </div>
                  );
                })}

                <div className="pt-3 border-t border-slate-200 dark:border-slate-800">
                  <p className="text-xs text-slate-500">
                    Confidence reflects available history, not a measured accuracy percentage. Low-confidence articles need human review.
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <HelpCircle className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
                  <div className="text-sm">
                    <p className="font-medium text-blue-900 dark:text-blue-100">
                      Understanding Projections
                    </p>
                    <p className="text-blue-700 dark:text-blue-300 mt-1">
                      Click any row to see the detailed stock matrix with color and size breakdowns
                      from the ML forecasting model.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
