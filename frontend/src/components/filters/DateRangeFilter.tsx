"use client";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

export interface DateRangeFilterProps<TPreset extends string = string> {
  preset: TPreset;
  presets: { value: TPreset; label: string }[];
  start?: string;
  end?: string;
  onChange: (next: { preset: TPreset; start?: string; end?: string }) => void;
  /** Shown under the custom From/To inputs when the caller has determined
   * the range is invalid (e.g. From > To) - purely a display prop, the
   * caller owns the actual validation (see `isValidCustomRange` in
   * `@/lib/date-range` or `@/features/analytics/lib/date-range`). */
  customRangeError?: string | null;
}

/**
 * Generic preset dropdown + conditional custom From/To date inputs, shared
 * by both the Analytics/Reports date-range system (its own preset set:
 * today/yesterday/last_7_days/this_month/last_month/custom - see
 * `features/analytics/lib/date-range.ts`) and the record-list "recent
 * records" filter (All/Today/This Week/This Month/Custom - see
 * `@/lib/date-range.ts`). The component itself is presentational only; the
 * preset list and all date-resolution logic live in each caller's own lib
 * module, since the two use cases resolve dates differently (Analytics
 * server-side, record lists client-side) and must not be conflated.
 */
export function DateRangeFilter<TPreset extends string = string>({
  preset,
  presets,
  start,
  end,
  onChange,
  customRangeError,
}: DateRangeFilterProps<TPreset>) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="date-range-filter">
      <Select
        value={preset}
        onChange={(e) => onChange({ preset: e.target.value as TPreset, start, end })}
        className="w-auto min-w-[10rem]"
        aria-label="Date range preset"
      >
        {presets.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </Select>
      {preset === "custom" ? (
        <>
          <Input
            type="date"
            value={start ?? ""}
            onChange={(e) => onChange({ preset, start: e.target.value, end })}
            aria-label="Start date"
            className="w-auto"
          />
          <span className="text-sm text-muted-foreground">to</span>
          <Input
            type="date"
            value={end ?? ""}
            onChange={(e) => onChange({ preset, start, end: e.target.value })}
            aria-label="End date"
            className="w-auto"
          />
          {customRangeError ? <span className="text-xs text-destructive">{customRangeError}</span> : null}
        </>
      ) : null}
    </div>
  );
}
