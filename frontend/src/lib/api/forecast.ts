import { apiClient } from './client';
import { useSeasonStore } from '@/store/seasonStore';

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export interface DashboardData {
  financialComplete: boolean; missingInputRows: number;
  kpis: Array<{
    label: string;
    value: string;
    subLabel: string;
    trend: 'up' | 'down' | 'neutral';
    trendValue: number;
  }>;
  financialSummary: {
    budgetUsed: number;
    budgetTotal: number;
    margin: number;
    targetMargin: number;
    coverage: number;
    totalPurchaseCost: number;
    expectedTurnover: number;
  };
  confidenceDistribution: Record<string, number>;
  lastPipelineRun: string | null;
  totalSKUs: number;
}

export const fetchDashboard = () =>
  apiClient.get<DashboardData>('/dashboard');

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

export interface ProductRow {
  skuId: string;
  name: string;
  category: string;
  status: string;
  season: string;
  diffusionRate: number;
  depthPerCustomer: number;
  reorderRate: number|null;
  repeatOrderRate: number|null;
  reorderCustomers: number;
  repeatOrderCustomers: number;
  reorderBuyingCustomers: number;
  reorderMissingLines: number;
  reorderDefinition: string;
  totalUnitsSold: number|null;
  historicalDemand: number|null;
  forecastUnits: number;
  historyStart: string|null;
  historyEnd: string|null;
  forecastStart: string|null;
  forecastEnd: string|null;
  trainingCutoff: string|null;
  ordersThrough: string|null;
  demandDefinition: string;
  buyingCustomers: number;
  sizeBreakdown: Record<string, number>;
  aiConfidence: string;
}

export const fetchProducts = (params?: {
  season?: string;
  category?: string;
  status?: string;
  search?: string;
}) =>
  apiClient.get<ProductRow[]>('/products', params as Record<string, string>);

export interface ProductSizeHistory {
  reference:string;color:string;startDate:string;endDate:string;forecastStart:string;
  sizeBreakdown:Record<string,number>;totalUnits:number;definition:string;
}
export const fetchProductSizeHistory=(reference:string,color:string)=>
  apiClient.get<ProductSizeHistory>('/products/size-history',{reference,color});

// ---------------------------------------------------------------------------
// Projections
// ---------------------------------------------------------------------------

export interface ProjectionRow {
  projectionBasis?: 'season_bookings' | 'legacy_open_balances';
  skuId: string;
  skuName: string;
  category: string;
  scenarios: {
    conservative: { confirmed: number; probableReorders: number; nonVisitedProjection: number; total: number };
    base: { confirmed: number; probableReorders: number; nonVisitedProjection: number; total: number };
    optimistic: { confirmed: number; probableReorders: number; nonVisitedProjection: number; total: number };
  };
  confidence: 'high' | 'medium' | 'low';
  explainability: {
    confirmedOrders: { units: number; customerCount: number };
    probableReorders: { units: number; reorderRate: number; likelyCustomers: number };
    nonVisitedDemand: { units: number; matchedCustomers: number; clusterProfile: string };
    keySignals: { diffusionRate: number; depthPerCustomer: number; customerCluster: string; scenarioMultiplier: number };
  };
}

export type ProjectionDetail = import("@/types/stockMatrix").SKUDetailedProjection;

export const fetchProjections = (params?: { season?: string; search?: string }) =>
  apiClient.get<ProjectionRow[]>('/projections', params as Record<string, string>);

export const fetchProjectionDetail = (reference: string, scenario: string = 'base') =>
  apiClient.get<ProjectionDetail>(`/projections/${encodeURIComponent(reference)}/detail`, {scenario});

// ---------------------------------------------------------------------------
// Budget
// ---------------------------------------------------------------------------

export interface BudgetData {
  financialComplete: boolean; missingInputRows: number;
  summary: {
    totalPurchaseCost: number;
    seasonBudget: number;
    expectedTurnover: number;
    grossMargin: number;
    grossMarginPercent: number;
  };
  categories: Array<{
    category: string;
    purchaseCost: number;
    budgetPercent: number;
    marginPercent: number;
    status: 'on_target' | 'below_margin' | 'over_budget';
    skus: Array<{
      skuId: string;
      name: string;
      purchaseCost: number;
      margin: number;
      targetMargin: number;
    }>;
  }>;
}

export const fetchBudget = (scenario?: string) =>
  apiClient.get<BudgetData>('/budget', { scenario });

// ---------------------------------------------------------------------------
// Recommendations
// ---------------------------------------------------------------------------

export interface RecommendationRow {
  draftVersion?:number;
  forecastRun?:string;
  skuId: string;
  skuName: string;
  category: string;
  status: string;
  locked: boolean;
  scenarios: {
    conservative: { confirmed: number; probableReorders: number; nonVisitedProjection: number; total: number };
    base: { confirmed: number; probableReorders: number; nonVisitedProjection: number; total: number };
    optimistic: { confirmed: number; probableReorders: number; nonVisitedProjection: number; total: number };
  };
  currentScenarioTotal: number;
  purchaseTotals:Record<string,number|null>;
  historicalSizes:Record<string,number>;
  sizeBreakdown: Array<{
    size: string;
    forecast:number;
    recommended: number|null;
    manualOverride: number | null;
    finalQty: number|null;
    minUnits: number | null;
    maxUnits: number | null;
    blocked: boolean;
    rounding: string | null;
  }>;
  confidence: string;
  explainability: {
    confirmedOrders: { units: number; customerCount: number };
    probableReorders: { units: number; reorderRate: number; likelyCustomers: number };
    nonVisitedDemand: { units: number; matchedCustomers: number; clusterProfile: string };
    keySignals: { diffusionRate: number; depthPerCustomer: number; customerCluster: string; scenarioMultiplier: number };
  };
  financialImpact: {
    complete?:boolean;
    purchaseCost: number;
    expectedTurnover: number;
    grossMargin: number;
    marginPercent: number;
    budgetImpactPercent: number;
  };
}

