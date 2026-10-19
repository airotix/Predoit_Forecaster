
export type ProductStatus = 'new' | 'carry-over' | 'core';
export type ConfidenceLevel = 'high' | 'medium' | 'low';
export type RecommendationStatus = 'pending' | 'adjusted' | 'locked' | 'validated';

export interface SKU {
  id: string;
  name: string;
  category: string;
  season: string;
  status: ProductStatus;
  wholesalePrice: number;
  supplierPurchasePrice: number;
  currency: string;
  transportDutyCost: number;
  expectedMargin: number;
  availableSizes: string[];
  historicalUnits: number;
  buyingCustomers: number;
  physicalStock: number;
  theoreticalStock: number;
  wipQty: number;
  leadTimeDays: number;
  moq: number;
  industrialMinPerSize: number;
}

export interface SKUKPI {
  skuId: string;
  diffusionRate: number;
  depthPerCustomer: number;
  reorderRate: number;
  totalUnitsSold: number;
  buyingCustomers: number;
  sizeBreakdown: Record<string, number>;
  aiConfidence: ConfidenceLevel;
}

export interface DemandBreakdown {
  confirmed: number;
  probableReorders: number;
  nonVisitedProjection: number;
  total: number;
}

export interface ScenarioProjection {
  conservative: DemandBreakdown;
  base: DemandBreakdown;
  optimistic: DemandBreakdown;
}

export interface SKUProjection {
  skuId: string;
  skuName: string;
  category: string;
  scenarios: ScenarioProjection;
  confidence: ConfidenceLevel;
  explainability: ExplainabilityData;
}

export interface ExplainabilityData {
  confirmedOrders: {
    units: number;
    customerCount: number;
  };
  probableReorders: {
    units: number;
    reorderRate: number;
    likelyCustomers: number;
  };
  nonVisitedDemand: {
    units: number;
    matchedCustomers: number;
    clusterProfile: string;
  };
  keySignals: {
    diffusionRate: number;
    depthPerCustomer: number;
    customerCluster: string;
    scenarioMultiplier: number;
  };
}

export interface SizeRecommendation {
  size: string;
  recommended: number;
  manualOverride: number | null;
  finalQty: number;
  minUnits: number | null;
  maxUnits: number | null;
  blocked: boolean;
  rounding: string | null;
}

export interface SKURecommendation {
  skuId: string;
  skuName: string;
  category: string;
  status: RecommendationStatus;
  locked: boolean;
  scenarios: ScenarioProjection;
  currentScenarioTotal: number;
  sizeBreakdown: SizeRecommendation[];
  confidence: ConfidenceLevel;
  explainability: ExplainabilityData;
  financialImpact: FinancialImpact;
  userOverride?: {
    totalQty: number;
    reason?: string;
    notes?: string;
    timestamp: string;
    user: string;
  };
}

export interface FinancialImpact {
  complete?:boolean;
  purchaseCost: number;
  expectedTurnover: number;
  grossMargin: number;
  marginPercent: number;
  budgetImpactPercent: number;
}

export interface SizeRule {
  size: string;
  minUnits: number | null;
  maxUnits: number | null;
  blocked: boolean;
  rounding: string | null;
}
