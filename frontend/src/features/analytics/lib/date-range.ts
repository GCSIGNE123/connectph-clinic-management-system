import type { DateRangePreset } from "@/features/analytics/types";

export const DATE_RANGE_PRESETS: { value: DateRangePreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last_7_days", label: "Last 7 Days" },
  { value: "this_month", label: "This Month" },
  { value: "last_month", label: "Last Month" },
  { value: "custom", label: "Custom Range" },
];

/** True when `preset` is `custom` and both `start`/`end` are non-empty -
 * the only combination the backend's `date_range=custom` filter accepts. */
export function isValidCustomRange(preset: DateRangePreset, start?: string, end?: string): boolean {
  if (preset !== "custom") return true;
  if (!start || !end) return false;
  return new Date(start).getTime() <= new Date(end).getTime();
}
