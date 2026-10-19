"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Info, UserCircle2 } from "lucide-react";
import { Customer } from "@/types";
import { fetchCustomersV2, fetchCustomerDetailV2 } from "@/lib/api";
import { PurchaseHistoryItem } from "@/types";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetTrigger,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

interface CustomerPanelState {
    customers: Customer[];
    regions: string[];
    latestSeason: string | null;
}

interface CustomerDetailState {
    customer: string;
    purchaseHistory: PurchaseHistoryItem[];
    seasons: string[];
}

export default function CustomerPanel() {
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<CustomerPanelState | null>(null);
    const [selectedCustomer, setSelectedCustomer] = useState<string | null>(null);
    const [detail, setDetail] = useState<CustomerDetailState | null>(null);
    const [detailSeason, setDetailSeason] = useState<string>("All");
    const [detailLoading, setDetailLoading] = useState(false);

    useEffect(() => {
        if (!open) return;
        if (data) return;

        setLoading(true);
        fetchCustomersV2()
            .then((res) => {
                setData({
                    customers: res.customers || [],
                    regions: res.regions || [],
                    latestSeason: res.latestSeason,
                });
            })
            .catch((err) => {
                console.error("Failed to load customers", err);
            })
            .finally(() => setLoading(false));
    }, [open, data]);

    const handleOpenDetail = (customerId: string) => {
        setSelectedCustomer(customerId);
        setDetail(null);
        setDetailSeason("All");
        loadDetail(customerId, "All");
    };

    const loadDetail = (customerId: string, season: string) => {
        setDetailLoading(true);
        fetchCustomerDetailV2(customerId, season)
            .then((res) => {
                setDetail(res);
            })
            .catch((err) => {
                console.error("Failed to load customer detail", err);
            })
            .finally(() => setDetailLoading(false));
    };

    const seasonsForDetail = useMemo(() => {
        if (!detail) return ["All"];
        return ["All", ...(detail.seasons ?? [])];
    }, [detail]);

    return (
        <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
                <Button variant="outline" className="h-10 px-3 flex items-center gap-2">
                    <UserCircle2 className="h-4 w-4" />
                    <span className="hidden sm:inline">Customers</span>
                </Button>
            </SheetTrigger>
            <SheetContent className="w-full sm:w-[640px] overflow-y-auto">
                <SheetHeader>
                    <SheetTitle>Customers overview</SheetTitle>
                    <SheetDescription>
                        See which customers have bought across seasons and inspect their ordered products.
                    </SheetDescription>
                </SheetHeader>

                <div className="py-4 space-y-4">
                    {loading && (
                        <div className="text-sm text-slate-500">Loading customers...</div>
                    )}
                    {!loading && data && data.customers.length === 0 && (
                        <div className="text-sm text-slate-500">
                            No customer information available yet.
                        </div>
                    )}

                    {!loading && data && data.customers.length > 0 && (
                        <div className="space-y-3">
                            <div className="text-xs font-medium text-slate-500">
                                {data.customers.length} customers loaded
                            </div>
                            <div className="border rounded-md divide-y max-h-72 overflow-y-auto">
                                {data.customers.map((c) => (
                                    <div
                                        key={c.id}
                                        className="flex items-center justify-between px-3 py-2 gap-3"
                                    >
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-center gap-2">
                                                <span className="font-medium truncate">{c.name}</span>
                                                <span
                                                    className={
                                                        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold " +
                                                        (c.status === "visited"
                                                            ? "text-emerald-600 bg-emerald-50 border-emerald-100"
                                                            : "text-slate-600 bg-slate-50 border-slate-100")
                                                    }
                                                >
                                                    {c.status === "visited" ? "Visited" : "Not visited"}
                                                </span>
                                            </div>
                                            <div className="mt-1 text-[11px] text-slate-500">
                                                {c.typology.replace("_", " ")} &middot; {c.region}
                                            </div>
                                        </div>
                                        <Button
                                            size="icon"
                                            variant="outline"
                                            className="shrink-0"
                                            onClick={() => handleOpenDetail(c.id)}
                                        >
                                            <Info className="h-4 w-4" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {selectedCustomer && (
                        <div className="mt-4 space-y-3 border-t pt-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h3 className="text-sm font-semibold">
                                        Customer detail - {selectedCustomer}
                                    </h3>
                                    <p className="text-xs text-slate-500">
                                        Review purchase history with season filter.
                                    </p>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-slate-500">Season</span>
                                    <Select
                                        value={detailSeason}
                                        onValueChange={(val: string) => {
                                            setDetailSeason(val);
                                            loadDetail(selectedCustomer, val);
                                        }}
                                    >
                                        <SelectTrigger className="h-8 w-[120px] text-xs">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {seasonsForDetail.map((s) => (
                                                <SelectItem key={s} value={s}>
                                                    {s}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            {detailLoading && (
                                <div className="text-xs text-slate-500">Loading details...</div>
                            )}

                            {!detailLoading && detail && (
                                <div className="space-y-3">
                                    <div className="text-xs text-slate-600">
                                        {detail.purchaseHistory.length} product lines
                                    </div>
                                    <div className="border rounded-md max-h-60 overflow-y-auto divide-y">
                                        {detail.purchaseHistory.map((item, idx) => (
                                            <div
                                                key={`${item.skuId}-${item.season}-${idx}`}
                                                className="px-3 py-2 text-xs flex items-center justify-between gap-2"
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <div className="font-semibold truncate">
                                                        {item.skuId}
                                                    </div>
                                                    <div className="text-[11px] text-slate-500 truncate">
                                                        {item.skuName} &middot; {item.season}
                                                    </div>
                                                </div>
                                                <div className="text-right shrink-0">
                                                    <div className="font-medium">{item.units} units</div>
                                                    <div className="text-[11px] text-slate-500">
                                                        {"\u20AC"}{item.value.toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                        {detail.purchaseHistory.length === 0 && (
                                            <div className="px-3 py-4 text-xs text-slate-500">
                                                No products for this customer and season.
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </SheetContent>
        </Sheet>
    );
}
