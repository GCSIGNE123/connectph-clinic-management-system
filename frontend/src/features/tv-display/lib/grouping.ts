import type { TvDisplayNowServing, TvDisplayWaitingEntry } from "@/features/tv-display/types";

/**
 * Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): groups a flat
 * `now_serving`/`next_waiting` list by "destination" - the doctor if one is
 * assigned to the ticket, else the department name (e.g. a Laboratory or
 * Radiology department-only ticket with no doctor). Extracted as a pure,
 * independently-testable function (matching this codebase's existing
 * pattern in `lib/format.ts`) rather than baked into `TvDisplayScreen.tsx`'s
 * JSX, per the spec's testability requirement.
 *
 * A single doctor/department clinic (or a moment where only one destination
 * has anything active) naturally produces exactly one group - the caller
 * renders that as the existing clean single-queue layout, no special-casing
 * needed here.
 */
export interface DestinationGroup<T> {
  key: string;
  label: string;
  entries: T[];
}

function destinationKey(entry: { doctorName: string | null; departmentName: string | null }): {
  key: string;
  label: string;
} {
  if (entry.doctorName) {
    return { key: `doctor:${entry.doctorName}`, label: `Dr. ${entry.doctorName}` };
  }
  if (entry.departmentName) {
    return { key: `dept:${entry.departmentName}`, label: entry.departmentName };
  }
  return { key: "general", label: "General" };
}

function groupByDestination<T extends { doctorName: string | null; departmentName: string | null }>(
  entries: T[]
): DestinationGroup<T>[] {
  const groups = new Map<string, DestinationGroup<T>>();
  for (const entry of entries) {
    const { key, label } = destinationKey(entry);
    const existing = groups.get(key);
    if (existing) {
      existing.entries.push(entry);
    } else {
      groups.set(key, { key, label, entries: [entry] });
    }
  }
  return Array.from(groups.values());
}

export function groupNowServing(entries: TvDisplayNowServing[]): DestinationGroup<TvDisplayNowServing>[] {
  return groupByDestination(entries);
}

export function groupWaiting(entries: TvDisplayWaitingEntry[]): DestinationGroup<TvDisplayWaitingEntry>[] {
  return groupByDestination(entries);
}
