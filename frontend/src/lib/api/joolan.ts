import { getIngestStatus } from "./ingest";
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";
export interface JoolanSummary {
  totalRows: number; usableRows: number; quarantinedRows: number;
  rowsAdded?: number; rowsUpdated?: number; rowsSkipped?: number; rowsRemoved?: number;
  importedAt?: string; origin?: string; notice: string; forecastSource: "legacy" | "joolan" | "combined";
  documentTypes: { type: string; rows: number }[];
  customerOrderType: string;
}
export interface JoolanOrder {
  Order_Number: string; Customer: string; Order_Date: string; Product: string;
  Ordered_Quantity: number | string | null; Delivered_Quantity: number | string | null;
  Store: string; Colour: string; Size: string; Document_Type: string;
  Usable: boolean; Issues: string[];
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/joolan${path}`, options);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === "string" ? data.detail : `Joolan request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
export const getJoolanOrders = (offset = 0) => request<{ rows: JoolanOrder[]; summary: JoolanSummary }>(`/orders?offset=${offset}&limit=25`);
export const importJoolanWorkbook = (file: File) => {
  const body = new FormData(); body.append("file", file);
  return request<{ snapshot: JoolanSummary }>("/file", { method: "POST", body });
};
export const startJoolanSync = (apiKey: string, enseigne: string, documentType: string, startDate?: string, endDate?: string) =>
  request<{ jobId: string; status: string }>("/sync", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ apiKey, enseigne, documentType, startDate: startDate || undefined, endDate: endDate || undefined }) });
export const setJoolanForecastSource = (source: "legacy" | "joolan" | "combined") =>
  request<JoolanSummary>("/forecast-source", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source }) });
export const confirmJoolanOrderType = (documentType:string) =>
  request<JoolanSummary>("/order-type",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({documentType})});
export { getIngestStatus as getJoolanJobStatus };

export interface JoolanSchema {
  enseigne: string; discoveredAt: string; notice: string;
  tables: { name: string; columns: { name: string; dataType: string; key: string; nullable: boolean }[] }[];
}
export interface HistoricalProfile {
  fileName: string; bytes: number; rows: number; invalidDateRows: number;
  firstOrderDate: string; lastOrderDate: string; notice: string;
  columns: string[]; months: { month: string; rows: number }[];
}
export const discoverJoolanSchema = (apiKey: string, enseigne: string) =>
  request<JoolanSchema>('/schema', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ apiKey, enseigne }) });
export const inspectHistoricalCsv = async (): Promise<HistoricalProfile> => {
  const response = await fetch(`${API_BASE}/history/profile`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Could not inspect historical CSV');
  return data;
};
export interface CombinedHistory {
  legacyRows: number; joolanRows: number; totalRows: number; csvCutoff: string;
  firstDate: string | null; lastDate: string | null; coveredThrough: string;
  needsOrderType: boolean; gaps: { start: string; end: string }[]; notice: string;
  rawJoolanRows: number; rawQuarantinedRows: number; storedRows: number;
  legacyQuarantinedRows: number; forecastLegacyRows: number;
}
export const buildCombinedHistory = async (): Promise<CombinedHistory> => {
  const response = await fetch(`${API_BASE}/history/build`, { method: 'POST' });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Could not build combined history');
  return data;
};
export const getCombinedHistory = async (): Promise<CombinedHistory> => {
  const response = await fetch(`${API_BASE}/history/summary`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Could not read combined history');
  return data;
};
