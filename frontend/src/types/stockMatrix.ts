export type SizeLabel = 'XS' | 'S' | 'M' | 'L' | 'XL' | 'XL2' | 'XL3' | 'XL4' | 'XL5' | 'XL6' | 'XL7';

export const SIZE_COLUMNS: SizeLabel[] = ['XS', 'S', 'M', 'L', 'XL', 'XL2', 'XL3', 'XL4', 'XL5', 'XL6', 'XL7'];

export interface SizeData {
  [key: string]: number | null;
}

export interface ColorStockData {
  color: string;
  totalDeProduit: SizeData;
  recommendedQty: SizeData;
  totalDeFournisseur: SizeData;
  totalDeCitNegoce: SizeData;
  totalDeLeStock: SizeData;
  availableStock?: SizeData;
}

export interface StockSummary {
  stockReel: number | null;
  fournisseur: number | null;
  clientNegoce: number | null;
  total: number | null;
}

export interface ProductInfo {
  reference: string;
  name: string;
  matiere: string;
  theme: string;
  famille: string;
  sousFamille: string;
  rayon: string;
  saison: string;
}

export interface DetailedStockReport {
  productInfo: ProductInfo;
  stockSummary: StockSummary;
  colorData: ColorStockData[];
  totalQuantity: number;
}

export interface SKUDetailedProjection {
  warehouseStock?: WarehouseStockSnapshot | null;
  projectionBasis?: 'season_bookings' | 'legacy_open_balances';
  scenario?: string;
  skuId: string;
  skuName: string;
  category: string;
  productInfo: ProductInfo;
  stockSummary: StockSummary;
  colorVariants: ColorStockData[];
  confidence: 'high' | 'medium' | 'low';
}

export interface JoolanStockColor {
 color:string;stock:SizeData;toReceive:SizeData;clients:SizeData;
 allocated:SizeData;theoretical:SizeData;available:SizeData;
}
export interface WarehouseStockSnapshot {
 sourceRun:string;source:string;snapshotAt:string|null;warehouses:string[];
 colors:JoolanStockColor[];totalVariants:number;completeVariants:number;missingVariants:number;
 summary:Record<Exclude<keyof JoolanStockColor,'color'>,number|null>;
 recordedSummary:Record<Exclude<keyof JoolanStockColor,'color'>,number|null>;
}
