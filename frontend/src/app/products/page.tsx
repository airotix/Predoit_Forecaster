"use client";
// @refresh reset

import React, { useEffect, useState, useCallback, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { ConfidenceBadge } from "@/components/shared";
import { BrandButton } from "@/components/ui/brand-button";
import { Notice, PageHeader, SelectField, TextField } from "@/components/ui/brand";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  ArrowRightIcon,
  ArrowsDownUpIcon,
  CaretDownIcon,
  ClockCounterClockwiseIcon,
  MagnifyingGlassIcon,
  SortAscendingIcon,
  SortDescendingIcon,
} from "@phosphor-icons/react";
import { ProductStatus, ConfidenceLevel } from "@/types";
import { fetchProducts, type ProductRow } from "@/lib/api/forecast";
import { useSeasonStore } from "@/store/seasonStore";
import { useDataRefresh } from "@/hooks/useDataRefresh";
import RecentSizeHistory from '@/components/products/RecentSizeHistory';

interface ProductKPIRow extends Omit<ProductRow,'status'|'aiConfidence'> {
  name: string;
  category: string;
  status: ProductStatus;
  season: string;
  aiConfidence: ConfidenceLevel;
}

const statusColors: Record<ProductStatus, string> = {
  new: "bg-plum-50 text-plum-600",
  "carry-over": "bg-brand-50 text-brand-800",
  core: "bg-success-50 text-success-600",
};

type SortField = "diffusionRate" | "reorderRate" | "totalUnitsSold" | "depthPerCustomer";

const TH = "px-3.5 py-3 text-[11px] font-bold uppercase tracking-[0.1em] text-fg-3";

function StatusPill({ status, className }: { status: ProductStatus; className?: string }) {
  return (
    <span className={cn("inline-flex whitespace-nowrap rounded-full px-2.5 py-[3px] text-xs font-bold", statusColors[status], className)}>
      {status}
    </span>
  );
}

function MetricTile({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[18px] bg-soft px-[18px] py-4">
      <p className="text-[13px] text-fg-3">{label}</p>
      <p className="font-display text-[26px] font-bold tabular-nums">{value}</p>
    </div>
  );
}

