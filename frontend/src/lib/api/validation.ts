import { apiClient } from './client';
import {
  ValidationSummary,
  AuditEntry,
  ExportResult,
  ScenarioType,
} from '@/types';

export interface ValidationResponse {
  summary: ValidationSummary;
  canValidate: boolean;
  blockers?: string[];
}

export const validationApi = {
  getSummary: (seasonId: string, scenario: ScenarioType) =>
    apiClient.get<ValidationResponse>(`/seasons/${seasonId}/validation`, { scenario }),

  getAuditTrail: (seasonId: string, limit?: number, offset?: number) =>
    apiClient.get<{ entries: AuditEntry[]; total: number }>(
      `/seasons/${seasonId}/audit`,
      { limit, offset }
    ),

  validate: (seasonId: string, scenario: ScenarioType) =>
    apiClient.post<{ success: boolean; validationId: string }>(
      `/seasons/${seasonId}/validate`,
      { scenario }
    ),

  export: (seasonId: string, format: 'erp' | 'csv' | 'pdf') =>
    apiClient.post<ExportResult>(`/seasons/${seasonId}/export`, { format }),

  downloadExport: (seasonId: string, exportId: string) => {
    const url = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000/api'}/seasons/${seasonId}/export/${exportId}/download`;
    window.open(url, '_blank');
  },
};
