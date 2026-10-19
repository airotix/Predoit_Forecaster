// Re-export domain types selectively to avoid conflicts
export {
  type ScenarioType,
  type SeasonStatus,
  type Season,
  type FinancialSummary,
  type Alert,
  type DashboardKPI,
  type ActivityLog,
  type SeasonConfig,
} from './season';

export * from './product';
export * from './customer';
export * from './validation';
export * from './stockMatrix';

// Legacy types for backward compatibility with existing components
export type LegacySeason = string;

export interface ForecastMatrixValue {
    forecast: number;
    stock: number;
    orders: number;
}

export interface MetricTrend {
    value: number;
    trend: "up" | "down" | "neutral";
    percentage: number;
}

export interface ArticleData {
    id: string;
    season: LegacySeason;
    supplier: string;
    customer: string;
    family: string;
    theme: string;
    model: string;
    sizes: string[];
    colors: string[];
    matrix: Record<string, Record<string, ForecastMatrixValue>>;
    demandTrend: { date: string; value: number }[];
    price: number;
    cost: number;
}

export interface FilterState {
    supplier: string | null;
    family: string | null;
    theme: string | null;
    model: string | null;
    customer: string | null;
    searchQuery: string;
}

export interface FilterOptions {
    seasons: string[];
    suppliers: string[];
    families: string[];
    themes: string[];
    models: string[];
    customers: string[];
}

export interface KPIData {
    riskItems: MetricTrend;
    totalForecastQuantity: MetricTrend;
    totalCost: MetricTrend;
}

export interface BudgetData {
    seasonBudget: number;
    forecastSpend: number;
}

export interface CustomerSummaryLegacy {
    name: string;
    totalOrders: number;
    visitedSeasons: string[];
    lastSeason: string | null;
    visitedInLatestSeason: boolean;
}

export interface CustomersResponse {
    customers: CustomerSummaryLegacy[];
    seasons: string[];
    latestSeason: string | null;
}

export interface CustomersV2Response {
    customers: import('./customer').Customer[];
    regions: string[];
    latestSeason: string | null;
}

export interface CustomerDetailV2Response {
    customer: string;
    purchaseHistory: import('./customer').PurchaseHistoryItem[];
    seasons: string[];
}

export interface CustomerDetailLegacy {
    customer: string;
    season: string | null;
    seasonsAvailable: string[];
    totalOrders: number;
    articles: ArticleData[];
}
