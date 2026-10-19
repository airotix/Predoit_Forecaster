"use client";
// @refresh reset

import React, { useEffect, useState, useCallback, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { ConfidenceBadge } from "@/components/shared";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import Link from "next/link";
import {
  Search,
  ArrowUpDown,
  ArrowRight,
} from "lucide-react";
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
  new: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  "carry-over": "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  core: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
};

type SortField = "diffusionRate" | "reorderRate" | "totalUnitsSold" | "depthPerCustomer";

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

  const SortableHeader = ({ field, label }: { field: SortField; label: string }) => (
    <button
      onClick={() => handleSort(field)}
      className={cn(
        "flex items-center gap-1 text-xs font-medium uppercase tracking-wide hover:text-slate-900 dark:hover:text-slate-100 transition-colors",
        sortBy === field ? "text-blue-600 dark:text-blue-400" : "text-slate-500"
      )}
    >
      {label}
      <ArrowUpDown className="h-3 w-3" />
    </button>
  );

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Product KPI Explorer</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">
            Recorded customer-order demand by article and colour, with published base forecasts shown separately.
          </p>
        </div>
        {products.length>0&&<div className="rounded-lg border bg-slate-50 p-4 text-sm text-slate-600"><p>History: {products[0].historyStart||'unknown'} to {products[0].historyEnd||'unknown'}{products[0].ordersThrough?` · Joolan orders through ${products[0].ordersThrough}`:''}. Forecast: {products[0].forecastStart||'unknown'} to {products[0].forecastEnd||'unknown'}.</p><p className="mt-2">{products[0].demandDefinition} Model training cutoff: {products[0].trainingCutoff||'unknown'}. KPI history includes recorded orders after that cutoff.</p><details className="mt-2"><summary className="cursor-pointer font-medium">How these KPIs work</summary><p className="mt-2">Diffusion = customers buying this article/colour ÷ all customers in the published source history. Depth = historical booked demand ÷ buying customers. Reorder: {products[0].reorderDefinition} Multiple sizes or duplicate lines in one order count once. Repeat-order rate in the detail panel also includes repeat orders within one season. Missing order IDs or dates leave rates unavailable. These are history-wide metrics. Model confidence is a model signal, not measured forecast accuracy.</p></details></div>}
        {error&&<div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}<Button variant="outline" className="ml-3" onClick={()=>void loadProducts()}>Retry</Button></div>}

        {/* Filters */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-4">
              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <Input
                  placeholder="Search by SKU or name..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="Category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  {categories.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="carry-over">Carry-over</SelectItem>
                  <SelectItem value="core">Core</SelectItem>
                </SelectContent>
              </Select>
              <Select value={sortBy} onValueChange={(v) => setSortBy(v as SortField)}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="diffusionRate">Diffusion Rate</SelectItem>
                  <SelectItem value="reorderRate">Reorder Rate</SelectItem>
                  <SelectItem value="totalUnitsSold">Booked demand</SelectItem>
                  <SelectItem value="depthPerCustomer">Depth/Customer</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-14 bg-slate-100 dark:bg-slate-800 rounded animate-pulse"
                  />
                ))}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
                      <th className="px-4 py-3 text-left font-medium text-slate-500">SKU</th>
                      <th className="px-4 py-3 text-left font-medium text-slate-500">Status</th>
                      <th className="px-4 py-3 text-right">
                        <SortableHeader field="diffusionRate" label="Diffusion" />
                      </th>
                      <th className="px-4 py-3 text-right">
                        <SortableHeader field="depthPerCustomer" label="Depth/Cust" />
                      </th>
                      <th className="px-4 py-3 text-right">
                        <SortableHeader field="reorderRate" label="Reorder" />
                      </th>
                      <th className="px-4 py-3 text-right">
                        <SortableHeader field="totalUnitsSold" label="Booked demand" />
                      </th>
                      <th className="px-4 py-3 text-right font-medium text-slate-500">Base forecast</th>
                      <th className="px-4 py-3 text-center font-medium text-slate-500">
                        Customers
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-slate-500 max-w-[240px]">
                        Style name
                      </th>
                      <th className="px-4 py-3 text-center font-medium text-slate-500">
                        Confidence
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                    {filteredProducts.slice(page*50,(page+1)*50).map((product) => (
                      <tr
                        key={product.skuId}
                        className="hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer transition-colors"
                        onClick={() => setSelectedProduct(product)}
                        tabIndex={0}
                        onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelectedProduct(product);}}}
                      >
                        <td className="px-4 py-3">
                          <div>
                            <p className="font-medium">{product.skuId.split('|')[0]}</p>
                            <p className="text-xs text-slate-500">{product.skuId.split('|')[1]}</p>
                            <p className="text-xs text-slate-500">{product.category}</p>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Badge className={cn("text-xs", statusColors[product.status])}>
                            {product.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <Progress
                              value={product.diffusionRate * 100}
                              className="w-16 h-2"
                            />
                            <span className="text-xs font-medium w-10 text-right">
                              {(product.diffusionRate * 100).toFixed(1)}%
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right font-medium">
                          {product.depthPerCustomer.toFixed(1)}
                        </td>
                        <td className="px-4 py-3 text-right font-medium">
                          {rate(product.reorderRate)}
                        </td>
                        <td className="px-4 py-3 text-right font-medium">
                          {units(product.historicalDemand)}
                        </td>
                        <td className="px-4 py-3 text-right font-medium">{units(product.forecastUnits)}</td>
                        <td className="px-4 py-3 text-center">
                          <Badge variant="outline" className="text-xs">
                            {product.buyingCustomers}
                          </Badge>
                        </td>
                        <td
                          className="px-4 py-3 text-slate-700 dark:text-slate-300 max-w-[280px]"
                          title={product.name}
                        >
                          <p className="text-sm line-clamp-2">{product.name}</p>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-center">
                            <ConfidenceBadge level={product.aiConfidence} size="sm" />
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!filteredProducts.length&&<tr><td colSpan={10} className="p-8 text-center text-slate-500">{error?'Product KPIs could not be loaded. Retry above.':products.length?'No articles match your filters.':'No published product KPIs are available. Run a forecast in Setup.'}</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
        {!isLoading&&!error&&<div className="flex items-center justify-between text-sm"><p>{filteredProducts.length} article/colour combinations · Page {page+1} of {Math.max(1,Math.ceil(filteredProducts.length/50))}</p><div className="flex gap-2"><Button variant="outline" disabled={!page} onClick={()=>setPage(p=>p-1)}>Previous</Button><Button variant="outline" disabled={(page+1)*50>=filteredProducts.length} onClick={()=>setPage(p=>p+1)}>Next</Button></div></div>}
      </div>

      {/* Product Detail Sheet */}
      <Sheet open={!!selectedProduct} onOpenChange={() => setSelectedProduct(null)}>
        <SheetContent className="sm:max-w-lg overflow-y-auto">
          {selectedProduct && (
            <>
              <SheetHeader>
                <SheetTitle>{selectedProduct.skuId}</SheetTitle>
                <SheetDescription>
                  {selectedProduct.name} • {selectedProduct.category}
                </SheetDescription>
              </SheetHeader>
              <div className="mt-6 space-y-6">
                <div className="flex items-center gap-2">
                  <Badge className={statusColors[selectedProduct.status]}>
                    {selectedProduct.status}
                  </Badge>
                  <ConfidenceBadge level={selectedProduct.aiConfidence} />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-900">
                    <p className="text-sm text-slate-500">Diffusion Rate</p>
                    <p className="text-2xl font-bold">
                      {(selectedProduct.diffusionRate * 100).toFixed(1)}%
                    </p>
                  </div>
                  <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-900">
                    <p className="text-sm text-slate-500">Depth/Customer</p>
                    <p className="text-2xl font-bold">
                      {selectedProduct.depthPerCustomer.toFixed(1)}
                    </p>
                  </div>
                  <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-900">
                    <p className="text-sm text-slate-500">Reorder Rate</p>
                    <p className="text-2xl font-bold">
                      {rate(selectedProduct.reorderRate)}
                    </p>
                  </div>
                  <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-900">
                    <p className="text-sm text-slate-500">Historical booked demand</p>
                    <p className="text-2xl font-bold">
                      {units(selectedProduct.historicalDemand)}
                    </p>
                  </div>
                </div>

                <div className="rounded-lg border p-4 text-sm"><p className="font-medium">Repeat buying from dated orders</p><p className="mt-2">Across seasons: {selectedProduct.reorderCustomers} of {selectedProduct.reorderBuyingCustomers} buyers · {rate(selectedProduct.reorderRate)}</p><p className="mt-1">Two or more distinct orders, including within one season: {selectedProduct.repeatOrderCustomers} buyers · {rate(selectedProduct.repeatOrderRate)}</p><p className="mt-2 text-xs text-slate-500">April–September / October–March. Each article/colour on an order is counted once across all sizes.</p>{selectedProduct.reorderMissingLines>0&&<p className="mt-2 text-xs text-amber-800">{selectedProduct.reorderMissingLines} positive-demand lines have missing or inconsistent order IDs or dates. Rates remain unavailable.</p>}</div>

                <RecentSizeHistory product={selectedProduct}/>

                <div className="p-4 rounded-lg bg-slate-50 dark:bg-slate-900">
                  <p className="text-sm text-slate-500">Buying Customers</p>
                  <p className="text-2xl font-bold">{selectedProduct.buyingCustomers}</p>
                </div>

                <Button asChild className="w-full">
                  <Link href={`/recommendations?sku=${encodeURIComponent(selectedProduct.skuId)}`}>
                    View Recommendation
                    <ArrowRight className="h-4 w-4 ml-2" />
                  </Link>
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </AppShell>
  );
}
