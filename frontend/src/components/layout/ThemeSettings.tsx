"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { Moon, Sun, Monitor, Check } from "lucide-react";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

/**
 * Appearance/Theme control for the Settings page - a personal, per-browser
 * preference (via next-themes, already wired up app-wide in
 * `lib/query-client.tsx`'s `Providers` and already exposed as a quick
 * toggle in the header via `ThemeToggle`). This is the same underlying
 * mechanism, just a more discoverable, explicit Light/Dark/System control
 * with the current selection clearly visible - no second theme system.
 *
 * Real radio inputs (not styled buttons) so the browser's own semantics
 * (arrow-key navigation between options, screen-reader group
 * announcement) come for free instead of being reimplemented.
 */
export function ThemeSettings() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => setMounted(true), []);

  // Avoid rendering a possibly-wrong selected state before the persisted
  // preference is read on the client (next-themes' own hydration guard).
  const current = mounted ? (theme ?? "system") : undefined;

  return (
    <fieldset>
      <legend className="text-sm font-medium text-foreground">Theme</legend>
      <p className="mt-1 text-sm text-muted-foreground">Choose how CONNECT.PH looks on this device.</p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {OPTIONS.map(({ value, label, icon: Icon }) => {
          const selected = current === value;
          return (
            <label
              key={value}
              className={cn(
                "relative flex cursor-pointer items-center gap-3 rounded-lg border p-3 shadow-sm transition-colors",
                "hover:bg-accent hover:text-accent-foreground",
                "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2",
                selected ? "border-primary bg-accent" : "border-input bg-background"
              )}
            >
              <input
                type="radio"
                name="theme"
                value={value}
                checked={selected}
                onChange={() => setTheme(value)}
                className="sr-only"
              />
              <Icon className="h-5 w-5 shrink-0 text-foreground" aria-hidden="true" />
              <span className="text-sm font-medium text-foreground">{label}</span>
              {selected ? <Check className="ml-auto h-4 w-4 shrink-0 text-primary" aria-hidden="true" /> : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
