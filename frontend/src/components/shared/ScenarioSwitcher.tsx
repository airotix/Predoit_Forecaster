"use client";

import React from "react";
import { useSeasonStore } from "@/store/seasonStore";
import { ScenarioType } from "@/types";
import { cn } from "@/lib/utils";

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
    sm: "px-2.5 py-1 text-xs",
    md: "px-3.5 py-1.5 text-sm",
    lg: "px-4 py-2 text-base",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-lg border border-slate-200 bg-slate-100 p-1 dark:border-slate-800 dark:bg-slate-900",
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
            onClick={() => setActiveScenario(scenario.value)}
            className={cn(
              "rounded-md font-medium transition-all duration-200",
              sizeClasses[size],
              isActive
                ? "bg-white text-blue-700 shadow-sm dark:bg-slate-800 dark:text-blue-400"
                : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
            )}
            aria-pressed={isActive}
          >
            {scenario.label}
            {isActive && scenario.value === "base" && (
              <span className="ml-1 text-blue-500">✓</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
