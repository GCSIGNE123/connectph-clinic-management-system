"use client";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DATE_RANGE_PRESETS } from "@/features/analytics/lib/date-range";
import type { DateRangePreset } from "@/features/analytics/types";

export interface DateRangeFilterProps {
  preset: DateRangePreset;
  start?: string;
  end?: string;
  onChange: (next: { preset: DateRangePreset; start?: string; end?: string }) => void;
}

export function DateRangeFilter({ preset, start, end, onChange }: DateRangeFilterProps) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="date-range-filter">
      <Select
        value={preset}
        onChange={(e) => onChange({ preset: e.target.value as DateRangePreset, start, end })}
        className="w-auto min-w-[10rem]"
        aria-label="Date range preset"
      >
        {DATE_RANGE_PRESETS.map((p) => (
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
        </>
      ) : null}
    </div>
  );
}
