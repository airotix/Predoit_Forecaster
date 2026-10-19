"use client";

import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { SizeRecommendation } from "@/types";
import { cn } from "@/lib/utils";
import { RotateCcw } from "lucide-react";

interface SizeEditorModalProps {
  open: boolean;
  onClose: () => void;
  skuId: string;
  skuName: string;
  sizes: SizeRecommendation[];
  historicalSizes: Record<string, number>;
  onApply: (sizes: SizeRecommendation[]) => void;
}

export default function SizeEditorModal({
  open,
  onClose,
  skuId,
  skuName,
  sizes: initialSizes,
  historicalSizes,
  onApply,
}: SizeEditorModalProps) {
  const [sizes, setSizes] = useState<SizeRecommendation[]>(initialSizes);

  useEffect(() => {
    setSizes(initialSizes);
  }, [initialSizes]);

  const totalUnits = sizes.reduce((sum, s) => sum + (s.blocked ? 0 : s.finalQty), 0);

  const updateSize = (sizeId: string, field: keyof SizeRecommendation, value: unknown) => {
    setSizes((prev) =>
      prev.map((s) => {
        if (s.size !== sizeId) return s;
        const updated = { ...s, [field]: value };
        if (field === "minUnits" || field === "maxUnits" || field === "blocked") {
          let finalQty = updated.manualOverride ?? updated.recommended;
          if (updated.blocked) {
            finalQty = 0;
          } else {
            if (updated.minUnits !== null && finalQty < updated.minUnits) {
              finalQty = updated.minUnits;
            }
            if (updated.maxUnits !== null && finalQty > updated.maxUnits) {
              finalQty = updated.maxUnits;
            }
          }
          updated.finalQty = finalQty;
        }
        return updated;
      })
    );
  };

  const resetToAI = () => {
    setSizes(
      initialSizes.map((s) => ({
        ...s,
        manualOverride: null,
        finalQty: s.recommended,
        minUnits: null,
        maxUnits: null,
        blocked: false,
        rounding: null,
      }))
    );
  };

  const handleApply = () => {
    onApply(sizes);
    onClose();
  };

  const maxHistorical = Math.max(...Object.values(historicalSizes), 1);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Size Distribution Editor</DialogTitle>
          <DialogDescription>
            {skuId} — {skuName}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Curve Comparison Chart */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium">Curve Comparison</h4>
            <div className="flex items-end gap-4 h-32">
              {sizes.map((size) => {
                const historical = historicalSizes[size.size] || 0;
                const aiHeight = (size.recommended / Math.max(totalUnits, 1)) * 100;
                const histHeight = (historical / maxHistorical) * 100;

                return (
                  <div key={size.size} className="flex-1 flex flex-col items-center gap-1">
                    <div className="flex items-end gap-1 h-24 w-full">
                      <div
                        className="flex-1 bg-blue-500 rounded-t transition-all"
                        style={{ height: `${aiHeight}%` }}
                        title={`AI: ${size.recommended}`}
                      />
                      <div
                        className="flex-1 bg-slate-300 dark:bg-slate-600 rounded-t transition-all"
                        style={{ height: `${histHeight}%` }}
                        title={`Historical: ${historical}`}
                      />
                    </div>
                    <span className="text-xs font-medium">{size.size}</span>
                  </div>
                );
              })}
            </div>
            <div className="flex items-center gap-4 text-xs">
              <div className="flex items-center gap-1.5">
                <div className="h-2.5 w-2.5 rounded-sm bg-blue-500" />
                <span>AI Recommended</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2.5 w-2.5 rounded-sm bg-slate-300 dark:bg-slate-600" />
                <span>Historical Sales</span>
              </div>
            </div>
          </div>

          {/* Rules Table */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium">Per-Size Rules</h4>
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 dark:bg-slate-900">
                    <th className="px-3 py-2 text-left font-medium">Size</th>
                    <th className="px-3 py-2 text-right font-medium">AI Rec.</th>
                    <th className="px-3 py-2 text-center font-medium">Min</th>
                    <th className="px-3 py-2 text-center font-medium">Max</th>
                    <th className="px-3 py-2 text-center font-medium">Blocked</th>
                    <th className="px-3 py-2 text-center font-medium">Rounding</th>
                    <th className="px-3 py-2 text-right font-medium">Final Qty</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {sizes.map((size) => (
                    <tr
                      key={size.size}
                      className={cn(
                        size.blocked && "bg-slate-100 dark:bg-slate-800/50 opacity-60"
                      )}
                    >
                      <td className="px-3 py-2 font-medium">{size.size}</td>
                      <td className="px-3 py-2 text-right text-slate-600 dark:text-slate-400">
                        {size.recommended}
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          type="number"
                          min={0}
                          value={size.minUnits ?? ""}
                          onChange={(e) =>
                            updateSize(
                              size.size,
                              "minUnits",
                              e.target.value ? parseInt(e.target.value) : null
                            )
                          }
                          className="h-8 w-16 text-center mx-auto"
                          disabled={size.blocked}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          type="number"
                          min={0}
                          value={size.maxUnits ?? ""}
                          onChange={(e) =>
                            updateSize(
                              size.size,
                              "maxUnits",
                              e.target.value ? parseInt(e.target.value) : null
                            )
                          }
                          className="h-8 w-16 text-center mx-auto"
                          disabled={size.blocked}
                        />
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Checkbox
                          checked={size.blocked}
                          onCheckedChange={(checked) =>
                            updateSize(size.size, "blocked", checked)
                          }
                        />
                      </td>
                      <td className="px-3 py-2">
                        <select
                          value={size.rounding || ""}
                          onChange={(e) =>
                            updateSize(size.size, "rounding", e.target.value || null)
                          }
                          className="h-8 w-20 rounded border border-slate-200 dark:border-slate-700 bg-transparent text-xs mx-auto block"
                          disabled={size.blocked}
                        >
                          <option value="">—</option>
                          <option value="MOQ ×6">MOQ ×6</option>
                          <option value="MOQ ×12">MOQ ×12</option>
                          <option value="Round 5">Round 5</option>
                          <option value="Round 10">Round 10</option>
                        </select>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span
                          className={cn(
                            "font-semibold",
                            size.finalQty !== size.recommended && "text-amber-600"
                          )}
                        >
                          {size.finalQty}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Live Preview */}
          <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-900 rounded-lg">
            <div>
              <p className="text-sm text-slate-600 dark:text-slate-400">Total Units</p>
              <p className="text-2xl font-bold">{totalUnits.toLocaleString()}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-slate-600 dark:text-slate-400">vs AI Recommendation</p>
              <p
                className={cn(
                  "text-lg font-semibold",
                  totalUnits > initialSizes.reduce((s, x) => s + x.recommended, 0)
                    ? "text-amber-600"
                    : totalUnits < initialSizes.reduce((s, x) => s + x.recommended, 0)
                    ? "text-blue-600"
                    : "text-emerald-600"
                )}
              >
                {totalUnits - initialSizes.reduce((s, x) => s + x.recommended, 0) >= 0 && "+"}
                {totalUnits - initialSizes.reduce((s, x) => s + x.recommended, 0)}
              </p>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={resetToAI}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Reset to AI
          </Button>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleApply}>Apply Rules</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
