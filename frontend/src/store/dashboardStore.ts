import { create } from "zustand";
import {
    LegacySeason,
    FilterState,
    FilterOptions,
    ArticleData,
    KPIData,
    BudgetData,
} from "@/types";
import { fetchArticles, fetchFilterOptions } from "@/lib/api";

type Season = LegacySeason;

const EMPTY_FILTER_OPTIONS: FilterOptions = {
    seasons: ["All"],
    suppliers: ["All"],
    families: ["All"],
    themes: ["All"],
    models: ["All"],
    customers: ["All"],
};

/** Incremented on each loadData() start; used to ignore stale responses. */
let _loadId = 0;

interface DashboardState {
    season: Season;
    filters: FilterState;
    articles: ArticleData[];
    selectedArticleId: string | null;
    isLoading: boolean;
    error: string | null;
    filterOptions: FilterOptions | null;

    // Actions
    setSeason: (season: Season) => void;
    setFilter: (key: keyof FilterState, value: string | null) => void;
    setSearchQuery: (query: string) => void;
    setSelectedArticleId: (id: string | null) => void;
    loadData: () => Promise<void>;
    loadFilterOptions: (season: Season) => Promise<void>;

    // Computed (will be updated on data load)
    kpiData: KPIData | null;
    budgetData: BudgetData | null;
}

const defaultFilters: FilterState = {
    supplier: "All",
    family: "All",
    theme: "All",
    model: "All",
    customer: "All",
    searchQuery: "",
};

const calculateKPIs = (articles: ArticleData[]): KPIData => {
    let riskCount = 0;
    let totalQty = 0;
    let totalCost = 0;

    articles.forEach((article) => {
        let hasRisk = false;
        Object.values(article.matrix).forEach((sizes) => {
            Object.values(sizes).forEach((cell) => {
                totalQty += cell.forecast;
                // Cost is forecast * unit cost
                totalCost += cell.forecast * article.cost;
                if (cell.forecast > cell.stock) {
                    hasRisk = true;
                }
            });
        });
        if (hasRisk) riskCount++;
    });

    return {
        riskItems: {
            value: riskCount,
            trend: riskCount > 50 ? "up" : "down", // Dummy trend logic
            percentage: 12, // Dummy percentage
        },
        totalForecastQuantity: {
            value: totalQty,
            trend: "up",
            percentage: 5.4,
        },
        totalCost: {
            value: totalCost,
            trend: "up",
            percentage: 2.1,
        },
    };
};

export const useDashboardStore = create<DashboardState>()((set, get) => ({
    season: "All", // Default: show all articles from backend
    filters: defaultFilters,
    articles: [],
    selectedArticleId: null,
    isLoading: false,
    error: null,
    filterOptions: null,
    kpiData: null,
    budgetData: null,

    setSeason: (season) => {
        set({ season, selectedArticleId: null });
        get().loadFilterOptions(season);
        get().loadData();
    },

    loadFilterOptions: async (season) => {
        try {
            const opts = await fetchFilterOptions(season);
            set({
                filterOptions: {
                    seasons: opts.seasons ?? EMPTY_FILTER_OPTIONS.seasons,
                    suppliers: opts.suppliers ?? EMPTY_FILTER_OPTIONS.suppliers,
                    families: opts.families ?? EMPTY_FILTER_OPTIONS.families,
                    themes: opts.themes ?? EMPTY_FILTER_OPTIONS.themes,
                    models: opts.models ?? EMPTY_FILTER_OPTIONS.models,
                    customers: opts.customers ?? EMPTY_FILTER_OPTIONS.customers,
                },
            });
        } catch (err) {
            console.error("Failed to load filter options", err);
            set({ filterOptions: EMPTY_FILTER_OPTIONS });
        }
    },

    setFilter: (key, value) => {
        set((state) => ({
            filters: { ...state.filters, [key]: value },
            selectedArticleId: null,
        }));
        get().loadData();
    },

    setSearchQuery: (query) => {
        set((state) => ({
            filters: { ...state.filters, searchQuery: query },
            selectedArticleId: null,
        }));
        get().loadData();
    },

    setSelectedArticleId: (id) => {
        set({ selectedArticleId: id });
    },

    loadData: async () => {
        const { season, filters } = get();
        const loadId = ++_loadId;
        set({ isLoading: true, error: null });

        try {
            const articles = await fetchArticles(season, filters);

            // Ignore if a newer load was started (e.g. user searched and initial load returned later)
            if (loadId !== _loadId) return;

            const kpis = calculateKPIs(articles);

            // Calculate dummy budget based on total cost
            const totalCost = kpis.totalCost.value;
            const budget = {
                seasonBudget: totalCost * 0.9, // Budget defaults to 90% of spend to trigger some warnings
                forecastSpend: totalCost,
            };

            set({
                articles,
                kpiData: kpis,
                budgetData: budget,
                isLoading: false,
                error: null,
                selectedArticleId: articles.length > 0 ? articles[0].id : null,
            });
        } catch (error) {
            if (loadId !== _loadId) return;
            console.error("Failed to load data", error);
            const message = error instanceof Error ? error.message : "Failed to load data";
            set({ isLoading: false, error: message });
        }
    },
}));
