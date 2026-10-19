export type CustomerTypology = 'independent' | 'chain' | 'key_account';
export type VisitedStatus = 'visited' | 'not_visited';
export type MatchConfidence = 'high' | 'medium' | 'low';

export interface Customer {
  id: string;
  name: string;
  typology: CustomerTypology;
  region: string;
  categories: string[];
  reorderFrequency: number;
  avgBasket: number;
  status: VisitedStatus;
  matchedTo?: string;
  similarityScore?: number;
  matchConfidence?: MatchConfidence;
}

export interface CustomerCluster {
  id: string;
  name: string;
  profile: string;
  visitedCount: number;
  notVisitedCount: number;
  characteristics: string[];
}

export interface CustomerCoverageStats {
  total: number;
  visited: number;
  notVisited: number;
  visitedPercent: number;
}

export interface CustomerProjection {
  customerId: string;
  customerName: string;
  matchedCluster: CustomerCluster;
  projectedDemand: number;
  similarities: string[];
  confidence: MatchConfidence;
  purchaseHistory: PurchaseHistoryItem[];
}

export interface PurchaseHistoryItem {
  skuId: string;
  skuName: string;
  season: string;
  units: number;
  value: number;
}

export interface CustomerImportRow {
  customerId: string;
  typology: CustomerTypology;
  region: string;
  categories: string;
  reorderFreq: number;
  avgBasket: number;
  status: VisitedStatus;
}

export interface GeographyData {
  region: string;
  visited: number;
  notVisited: number;
  total: number;
}

export interface TypologyData {
  typology: CustomerTypology;
  visited: number;
  notVisited: number;
  total: number;
}
