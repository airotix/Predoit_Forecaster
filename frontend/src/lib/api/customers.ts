import { apiClient } from './client';
import {
  Customer,
  CustomerCluster,
  CustomerCoverageStats,
  CustomerProjection,
  GeographyData,
  TypologyData,
} from '@/types';

export interface CustomersResponse {
  customers: Customer[];
  total: number;
  coverageStats: CustomerCoverageStats;
}

export interface CustomerCoverageResponse {
  coverageStats: CustomerCoverageStats;
  byGeography: GeographyData[];
  byTypology: TypologyData[];
  clusters: CustomerCluster[];
}

export const customersApi = {
  list: (seasonId: string, filters?: Record<string, string | string[]>) =>
    apiClient.get<CustomersResponse>(`/seasons/${seasonId}/customers`, filters as Record<string, string>),

  get: (seasonId: string, customerId: string) =>
    apiClient.get<Customer>(`/seasons/${seasonId}/customers/${customerId}`),

  getCoverage: (seasonId: string) =>
    apiClient.get<CustomerCoverageResponse>(`/seasons/${seasonId}/customers/coverage`),

  getProjection: (seasonId: string, customerId: string) =>
    apiClient.get<CustomerProjection>(`/seasons/${seasonId}/customers/${customerId}/projection`),

  updateStatus: (seasonId: string, customerId: string, status: 'visited' | 'not_visited') =>
    apiClient.patch<Customer>(`/seasons/${seasonId}/customers/${customerId}`, { status }),

  bulkUpdateStatus: (
    seasonId: string,
    updates: Array<{ customerId: string; status: 'visited' | 'not_visited' }>
  ) => apiClient.post<{ updated: number }>(`/seasons/${seasonId}/customers/bulk-status`, { updates }),
};
