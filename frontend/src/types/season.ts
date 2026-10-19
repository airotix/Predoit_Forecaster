export type ScenarioType = 'conservative' | 'base' | 'optimistic';

export type SeasonStatus = 'draft' | 'active' | 'validated' | 'reopened';

export interface Season {
  id: string;
  name: string;
  startDate: string;
  endDate: string;
  currency: string;
  budget: number;
  targetMargin: number;
  status: SeasonStatus;
  createdAt: string;
  updatedAt: string;
}

export interface FinancialSummary {
  budgetUsed: number;
  budgetTotal: number;
  margin: number;
  targetMargin: number;
  coverage: number;
  totalPurchaseCost: number;
  expectedTurnover: number;
}

export interface Alert {
  id: string;
  type: 'budget_overrun' | 'margin_miss' | 'coverage_risk' | 'stockout_risk';
  title: string;
  message: string;
  severity: 'warning' | 'danger';
  link: string;
  dismissed: boolean;
}

export interface DashboardKPI {
  label: string;
  value: number | string;
  subLabel: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: number;
  link?: string;
}

export interface ActivityLog {
  id: string;
  action: string;
  skuId?: string;
  skuName?: string;
  user: string;
  timestamp: string;
  details?: string;
}

export interface SeasonConfig {
  name: string;
  startDate: string;
  endDate: string;
  currency: string;
  budget: number;
  targetMargin: number;
}
