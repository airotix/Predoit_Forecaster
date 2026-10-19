import { apiClient } from './client';
import {
  SKU,
  SKUKPI,
  SKUProjection,
  SKURecommendation,
  SizeRecommendation,
} from '@/types';

export interface ProductsResponse {
  products: SKU[];
  total: number;
}

export interface ProjectionsResponse {
  projections: SKUProjection[];
  totalDemand: {
    conservative: number;
    base: number;
    optimistic: number;
  };
  breakdown: {
    confirmed: number;
    probableReorders: number;
    nonVisitedProjection: number;
  };
}

export interface RecommendationsResponse {
  recommendations: SKURecommendation[];
  summary: {
    totalSKUs: number;
    pending: number;
    adjusted: number;
    locked: number;
    validated: number;
  };
}

export interface OverridePayload {
  totalQty?: number;
  sizes?: SizeRecommendation[];
  locked?: boolean;
  reason?: string;
  notes?: string;
}

export const productsApi = {
  list: (seasonId: string, filters?: Record<string, string | string[]>) =>
    apiClient.get<ProductsResponse>(`/seasons/${seasonId}/products`, filters as Record<string, string>),

  get: (seasonId: string, skuId: string) =>
    apiClient.get<SKU>(`/seasons/${seasonId}/products/${skuId}`),

  getKPIs: (seasonId: string) =>
    apiClient.get<Record<string, SKUKPI>>(`/seasons/${seasonId}/products/kpis`),

  getProjections: (seasonId: string) =>
    apiClient.get<ProjectionsResponse>(`/seasons/${seasonId}/projection`),

  getRecommendations: (seasonId: string) =>
    apiClient.get<RecommendationsResponse>(`/seasons/${seasonId}/recommendations`),

  getRecommendation: (seasonId: string, skuId: string) =>
    apiClient.get<SKURecommendation>(`/seasons/${seasonId}/recommendations/${skuId}`),

  updateRecommendation: (seasonId: string, skuId: string, data: OverridePayload) =>
    apiClient.put<SKURecommendation>(`/seasons/${seasonId}/recommendations/${skuId}`, data),

  lockSKU: (seasonId: string, skuId: string) =>
    apiClient.post<SKURecommendation>(`/seasons/${seasonId}/recommendations/${skuId}/lock`),

  unlockSKU: (seasonId: string, skuId: string) =>
    apiClient.post<SKURecommendation>(`/seasons/${seasonId}/recommendations/${skuId}/unlock`),

  bulkUpdate: (
    seasonId: string,
    updates: Array<{ skuId: string; data: OverridePayload }>
  ) => apiClient.post<{ updated: number }>(`/seasons/${seasonId}/recommendations/bulk`, { updates }),

  updateSupplyChain: (
    seasonId: string,
    skuId: string,
    data: {
      physicalStock?: number;
      theoreticalStock?: number;
      wipQty?: number;
      leadTimeDays?: number;
      moq?: number;
      industrialMinPerSize?: number;
    }
  ) => apiClient.patch<SKU>(`/seasons/${seasonId}/products/${skuId}/supply-chain`, data),

  updateFinance: (
    seasonId: string,
    skuId: string,
    data: {
      supplierPurchasePrice?: number;
      currency?: string;
      transportDutyCost?: number;
      expectedMargin?: number;
    }
  ) => apiClient.patch<SKU>(`/seasons/${seasonId}/products/${skuId}/finance`, data),
};
