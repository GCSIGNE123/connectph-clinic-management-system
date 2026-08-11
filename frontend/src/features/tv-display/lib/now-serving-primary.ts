import type { TvDisplayNowServing } from "@/features/tv-display/types";

/**
 * Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display - single-active-
 * ticket display rule): a clinic doctor/department should only ever be
 * shown as actively serving ONE patient at a time on the TV, even if the
 * backend has more than one ticket in `Called`/`Serving` status for that
 * same destination simultaneously (e.g. a doctor called a second patient
 * without the first one's visit ever being completed - a real state the
 * backend allows, since nothing forces strict one-at-a-time completion).
 *
 * For each destination (doctor if assigned, else department - same key as
 * `grouping.ts`), the entry with the most recently updated `calledAt` is
 * treated as the one genuinely being served right now ("primary"); any
 * other Called/Serving tickets for that same destination are demoted to
 * `overflow` so the caller can fold them into "Next in Queue" instead of
 * rendering them as a second simultaneous Now Serving card.
 *
 * Does NOT affect the announcer - every entry in `nowServing` (primary or
 * overflow) still represents a real call the doctor/department made, so
 * `TvDisplayScreen.tsx` still announces off the full, unfiltered list.
 */
export interface PrimaryNowServingSplit {
  primary: TvDisplayNowServing[];
  overflow: TvDisplayNowServing[];
}

function destinationKey(entry: TvDisplayNowServing): string {
  if (entry.doctorName) return `doctor:${entry.doctorName}`;
  if (entry.departmentName) return `dept:${entry.departmentName}`;
  return "general";
}

export function splitPrimaryNowServing(entries: TvDisplayNowServing[]): PrimaryNowServingSplit {
  const byDestination = new Map<string, TvDisplayNowServing[]>();
  for (const entry of entries) {
    const key = destinationKey(entry);
    const existing = byDestination.get(key);
    if (existing) {
      existing.push(entry);
    } else {
      byDestination.set(key, [entry]);
    }
  }

  const primary: TvDisplayNowServing[] = [];
  const overflow: TvDisplayNowServing[] = [];
  for (const group of byDestination.values()) {
    if (group.length === 1) {
      primary.push(group[0]);
      continue;
    }
    // Most recently called/recalled wins the Now Serving card; a `null`
    // calledAt (shouldn't happen for a Called ticket, but defensively
    // handled) sorts last so it never wins over a real timestamp.
    let winnerIndex = 0;
    for (let i = 1; i < group.length; i++) {
      const currentCalledAt = group[winnerIndex].calledAt;
      const candidateCalledAt = group[i].calledAt;
      if (candidateCalledAt && (!currentCalledAt || candidateCalledAt > currentCalledAt)) {
        winnerIndex = i;
      }
    }
    group.forEach((entry, i) => {
      if (i === winnerIndex) primary.push(entry);
      else overflow.push(entry);
    });
  }

  return { primary, overflow };
}
