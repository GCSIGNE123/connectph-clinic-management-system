"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SearchableSelectOption {
  value: string;
  label: string;
}

export interface SearchableSelectProps {
  options: SearchableSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  disabled?: boolean;
  invalid?: boolean;
  className?: string;
  id?: string;
}

/**
 * Type-to-filter dropdown for a plain `<select>`-shaped value (a single id
 * chosen from a list of options), for lists too long to scan by eye - a
 * native `<select>`'s only "search" is jump-to-first-matching-letter, which
 * doesn't help once a list runs into the hundreds (e.g. a clinic's full
 * lab/service catalog). Not a general combobox library - deliberately
 * minimal and dependency-free, matching this codebase's existing
 * `components/ui` primitives (plain `<select>`, no headless-UI dependency).
 *
 * Keeps the exact same "single id in, single id out" contract as `Select`
 * so it drops into `react-hook-form` the same way the `Patient` field in
 * `NewQueueDialog.tsx` already does (`setValue`/`watch`, not `register` -
 * a free-text search input can't be registered as a native form control
 * whose value IS the id).
 */
export function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = "Select...",
  emptyLabel = "No matches.",
  disabled,
  invalid,
  className,
  id,
}: SearchableSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const containerRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const selected = options.find((o) => o.value === value) ?? null;

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  React.useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function selectOption(option: SearchableSelectOption) {
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          id={id}
          type="text"
          disabled={disabled}
          className={cn(
            "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 pr-8 text-sm shadow-sm transition-colors",
            "placeholder:text-muted-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
            "disabled:cursor-not-allowed disabled:opacity-50",
            invalid && "border-destructive focus-visible:ring-destructive",
            className
          )}
          placeholder={placeholder}
          value={open ? query : (selected?.label ?? "")}
          onFocus={() => {
            setOpen(true);
            setQuery("");
          }}
          onChange={(e) => {
            setOpen(true);
            setQuery(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              setQuery("");
              inputRef.current?.blur();
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (filtered.length === 1) selectOption(filtered[0]);
            }
          }}
          aria-invalid={invalid ? "true" : undefined}
          autoComplete="off"
        />
        <ChevronDown
          className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
      </div>

      {open ? (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-border bg-popover shadow-md">
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted-foreground">{emptyLabel}</p>
          ) : (
            filtered.map((option) => (
              <button
                key={option.value}
                type="button"
                className={cn(
                  "flex w-full items-center px-3 py-2 text-left text-sm hover:bg-accent",
                  option.value === value && "bg-accent"
                )}
                onClick={() => selectOption(option)}
              >
                {option.label}
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
