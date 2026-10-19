import { create } from 'zustand';
import {
  Customer,
  CustomerCluster,
  CustomerCoverageStats,
  CustomerProjection,
  CustomerTypology,
  VisitedStatus,
} from '@/types';

interface CustomersState {
  customers: Customer[];
  clusters: CustomerCluster[];
  coverageStats: CustomerCoverageStats | null;
  projections: CustomerProjection[];
  selectedCustomerId: string | null;
  filters: {
    visitedStatus: VisitedStatus | 'all';
    typology: CustomerTypology[];
    region: string[];
    search: string;
  };
  isLoading: boolean;
  error: string | null;

  // Actions
  setCustomers: (customers: Customer[]) => void;
  setClusters: (clusters: CustomerCluster[]) => void;
  setCoverageStats: (stats: CustomerCoverageStats) => void;
  setProjections: (projections: CustomerProjection[]) => void;
  setSelectedCustomer: (customerId: string | null) => void;
  toggleVisitedStatus: (customerId: string) => void;
  
  // Filter actions
  setFilter: <K extends keyof CustomersState['filters']>(
    key: K,
    value: CustomersState['filters'][K]
  ) => void;
  clearFilters: () => void;
  
  // Computed
  getFilteredCustomers: () => Customer[];
  getCustomerById: (customerId: string) => Customer | undefined;
  getProjectionForCustomer: (customerId: string) => CustomerProjection | undefined;
  getVisitedCount: () => number;
  getNotVisitedCount: () => number;
  
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

const defaultFilters = {
  visitedStatus: 'all' as const,
  typology: [],
  region: [],
  search: '',
};

export const useCustomersStore = create<CustomersState>()((set, get) => ({
  customers: [],
  clusters: [],
  coverageStats: null,
  projections: [],
  selectedCustomerId: null,
  filters: defaultFilters,
  isLoading: false,
  error: null,

  setCustomers: (customers) => {
    const visited = customers.filter((c) => c.status === 'visited').length;
    const total = customers.length;
    set({
      customers,
      coverageStats: {
        total,
        visited,
        notVisited: total - visited,
        visitedPercent: total > 0 ? Math.round((visited / total) * 100) : 0,
      },
    });
  },

  setClusters: (clusters) => set({ clusters }),

  setCoverageStats: (stats) => set({ coverageStats: stats }),

  setProjections: (projections) => set({ projections }),

  setSelectedCustomer: (customerId) => set({ selectedCustomerId: customerId }),

  toggleVisitedStatus: (customerId) =>
    set((state) => {
      const customers = state.customers.map((c) =>
        c.id === customerId
          ? { ...c, status: c.status === 'visited' ? 'not_visited' : 'visited' as VisitedStatus }
          : c
      );
      const visited = customers.filter((c) => c.status === 'visited').length;
      const total = customers.length;
      return {
        customers,
        coverageStats: {
          total,
          visited,
          notVisited: total - visited,
          visitedPercent: total > 0 ? Math.round((visited / total) * 100) : 0,
        },
      };
    }),

  setFilter: (key, value) =>
    set((state) => ({
      filters: { ...state.filters, [key]: value },
    })),

  clearFilters: () => set({ filters: defaultFilters }),

  getFilteredCustomers: () => {
    const { customers, filters } = get();
    return customers.filter((c) => {
      if (filters.visitedStatus !== 'all' && c.status !== filters.visitedStatus) {
        return false;
      }
      if (filters.typology.length > 0 && !filters.typology.includes(c.typology)) {
        return false;
      }
      if (filters.region.length > 0 && !filters.region.includes(c.region)) {
        return false;
      }
      if (filters.search) {
        const search = filters.search.toLowerCase();
        if (
          !c.id.toLowerCase().includes(search) &&
          !c.name.toLowerCase().includes(search)
        ) {
          return false;
        }
      }
      return true;
    });
  },

  getCustomerById: (customerId) => get().customers.find((c) => c.id === customerId),

  getProjectionForCustomer: (customerId) =>
    get().projections.find((p) => p.customerId === customerId),

  getVisitedCount: () => get().customers.filter((c) => c.status === 'visited').length,

  getNotVisitedCount: () => get().customers.filter((c) => c.status === 'not_visited').length,

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),
}));
