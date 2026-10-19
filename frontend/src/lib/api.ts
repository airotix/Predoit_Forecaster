import {
    ArticleData,
    LegacySeason,
    FilterState,
    CustomersResponse,
    CustomersV2Response,
    CustomerDetailV2Response,
    CustomerDetailLegacy,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

function buildQueryString(params: Record<string, string | null | undefined>): string {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") {
            search.set(k, String(v));
        }
    });
    const qs = search.toString();
    return qs ? `?${qs}` : "";
}

export const fetchArticles = async (
    season: LegacySeason,
    filters: FilterState
): Promise<ArticleData[]> => {
    const params: Record<string, string | null | undefined> = {
        season,
        supplier: filters.supplier || undefined,
        family: filters.family || undefined,
        theme: filters.theme || undefined,
        model: filters.model || undefined,
        customer: filters.customer || undefined,
        searchQuery: filters.searchQuery || undefined,
    };
    const url = `${API_BASE}/articles${buildQueryString(params)}`;
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Failed to fetch articles: ${res.status}`);
    }
    return res.json();
};

export const fetchFilterOptions = async (season: LegacySeason) => {
    const url = `${API_BASE}/filter-options?season=${encodeURIComponent(season)}`;
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Failed to fetch filter options: ${res.status}`);
    }
    return res.json();
};

export const fetchCustomers = async (): Promise<CustomersResponse> => {
    const url = `${API_BASE}/customers`;
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Failed to fetch customers: ${res.status}`);
    }
    return res.json();
};

export const fetchCustomersV2 = async (): Promise<CustomersV2Response> => {
    const url = `${API_BASE}/customers`;
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Failed to fetch customers: ${res.status}`);
    }
    return res.json();
};

export const fetchCustomerDetailV2 = async (
    customer: string,
    season?: string
): Promise<CustomerDetailV2Response> => {
    const params = new URLSearchParams();
    params.set("customer", customer);
    if (season && season !== "All") {
        params.set("season", season);
    }
    const url = `${API_BASE}/customer-detail?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Failed to fetch customer detail: ${res.status}`);
    }
    return res.json();
};

export const fetchCustomerDetail = async (
    customer: string,
    season: LegacySeason | "All"
): Promise<CustomerDetailLegacy> => {
    const params = new URLSearchParams();
    params.set("customer", customer);
    if (season) {
        params.set("season", season);
    }
    const url = `${API_BASE}/customer-detail?${params.toString()}`;
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Failed to fetch customer detail: ${res.status}`);
    }
    return res.json();
};
