export type Season = "SS2024" | "FW2024" | "SS2025" | "FW2025";

export interface ForecastMatrixValue {
  forecast: number;
  stock: number;
  orders: number;
}

export interface ArticleData {
  id: string;
  season: Season;
  supplier: string;
  customer: string;
  family: string;
  theme: string;
  model: string;
  sizes: string[];
  colors: string[];
  matrix: Record<string, Record<string, ForecastMatrixValue>>;
  demandTrend: { date: string; value: number }[];
  price: number;
  cost: number;
}

export interface FilterQuery {
  season: Season;
  supplier?: string;
  family?: string;
  theme?: string;
  model?: string;
  customer?: string;
  searchQuery?: string;
}

export interface FilterOptions {
  suppliers: string[];
  families: string[];
  themes: string[];
  models: string[];
  customers: string[];
}
