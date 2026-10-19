import { apiClient } from "./client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

export interface IngestResult {
  jobId: string;
  status: string;
  mode?: "erp" | "sample";
  rowsAdded: number;
  rowsUpdated: number;
  rowsSkipped: number;
  byTable?: Record<
    string,
    { added: number; updated: number; skipped: number }
  >;
}

export interface ErpStatus {
  enabled: boolean;
  configured: boolean;
  hasHistoryQuery: boolean;
  baseUrl: string | null;
  enseigne: string | null;
  mode: "erp" | "sample";
  provider: string;
}

export interface IngestJobStatus {
  jobId: string;
  jobType: string;
  status: string;
  rowsAdded: number;
  rowsUpdated: number;
  rowsSkipped: number;
  errorMessage: string | null;
  startedAt: string;
  finishedAt: string | null;
}

export interface ForecastJobStatus {
  jobId: string | null;
  status: string;
  lastRun: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export async function uploadFile(file: File): Promise<IngestResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/ingest/file`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail: string;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `Upload failed: ${res.status}`);
  }
  return res.json() as Promise<IngestResult>;
}

export const syncERP = () =>
  apiClient.post<IngestResult>("/ingest/erp", {});

export const getErpStatus = () =>
  apiClient.get<ErpStatus>("/ingest/erp/status");

export const getIngestStatus = (jobId: string) =>
  apiClient.get<IngestJobStatus>(`/ingest/status/${jobId}`);

export const triggerForecastRefresh = () =>
  apiClient.post<{ jobId: string; status: string }>("/forecast/refresh", {});

export const getForecastJobStatus = () =>
  apiClient.get<ForecastJobStatus>("/forecast/job");
