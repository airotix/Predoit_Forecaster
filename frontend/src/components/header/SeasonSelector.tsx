"use client";

import React from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import { LegacySeason } from "@/types";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";

const SEASONS_FALLBACK: LegacySeason[] = ["All", "SS2024", "FW2024", "SS2025", "FW2025"];

export default function SeasonSelector() {
    const { season, setSeason, filterOptions } = useDashboardStore();
    const options = (filterOptions?.seasons?.length ? filterOptions.seasons : SEASONS_FALLBACK) as LegacySeason[];
    const value = options.includes(season) ? season : options[0];

    return (
        <Select value={value} onValueChange={(val: LegacySeason) => setSeason(val)}>
            <SelectTrigger className="w-[140px] font-medium bg-slate-50/50">
                <SelectValue placeholder="Select season" />
            </SelectTrigger>
            <SelectContent>
                {options.map((s) => (
                    <SelectItem key={s} value={s}>
                        {s}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}