export const fetchRecommendations = (params?: {
  season?: string;
  scenario?: string;
  search?: string;
  status?: string;
  category?: string;
}) =>
  apiClient.get<RecommendationRow[]>('/recommendations', params as Record<string, string>);

export const updateRecommendation = (
  reference: string,
  couleur: string,
  data: { sizeBreakdown: Array<{ size: string; finalQty: number }>; reason?: string; notes?: string;draftVersion?:number;forecastRun?:string }
) =>
  apiClient.put<{ status: string }>(`/recommendations/${encodeURIComponent(reference)}/${encodeURIComponent(couleur)}`, {...data,scenario:useSeasonStore.getState().activeScenario});

export const lockRecommendation = (reference: string, couleur: string) =>
  apiClient.post<{ status: string }>(`/recommendations/${encodeURIComponent(reference)}/${encodeURIComponent(couleur)}/lock`);

export const unlockRecommendation = (reference: string, couleur: string) =>
  apiClient.post<{ status: string }>(`/recommendations/${encodeURIComponent(reference)}/${encodeURIComponent(couleur)}/unlock`);

// ---------------------------------------------------------------------------
// Validation & Audit
// ---------------------------------------------------------------------------

export interface ValidationData {
  financialComplete: boolean;
  approvalAvailable: boolean;
  approvalNotice: string;
  skuCount: number;
  scenarioMetrics: Record<string, {
    totalUnits: number | null;
    purchaseCost: number | null;
    budgetUsage: number | null;
    grossMargin: number | null;
    skusAtRisk: number;
  }>;
  overrides: Array<{
    skuId: string;
    skuName: string;
    aiRecommended: number;
    userOverride: number;
    reasonTag: string;
    notes: string;
  }>;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  user: string;
  action: string;
  entity_type: string;
  entity_id: string;
  entity_name: string | null;
  previous_value: string | null;
  new_value: string | null;
  details: string | null;
}

export const fetchValidation = (scenario?: string) =>
  apiClient.get<ValidationData>('/validation', { scenario });

export const fetchAudit = (limit?: number) =>
  apiClient.get<AuditEntry[]>('/audit', { limit });

export const exportRecommendations = async (format = 'csv', scenario = 'base', seasonId?:string, purpose = 'draft') => {
  const params=new URLSearchParams({format,scenario,purpose});if(seasonId)params.set('season_id',seasonId);
  const token=await import('./tokenProvider').then(m=>m.getAccessToken());
  const response=await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api'}/export?${params}`,{headers:token?{Authorization:`Bearer ${token}`}:{}});
  if(!response.ok){const result=await response.json().catch(()=>null);throw new Error(result?.detail||'Export failed');}
  const blob=await response.blob();const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`recommendations_${scenario}_${purpose}.${format}`;
  document.body.appendChild(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
};

// ---------------------------------------------------------------------------
// Pipeline Status
// ---------------------------------------------------------------------------

export interface PipelineStatus {
  lastRun: string | null;
  status: string;
  totalRecommendations: number;
  totalSKUs: number;
}

export const fetchPipelineStatus = () =>
  apiClient.get<PipelineStatus>('/pipeline/status');

export const resetRecommendation = (reference:string,couleur:string,scenario:string,draftVersion?:number,forecastRun?:string) => apiClient.delete(`/recommendations/${encodeURIComponent(reference)}/${encodeURIComponent(couleur)}/override`,{scenario,draftVersion,forecastRun});

// Packaged-runtime compatibility helpers retained from main.
// Forecast accuracy / backtest
// ---------------------------------------------------------------------------

export interface ForecastAccuracyData {
  headline: {
    wmape: number | null;
    bias: number | null;
    coverage80: number | null;
    lastRunAt: string | null;
    skuCount: number;
  };
  byModelType: Array<{
    modelType: string;
    wmape: number | null;
    bias: number | null;
    coverage80: number | null;
    skuCount: number;
  }>;
  byCategory: Array<{
    famille: string;
    wmape: number | null;
    bias: number | null;
    coverage80: number | null;
    skuCount: number;
  }>;
  trend: Array<{
    foldMonth: string;
    wmape: number | null;
    bias: number | null;
    coverage80: number | null;
  }>;
}

export interface BacktestJobStatus {
  runId: number | null;
  status: string;
  startedAt?: string | null;
  completedAt?: string | null;
  holdoutMonths?: number;
}

export const fetchForecastAccuracy = () =>
  apiClient.get<ForecastAccuracyData>('/forecast/accuracy');

export const triggerBacktest = (holdoutMonths?: number) =>
  apiClient.post<{ runId: number; status: string; holdoutMonths: number }>(
    '/forecast/backtest',
    undefined,
    holdoutMonths ? { holdoutMonths } : undefined
  );

export const getBacktestStatus = (runId?: number) =>
  apiClient.get<BacktestJobStatus>('/forecast/backtest/status', runId ? { runId } : undefined);

export const downloadExport = async (format = 'csv') => {
  const token = await import('./tokenProvider').then((m) => m.getAccessToken());
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api';
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${base}/export?format=${format}`, {
    method: 'POST',
    headers,
  });
  if (!response.ok) throw new Error('Export failed');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `recommendations.${format}`;
  a.click();
  URL.revokeObjectURL(url);
};
