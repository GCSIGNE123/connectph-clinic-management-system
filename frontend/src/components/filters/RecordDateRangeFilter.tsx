"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DateRangeFilter } from "@/components/filters/DateRangeFilter";
import {
  RECORD_DATE_RANGE_PRESETS,
  isValidCustomRange,
  resolveRecordDateRange,
  type RecordDateRangePreset,
} from "@/lib/date-range";

export interface RecordDateRangeFilterProps {
  /** Called with the resolved `dateFrom`/`dateTo` (both undefined for
   * "All") whenever a non-custom preset is picked, or when Custom's Apply
   * button is clicked with a valid range. Never called for an invalid
   * custom range - the error is shown inline instead. */
  onApply: (range: { dateFrom?: string; dateTo?: string }) => void;
  /** Initial preset - defaults to "all" (no filter), matching every
   * existing list endpoint's own "omitted = unfiltered" behavior. */
  defaultPreset?: RecordDateRangePreset;
}

/**
 * The shared "recent records" date filter control for record-list tabs -
 * a thin, opinionated wrapper around the generic `DateRangeFilter` that
 * adds the record-tab preset set (All/Today/This Week/This Month/Custom),
 * client-side date resolution, and an explicit Apply step for Custom (non-
 * custom presets apply immediately on selection - only Custom needs an
 * extra step since it has two fields to fill in first).
 */
export function RecordDateRangeFilter({ onApply, defaultPreset = "all" }: RecordDateRangeFilterProps) {
  const [preset, setPreset] = useState<RecordDateRangePreset>(defaultPreset);
  const [customFrom, setCustomFrom] = useState<string | undefined>(undefined);
  const [customTo, setCustomTo] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  function handleChange(next: { preset: RecordDateRangePreset; start?: string; end?: string }) {
    setPreset(next.preset);
    setCustomFrom(next.start);
    setCustomTo(next.end);
    setError(null);
    if (next.preset !== "custom") {
      onApply(resolveRecordDateRange(next.preset));
    }
  }

  function handleApply() {
    if (!isValidCustomRange("custom", customFrom, customTo)) {
      setError(!customFrom || !customTo ? "Select both a From and To date." : "From date must be before or equal to the To date.");
      return;
    }
    setError(null);
    onApply(resolveRecordDateRange("custom", customFrom, customTo));
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <DateRangeFilter
        preset={preset}
        presets={RECORD_DATE_RANGE_PRESETS}
        start={customFrom}
        end={customTo}
        onChange={handleChange}
        customRangeError={error}
      />
      {preset === "custom" ? (
        <Button type="button" size="sm" onClick={handleApply}>
          Apply
        </Button>
      ) : null}
    </div>
  );
}
