import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class names, resolving conflicts (shadcn-style helper).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Global date display standard for the whole app: MM/DD/YYYY (e.g.
 * "08/16/2026"). This is the ONE place that decision lives - every
 * user-visible date in the app should route through `formatDate`/
 * `formatDateTime` rather than calling `toLocaleDateString()`/
 * `Intl.DateTimeFormat` directly, so the format never drifts between
 * screens. This only changes how dates are DISPLAYED - it has no effect
 * on `<input type="date">` values (which must stay the browser-required
 * `YYYY-MM-DD`), on API request/response bodies, or on any stored value.
 */
const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Timezone-safe date-only parsing. A bare `YYYY-MM-DD` string (what every
 * backend `date`-typed field, e.g. `appointment_date`/`birth_date`/
 * `queue_date`, serializes as - no time, no offset) has no timezone
 * component at all; the calendar day it names must never depend on the
 * viewer's local timezone. Feeding a bare date string to `new Date(...)`
 * parses it as UTC midnight (per the ECMA-262 date-only string rule),
 * and any subsequent `.getMonth()`/`.getDate()`/`.getFullYear()` or
 * `Intl.DateTimeFormat` call (with no explicit `timeZone`) then reads it
 * back in the viewer's LOCAL timezone - for any timezone behind UTC, that
 * silently rolls the displayed date back by one day. Splitting the string
 * directly, with no `Date` object or timezone conversion involved at all,
 * avoids that class of bug entirely.
 */
function splitDateOnly(value: string): { year: number; month: number; day: number } | null {
  if (!DATE_ONLY_PATTERN.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/**
 * Format a Date, ISO datetime string, or bare `YYYY-MM-DD` date-only
 * string into MM/DD/YYYY. Date-only strings are parsed directly (see
 * `splitDateOnly`) to avoid a timezone-driven off-by-one day; anything
 * else (a `Date` object, or a string with a time/timezone component) is
 * read via local-time getters - the same "show it in the viewer's own
 * local time" behavior `toLocaleDateString()` already had, just forced
 * into MM/DD/YYYY instead of a locale-dependent format.
 */
export function formatDate(date: Date | string): string {
  if (typeof date === "string") {
    const parsed = splitDateOnly(date);
    if (parsed) return `${pad2(parsed.month)}/${pad2(parsed.day)}/${parsed.year}`;
  }
  const d = typeof date === "string" ? new Date(date) : date;
  return `${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}/${d.getFullYear()}`;
}

/**
 * Format a Date or ISO datetime string into "MM/DD/YYYY h:mm AM/PM" - the
 * date portion always MM/DD/YYYY, the time portion unchanged from the
 * existing `toLocaleTimeString`-style short local time. Not meant for
 * bare date-only values (they have no time to show) - use `formatDate`
 * for those.
 */
export function formatDateTime(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const datePart = formatDate(d);
  const timePart = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return `${datePart} ${timePart}`;
}

/**
 * Produce initials from a display name, e.g. "Jane Doe" -> "JD".
 */
export function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

/**
 * Small delay helper, useful for simulating latency in placeholder UI.
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Type-safe wrapper to assert a value is never reached (exhaustiveness check).
 */
export function assertNever(value: never): never {
  throw new Error(`Unhandled case: ${JSON.stringify(value)}`);
}
