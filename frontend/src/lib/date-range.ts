/**
 * Shared "recent records" date-range filter for record-list tabs (Visits,
 * Billing, Laboratory, Queue, Appointments, Vaccinations, Patients, and
 * their patient-history nested views). Deliberately separate from
 * `features/analytics/lib/date-range.ts` - Analytics has its own,
 * report-specific preset set (today/yesterday/last_7_days/this_month/
 * last_month/custom, always a bounded range, resolved server-side by
 * `AnalyticsService.resolve_range`) which this feature must not disturb.
 * Record tabs need a different, simpler set (All/Today/This Week/This
 * Month/Custom, with "All" meaning "no filter" - a concept Analytics never
 * needed) and resolve the concrete dates client-side before calling the
 * API, mirroring the pattern the Visits page already used locally.
 *
 * Timezone: uses the browser's `Date` + `toISOString()` (UTC calendar
 * day), matching the existing convention already used by the Visits page's
 * own (now-removed) local resolver and the backend's `date_from`/`date_to`
 * filters (see `backend/app/db/date_filters.py`'s docstring) - the
 * application has no working per-clinic timezone conversion anywhere, so
 * this stays consistent with everything else rather than introducing a
 * second, different boundary rule.
 */

export type RecordDateRangePreset = "all" | "today" | "this_week" | "this_month" | "custom";

export const RECORD_DATE_RANGE_PRESETS: { value: RecordDateRangePreset; label: string }[] = [
  { value: "all", label: "All" },
  { value: "today", label: "Today" },
  { value: "this_week", label: "This Week" },
  { value: "this_month", label: "This Month" },
  { value: "custom", label: "Custom" },
];

export function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Monday-Sunday, per the project's explicit convention for this feature
 * (no pre-existing calendar-week convention exists elsewhere in the
 * codebase - `day_of_week` fields are for weekly schedules, unrelated). */
function startOfWeekMonday(d: Date): Date {
  const day = d.getUTCDay(); // 0=Sunday..6=Saturday (UTC, matching toIsoDate's UTC basis)
  const diffToMonday = day === 0 ? 6 : day - 1;
  const start = new Date(d);
  start.setUTCDate(start.getUTCDate() - diffToMonday);
  return start;
}

function endOfWeekSunday(d: Date): Date {
  const start = startOfWeekMonday(d);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 6);
  return end;
}

function startOfMonth(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
}

function endOfMonth(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
}

/** Resolves a preset (plus optional custom bounds) into concrete
 * `dateFrom`/`dateTo` ISO date strings to send to the backend. "all"
 * returns `{}` (both undefined) - no filter applied, matching every
 * existing endpoint's "omitted = unfiltered" convention. */
export function resolveRecordDateRange(
  preset: RecordDateRangePreset,
  customFrom?: string,
  customTo?: string,
): { dateFrom?: string; dateTo?: string } {
  const now = new Date();
  switch (preset) {
    case "today": {
      const today = toIsoDate(now);
      return { dateFrom: today, dateTo: today };
    }
    case "this_week":
      return { dateFrom: toIsoDate(startOfWeekMonday(now)), dateTo: toIsoDate(endOfWeekSunday(now)) };
    case "this_month":
      return { dateFrom: toIsoDate(startOfMonth(now)), dateTo: toIsoDate(endOfMonth(now)) };
    case "custom":
      return { dateFrom: customFrom || undefined, dateTo: customTo || undefined };
    case "all":
    default:
      return {};
  }
}

/** True unless `preset` is "custom" with a missing bound or `from > to`. */
export function isValidCustomRange(preset: RecordDateRangePreset, from?: string, to?: string): boolean {
  if (preset !== "custom") return true;
  if (!from || !to) return false;
  return new Date(from).getTime() <= new Date(to).getTime();
}
