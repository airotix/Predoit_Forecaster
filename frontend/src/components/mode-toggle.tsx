"use client";

import * as React from "react";
import { MoonIcon, SunIcon } from "@phosphor-icons/react";
import { useTheme } from "next-themes";

export function ModeToggle() {
  const { setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";

  return (
    <button
      type="button"
      aria-label="Toggle theme"
      title="Appearance"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-line bg-card text-fg-2 transition-colors hover:border-border-strong hover:text-fg-1"
    >
      {dark ? <SunIcon className="h-[18px] w-[18px]" /> : <MoonIcon className="h-[18px] w-[18px]" />}
    </button>
  );
}
