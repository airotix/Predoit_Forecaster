import { ScenarioType } from './season';

export interface ScenarioComparison {
  metric: string;
  conservative: number | string;
  base: number | string;
  optimistic: number | string;
}

export interface OverrideSummary {
  skuId: string;
  skuName: string;
  reference?: string;
  couleur?: string;
  taille?: string;
  aiRecommended: number;
  userOverride: number;
  reasonTag: string;
  notes?: string;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  user: string;
  action: 'created' | 'updated' | 'locked' | 'unlocked' | 'validated' | 'exported';
  entityType: 'sku' | 'season' | 'recommendation';
  entityId: string;
  entityName?: string;
  previousValue?: string | number;
  newValue?: string | number;
  details?: string;
}

export interface ValidationSummary {
  seasonId: string;
  seasonName: string;
  activeScenario: ScenarioType;
  totalUnits: number;
  totalSKUs: number;
  purchaseCost: number;
  budgetUsage: number;
  grossMargin: number;
  skusAtRisk: number;
  overrides: OverrideSummary[];
  auditTrail: AuditEntry[];
}

export interface ExportResult {
  success: boolean;
  exportId: string;
  timestamp: string;
  recordsExported: number;
  errors?: string[];
}
