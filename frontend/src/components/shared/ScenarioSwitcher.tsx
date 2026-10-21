"use client";

import React from "react";
import { useSeasonStore } from "@/store/seasonStore";
import { ScenarioType } from "@/types";
import { cn } from "@/lib/utils";
import { CheckIcon } from "@phosphor-icons/react";

interface ScenarioSwitcherProps {
  className?: string;
  size?: "sm" | "md" | "lg";
}

const scenarios: { value: ScenarioType; label: string }[] = [
  { value: "conservative", label: "Conservative" },
  { value: "base", label: "Base Case" },
  { value: "optimistic", label: "Optimistic" },
];

export default function ScenarioSwitcher({ className, size = "md" }: ScenarioSwitcherProps) {
  const { activeScenario, setActiveScenario } = useSeasonStore();

  const sizeClasses = {
    sm: "h-8 px-3.5 text-xs",
    md: "h-[38px] px-[18px] text-sm",
    lg: "h-11 px-5 text-base",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-line bg-card p-[5px] shadow-card",
        className
      )}
      role="group"
      aria-label="Scenario selection"
    >
      {scenarios.map((scenario) => {
        const isActive = activeScenario === scenario.value;
        return (
          <button
            key={scenario.value}
            type="button"
            onClick={() => setActiveScenario(scenario.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full transition-colors duration-150",
              sizeClasses[size],
              isActive
                ? "bg-brand font-bold text-white shadow-brand"
                : "font-semibold text-fg-2 hover:bg-soft hover:text-fg-1"
            )}
            aria-pressed={isActive}
          >
            {scenario.label}
            {isActive && scenario.value === "base" && (
              <CheckIcon weight="bold" aria-hidden className="h-[13px] w-[13px]" />
            )}
          </button>
        );
      })}
    </div>
  );
}
