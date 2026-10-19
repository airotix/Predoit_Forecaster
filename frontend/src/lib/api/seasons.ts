import { apiClient } from './client';
import {
  Season,
  SeasonConfig,
  FinancialSummary,
  Alert,
  DashboardKPI,
  ActivityLog,
} from '@/types';

export interface DashboardResponse {
  season: Season;
  kpis: DashboardKPI[];
  alerts: Alert[];
  financialSummary: FinancialSummary;
  recentActivity: ActivityLog[];
}

export const seasonsApi = {
  active: () => apiClient.get<Season | null>('/seasons/active'),
  activate: (id:string) => apiClient.post<Season>(`/seasons/${id}/activate`),
  list: () => apiClient.get<Season[]>('/seasons'),

  get: (seasonId: string) => apiClient.get<Season>(`/seasons/${seasonId}`),

  create: (config: SeasonConfig) => apiClient.post<Season>('/seasons', config),

  update: (seasonId: string, data: Partial<Season>) =>
    apiClient.patch<Season>(`/seasons/${seasonId}`, data),

  delete: (seasonId: string) => apiClient.delete<void>(`/seasons/${seasonId}`),

  getDashboard: (seasonId: string) =>
    apiClient.get<DashboardResponse>(`/seasons/${seasonId}/dashboard`),

  triggerImport: (
    seasonId: string,
    type: 'erp' | 'csv',
    dataType: 'products' | 'customers' | 'supply_chain' | 'finance',
    file?: File
  ) => {
    if (type === 'csv' && file) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('dataType', dataType);
      return fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api'}/seasons/${seasonId}/import`,
        {
          method: 'POST',
          body: formData,
        }
      ).then((res) => res.json());
    }
    return apiClient.post(`/seasons/${seasonId}/import`, { type, dataType });
  },

  initializeModel: (seasonId: string) =>
    apiClient.post<{ status: string }>(`/seasons/${seasonId}/initialize`),

  validate: (seasonId: string) =>
    apiClient.post<{ success: boolean; exportId: string }>(`/seasons/${seasonId}/validate`),
};
