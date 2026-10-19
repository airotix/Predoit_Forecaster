import { create } from 'zustand';
import {
  SKU,
  SKUKPI,
  SKUProjection,
  SKURecommendation,
  SizeRecommendation,
  RecommendationStatus,
} from '@/types';

interface SKUOverride {
  totalQty: number;
  sizes: SizeRecommendation[];
  locked: boolean;
  notes?: string;
  reason?: string;
  timestamp: string;
  user: string;
}

interface ProductsState {
  skus: SKU[];
  kpis: Record<string, SKUKPI>;
  projections: SKUProjection[];
  recommendations: SKURecommendation[];
  overrides: Record<string, SKUOverride>;
  selectedSKUId: string | null;
  filters: {
    category: string[];
    status: RecommendationStatus[];
    confidence: string[];
    marginStatus: 'all' | 'below_target' | 'on_target';
    search: string;
  };
  isLoading: boolean;
  error: string | null;

  // Actions
  setSKUs: (skus: SKU[]) => void;
  setKPIs: (kpis: Record<string, SKUKPI>) => void;
  setProjections: (projections: SKUProjection[]) => void;
  setRecommendations: (recommendations: SKURecommendation[]) => void;
  setSelectedSKU: (skuId: string | null) => void;
  
  // Override actions
  updateOverride: (skuId: string, override: Partial<SKUOverride>) => void;
  lockSKU: (skuId: string, user: string) => void;
  unlockSKU: (skuId: string) => void;
  resetToAIRecommendation: (skuId: string) => void;
  
  // Size actions
  updateSizeOverride: (skuId: string, size: string, qty: number) => void;
  applySizeRules: (skuId: string, rules: SizeRecommendation[]) => void;
  
  // Filter actions
  setFilter: <K extends keyof ProductsState['filters']>(
    key: K,
    value: ProductsState['filters'][K]
  ) => void;
  clearFilters: () => void;
  
  // Computed
  getFilteredRecommendations: () => SKURecommendation[];
  getSKUById: (skuId: string) => SKU | undefined;
  getRecommendationById: (skuId: string) => SKURecommendation | undefined;
  getProjectionById: (skuId: string) => SKUProjection | undefined;
  
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

const defaultFilters = {
  category: [],
  status: [],
  confidence: [],
  marginStatus: 'all' as const,
  search: '',
};

export const useProductsStore = create<ProductsState>()((set, get) => ({
  skus: [],
  kpis: {},
  projections: [],
  recommendations: [],
  overrides: {},
  selectedSKUId: null,
  filters: defaultFilters,
  isLoading: false,
  error: null,

  setSKUs: (skus) => set({ skus }),

  setKPIs: (kpis) => set({ kpis }),

  setProjections: (projections) => set({ projections }),

  setRecommendations: (recommendations) => set({ recommendations }),

  setSelectedSKU: (skuId) => set({ selectedSKUId: skuId }),

  updateOverride: (skuId, override) =>
    set((state) => ({
      overrides: {
        ...state.overrides,
        [skuId]: {
          ...state.overrides[skuId],
          ...override,
          timestamp: new Date().toISOString(),
        },
      },
      recommendations: state.recommendations.map((r) =>
        r.skuId === skuId ? { ...r, status: 'adjusted' as RecommendationStatus } : r
      ),
    })),

  lockSKU: (skuId, user) =>
    set((state) => ({
      overrides: {
        ...state.overrides,
        [skuId]: {
          ...state.overrides[skuId],
          locked: true,
          timestamp: new Date().toISOString(),
          user,
        },
      },
      recommendations: state.recommendations.map((r) =>
        r.skuId === skuId ? { ...r, locked: true, status: 'locked' as RecommendationStatus } : r
      ),
    })),

  unlockSKU: (skuId) =>
    set((state) => ({
      overrides: {
        ...state.overrides,
        [skuId]: {
          ...state.overrides[skuId],
          locked: false,
          timestamp: new Date().toISOString(),
        },
      },
      recommendations: state.recommendations.map((r) =>
        r.skuId === skuId ? { ...r, locked: false, status: 'adjusted' as RecommendationStatus } : r
      ),
    })),

  resetToAIRecommendation: (skuId) =>
    set((state) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [skuId]: _removed, ...remainingOverrides } = state.overrides;
      return {
        overrides: remainingOverrides,
        recommendations: state.recommendations.map((r) =>
          r.skuId === skuId ? { ...r, status: 'pending' as RecommendationStatus, locked: false } : r
        ),
      };
    }),

  updateSizeOverride: (skuId, size, qty) =>
    set((state) => {
      const recommendation = state.recommendations.find((r) => r.skuId === skuId);
      if (!recommendation) return state;

      const currentOverride = state.overrides[skuId];
      const sizes = currentOverride?.sizes || recommendation.sizeBreakdown;

      return {
        overrides: {
          ...state.overrides,
          [skuId]: {
            ...currentOverride,
            sizes: sizes.map((s) =>
              s.size === size
                ? { ...s, manualOverride: qty, finalQty: qty }
                : s
            ),
            timestamp: new Date().toISOString(),
            totalQty: sizes.reduce(
              (sum, s) => sum + (s.size === size ? qty : s.finalQty),
              0
            ),
          },
        },
        recommendations: state.recommendations.map((r) =>
          r.skuId === skuId ? { ...r, status: 'adjusted' as RecommendationStatus } : r
        ),
      };
    }),

  applySizeRules: (skuId, rules) =>
    set((state) => ({
      overrides: {
        ...state.overrides,
        [skuId]: {
          ...state.overrides[skuId],
          sizes: rules,
          totalQty: rules.reduce((sum, r) => sum + r.finalQty, 0),
          timestamp: new Date().toISOString(),
        },
      },
    })),

  setFilter: (key, value) =>
    set((state) => ({
      filters: { ...state.filters, [key]: value },
    })),

  clearFilters: () => set({ filters: defaultFilters }),

  getFilteredRecommendations: () => {
    const { recommendations, filters } = get();
    return recommendations.filter((r) => {
      if (filters.category.length > 0 && !filters.category.includes(r.category)) {
        return false;
      }
      if (filters.status.length > 0 && !filters.status.includes(r.status)) {
        return false;
      }
      if (filters.confidence.length > 0 && !filters.confidence.includes(r.confidence)) {
        return false;
      }
      if (filters.search) {
        const search = filters.search.toLowerCase();
        if (
          !r.skuId.toLowerCase().includes(search) &&
          !r.skuName.toLowerCase().includes(search)
        ) {
          return false;
        }
      }
      return true;
    });
  },

  getSKUById: (skuId) => get().skus.find((s) => s.id === skuId),

  getRecommendationById: (skuId) => get().recommendations.find((r) => r.skuId === skuId),

  getProjectionById: (skuId) => get().projections.find((p) => p.skuId === skuId),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),
}));