export default function ProductKPIsPage() {
  const [products, setProducts] = useState<ProductKPIRow[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<SortField>("diffusionRate");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedProduct, setSelectedProduct] = useState<ProductKPIRow | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error,setError]=useState('');
  const [page,setPage]=useState(0);
  const request=useRef({version:0});
  const {activeSeason}=useSeasonStore();
  const units=(value:number|null)=>value==null?'—':value.toLocaleString('en-GB',{maximumFractionDigits:1});
  const rate=(value:number|null)=>value==null?'—':`${(value*100).toFixed(1)}%`;

  const loadProducts = useCallback(async () => {
    // Older development renders used a numeric ref; migrate preserved state safely.
    if(typeof request.current!=='object'||request.current===null||!Number.isFinite(request.current.version)){
      request.current={version:0};
    }
    const version=++request.current.version;
    setIsLoading(true);
    setError('');
    try {
      const data = await fetchProducts();
      if(version!==request.current.version)return;
      const mapped: ProductKPIRow[] = data.map((p) => ({
        ...p,
        skuId: p.skuId,
        name: p.name,
        category: p.category,
        status: (p.status || "core") as ProductStatus,
        season: p.season || "",
        diffusionRate: p.diffusionRate,
        depthPerCustomer: p.depthPerCustomer,
        reorderRate: p.reorderRate,
        totalUnitsSold: p.totalUnitsSold,
        buyingCustomers: p.buyingCustomers,
        sizeBreakdown: p.sizeBreakdown,
        aiConfidence: (p.aiConfidence || "medium") as ConfidenceLevel,
      }));
      setProducts(mapped);
      setPage(0);
      setSelectedProduct(previous=>mapped.find(p=>p.skuId===previous?.skuId)||null);
    } catch (err) {
      if(version===request.current.version){setProducts([]);setSelectedProduct(null);setError(err instanceof Error?err.message:'Could not load product KPIs.');}
    } finally {
      if(version===request.current.version)setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const token=request.current;
    loadProducts();
    return ()=>{token.version++;};
  }, [loadProducts,activeSeason?.id]);
  useEffect(()=>setPage(0),[searchQuery,categoryFilter,statusFilter,sortBy,sortOrder]);

  useDataRefresh(loadProducts);

  const filteredProducts = products
    .filter((p) => {
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        if (!p.skuId.toLowerCase().includes(q) && !p.name.toLowerCase().includes(q)) {
          return false;
        }
      }
      if (categoryFilter !== "all" && p.category !== categoryFilter) return false;
      if (statusFilter !== "all" && p.status !== statusFilter) return false;
      return true;
    })
    .sort((a, b) => {
      const multiplier = sortOrder === "desc" ? -1 : 1;
      const left=a[sortBy],right=b[sortBy];
      if(left==null)return right==null?0:1;
      if(right==null)return -1;
      return (left-right) * multiplier;
    });

  const categories = [...new Set(products.map((p) => p.category))];

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };

  const SortableHeader = ({ field, label }: { field: SortField; label: string }) => {
    const active = sortBy === field;
    const SortIcon = !active ? ArrowsDownUpIcon : sortOrder === "desc" ? SortDescendingIcon : SortAscendingIcon;
    return (
      <button
        type="button"
        onClick={() => handleSort(field)}
        className={cn(
          "ml-auto flex items-center gap-1 text-[11px] font-bold uppercase tracking-[0.1em] transition-colors hover:text-fg-1",
          active ? "text-brand-700" : "text-fg-3"
        )}
      >
        {label}
        <SortIcon weight={active ? "bold" : "regular"} className="h-3 w-3" />
      </button>
    );
  };

  return (
    <AppShell>
      <PageHeader
        eyebrow="Insights"
        title="Product KPI Explorer"
        description="Recorded customer-order demand by article and colour, with published base forecasts shown separately."
      />
      {products.length>0&&(
        <div className="flex items-start gap-3.5 rounded-[20px] border border-line bg-card px-5 py-[18px]">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-plum-50"><ClockCounterClockwiseIcon className="h-[19px] w-[19px] text-plum-600"/></span>
          <div className="flex min-w-0 flex-col gap-1.5 text-sm leading-relaxed text-fg-2">
            <p className="font-semibold text-fg-1">History: {products[0].historyStart||'unknown'} to {products[0].historyEnd||'unknown'}{products[0].ordersThrough?` · Joolan orders through ${products[0].ordersThrough}`:''}. Forecast: {products[0].forecastStart||'unknown'} to {products[0].forecastEnd||'unknown'}.</p>
            <p className="text-pretty">{products[0].demandDefinition} Model training cutoff: {products[0].trainingCutoff||'unknown'}. KPI history includes recorded orders after that cutoff.</p>
            <details className="group">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 self-start text-[13px] font-bold text-brand-700 [&::-webkit-details-marker]:hidden">How these KPIs work<CaretDownIcon weight="bold" className="h-3 w-3 transition-transform group-open:rotate-180"/></summary>
              <p className="mt-2 text-pretty text-[13px] leading-[1.65]">Diffusion = customers buying this article/colour ÷ all customers in the published source history. Depth = historical booked demand ÷ buying customers. Reorder: {products[0].reorderDefinition} Multiple sizes or duplicate lines in one order count once. Repeat-order rate in the detail panel also includes repeat orders within one season. Missing order IDs or dates leave rates unavailable. These are history-wide metrics. Model confidence is a model signal, not measured forecast accuracy.</p>
            </details>
          </div>
        </div>
      )}
      {error&&<Notice tone="danger"><div className="flex flex-wrap items-center gap-3">{error}<BrandButton variant="outline" size="sm" onClick={()=>void loadProducts()}>Retry</BrandButton></div></Notice>}

      <section className="overflow-hidden rounded-3xl border border-line bg-card shadow-card">
        {/* Filters */}
        <div className="flex flex-wrap gap-2.5 border-b border-line px-5 py-[18px]">
          <div className="relative flex flex-[1_1_260px] items-center">
            <MagnifyingGlassIcon className="absolute left-3.5 h-4 w-4 text-fg-3" />
            <TextField
              aria-label="Search products"
              placeholder="Search by SKU or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10"
            />
          </div>
          <SelectField aria-label="Category" className="min-w-[160px]" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option value="all">All Categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </SelectField>
          <SelectField aria-label="Status" className="min-w-[160px]" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All Status</option>
            <option value="new">New</option>
            <option value="carry-over">Carry-over</option>
            <option value="core">Core</option>
          </SelectField>
          <SelectField aria-label="Sort by" className="min-w-[160px]" value={sortBy} onChange={(e) => setSortBy(e.target.value as SortField)}>
            <option value="diffusionRate">Diffusion Rate</option>
            <option value="reorderRate">Reorder Rate</option>
            <option value="totalUnitsSold">Booked demand</option>
            <option value="depthPerCustomer">Depth/Customer</option>
          </SelectField>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="flex flex-col gap-3 p-6">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-14 animate-pulse rounded-xl bg-soft" />
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1180px] text-sm">
              <thead>
                <tr className="border-b border-line bg-page">
                  <th className={cn(TH, "pl-6 text-left")}>SKU</th>
                  <th className={cn(TH, "text-left")}>Status</th>
                  <th className={cn(TH, "text-right")}>
                    <SortableHeader field="diffusionRate" label="Diffusion" />
                  </th>
                  <th className={cn(TH, "text-right")}>
                    <SortableHeader field="depthPerCustomer" label="Depth/Cust" />
                  </th>
                  <th className={cn(TH, "text-right")}>
                    <SortableHeader field="reorderRate" label="Reorder" />
                  </th>
                  <th className={cn(TH, "text-right")}>
                    <SortableHeader field="totalUnitsSold" label="Booked demand" />
                  </th>
                  <th className={cn(TH, "text-right")}>Base forecast</th>
                  <th className={cn(TH, "text-center")}>Customers</th>
                  <th className={cn(TH, "max-w-[240px] text-left")}>Style name</th>
                  <th className={cn(TH, "pr-6 text-center")}>Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filteredProducts.slice(page*50,(page+1)*50).map((product) => (
                  <tr
                    key={product.skuId}
                    className="cursor-pointer transition-colors hover:bg-page focus-visible:bg-page focus-visible:outline-none"
                    onClick={() => setSelectedProduct(product)}
                    tabIndex={0}
                    onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelectedProduct(product);}}}
                  >
                    <td className="py-[13px] pl-6 pr-3.5">
                      <div className="flex flex-col gap-0.5">
                        <p className="font-mono text-[13px] font-bold">{product.skuId.split('|')[0]}</p>
                        <p className="text-xs text-fg-2">{product.skuId.split('|')[1]}</p>
                        <p className="text-xs text-fg-3">{product.category}</p>
                      </div>
                    </td>
                    <td className="px-3.5 py-[13px]">
                      <StatusPill status={product.status} />
                    </td>
                    <td className="px-3.5 py-[13px]">
                      <div className="flex items-center justify-end gap-2.5">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-soft">
                          <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, Math.max(0, product.diffusionRate * 100))}%` }} />
                        </div>
                        <span className="w-11 text-right font-mono text-[13px] font-bold tabular-nums">
                          {(product.diffusionRate * 100).toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-3.5 py-[13px] text-right font-mono text-[13px] font-bold tabular-nums">
                      {product.depthPerCustomer.toFixed(1)}
                    </td>
                    <td className="px-3.5 py-[13px] text-right font-mono text-[13px] font-bold tabular-nums">
                      {rate(product.reorderRate)}
                    </td>
                    <td className="px-3.5 py-[13px] text-right font-mono text-[13px] font-bold tabular-nums">
                      {units(product.historicalDemand)}
                    </td>
                    <td className="px-3.5 py-[13px] text-right font-mono text-[13px] font-bold tabular-nums text-plum-600">{units(product.forecastUnits)}</td>
                    <td className="px-3.5 py-[13px] text-center">
                      <span className="inline-block min-w-8 rounded-full border border-line px-[9px] py-[3px] text-center font-mono text-xs font-semibold">
                        {product.buyingCustomers}
                      </span>
                    </td>
                    <td
                      className="max-w-[280px] px-3.5 py-[13px] text-fg-2"
                      title={product.name}
                    >
                      <p className="line-clamp-2 text-[13px]">{product.name}</p>
                    </td>
                    <td className="py-[13px] pl-3.5 pr-6">
                      <div className="flex justify-center">
                        <ConfidenceBadge level={product.aiConfidence} />
                      </div>
                    </td>
                  </tr>
                ))}
                {!filteredProducts.length&&<tr><td colSpan={10} className="p-10 text-center text-sm text-fg-3">{error?'Product KPIs could not be loaded. Retry above.':products.length?'No articles match your filters.':'No published product KPIs are available. Run a forecast in Setup.'}</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {!isLoading&&!error&&(
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <p className="text-fg-2"><strong className="text-fg-1">{filteredProducts.length}</strong> article/colour combinations · Page {page+1} of {Math.max(1,Math.ceil(filteredProducts.length/50))}</p>
          <div className="flex gap-2">
            <BrandButton variant="outline" disabled={!page} onClick={()=>setPage(p=>p-1)}>Previous</BrandButton>
            <BrandButton variant="outline" disabled={(page+1)*50>=filteredProducts.length} onClick={()=>setPage(p=>p+1)}>Next</BrandButton>
          </div>
        </div>
      )}

      {/* Product Detail Sheet */}
      <Sheet open={!!selectedProduct} onOpenChange={() => setSelectedProduct(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto border-line bg-card p-0 sm:max-w-[540px]">
          {selectedProduct && (
            <>
              <SheetHeader className="sticky top-0 z-[1] gap-1.5 space-y-0 border-b border-line bg-card px-7 py-6 pr-14 text-left">
                <SheetTitle className="break-all font-mono text-lg font-bold">{selectedProduct.skuId}</SheetTitle>
                <SheetDescription className="text-sm text-fg-3">
                  {selectedProduct.name} • {selectedProduct.category}
                </SheetDescription>
              </SheetHeader>
              <div className="flex flex-col gap-5 px-7 pb-8 pt-6">
                <div className="flex items-center gap-2">
                  <StatusPill status={selectedProduct.status} className="px-3 py-1" />
                  <ConfidenceBadge level={selectedProduct.aiConfidence} />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <MetricTile label="Diffusion Rate" value={`${(selectedProduct.diffusionRate * 100).toFixed(1)}%`} />
                  <MetricTile label="Depth/Customer" value={selectedProduct.depthPerCustomer.toFixed(1)} />
                  <MetricTile label="Reorder Rate" value={rate(selectedProduct.reorderRate)} />
                  <MetricTile label="Historical booked demand" value={units(selectedProduct.historicalDemand)} />
                </div>

                <section className="rounded-[18px] border border-line px-5 py-[18px] text-sm leading-relaxed"><p className="font-bold">Repeat buying from dated orders</p><p className="mt-2">Across seasons: {selectedProduct.reorderCustomers} of {selectedProduct.reorderBuyingCustomers} buyers · {rate(selectedProduct.reorderRate)}</p><p className="mt-1">Two or more distinct orders, including within one season: {selectedProduct.repeatOrderCustomers} buyers · {rate(selectedProduct.repeatOrderRate)}</p><p className="mt-2 text-xs text-fg-3">April–September / October–March. Each article/colour on an order is counted once across all sizes.</p>{selectedProduct.reorderMissingLines>0&&<p className="mt-2 text-xs text-brand-800">{selectedProduct.reorderMissingLines} positive-demand lines have missing or inconsistent order IDs or dates. Rates remain unavailable.</p>}</section>

                <RecentSizeHistory product={selectedProduct}/>

                <MetricTile label="Buying Customers" value={selectedProduct.buyingCustomers} />

                <BrandButton asChild size="lg" className="w-full">
                  <Link href={`/recommendations?sku=${encodeURIComponent(selectedProduct.skuId)}`}>
                    View Recommendation
                    <ArrowRightIcon />
                  </Link>
                </BrandButton>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </AppShell>
  );
}
