import { describe, expect, it } from "vitest";
import { cn, getInitials, formatDate, formatDateTime, assertNever } from "./utils";

describe("cn", () => {
  it("merges class names and resolves tailwind conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("handles conditional class values", () => {
    expect(cn("base", false && "hidden", "visible")).toBe("base visible");
  });
});

describe("getInitials", () => {
  it("returns initials from a full name", () => {
    expect(getInitials("Jane Doe")).toBe("JD");
  });

  it("returns first two letters for a single word name", () => {
    expect(getInitials("Cher")).toBe("CH");
  });

  it("returns empty string for empty input", () => {
    expect(getInitials("   ")).toBe("");
  });
});

describe("formatDate", () => {
  it("formats a bare date-only string as MM/DD/YYYY", () => {
    expect(formatDate("2026-01-02")).toBe("01/02/2026");
  });

  it("formats a bare date-only string near year-end as MM/DD/YYYY", () => {
    expect(formatDate("2026-12-31")).toBe("12/31/2026");
  });

  it("never swaps month/day (would produce DD/MM/YYYY) for a date-only string", () => {
    expect(formatDate("2026-01-02")).not.toBe("02/01/2026");
    expect(formatDate("2026-12-31")).not.toBe("31/12/2026");
  });

  it("never leaves the ISO YYYY-MM-DD shape in the output", () => {
    expect(formatDate("2026-12-31")).not.toBe("2026-12-31");
  });

  it("does not shift a date-only string by a day regardless of local timezone (UTC-parsing hazard)", () => {
    // A naive `new Date("2026-01-02")` parses as UTC midnight; formatting it
    // with local getters in a timezone behind UTC would wrongly show
    // 01/01/2026. Direct string-splitting must avoid that entirely.
    expect(formatDate("2026-01-02")).toBe("01/02/2026");
  });

  it("formats a full ISO datetime string using its local calendar date", () => {
    const d = new Date("2026-07-23T15:30:00.000Z");
    const expected = `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")}/${d.getFullYear()}`;
    expect(formatDate("2026-07-23T15:30:00.000Z")).toBe(expected);
  });

  it("formats a Date object as MM/DD/YYYY", () => {
    expect(formatDate(new Date(2026, 0, 2))).toBe("01/02/2026");
  });
});

describe("formatDateTime", () => {
  it("keeps the MM/DD/YYYY date format and retains the time component", () => {
    const result = formatDateTime(new Date(2026, 0, 2, 14, 30));
    expect(result.startsWith("01/02/2026")).toBe(true);
    expect(result).toMatch(/\d{1,2}:\d{2}\s*(AM|PM)/i);
  });

  it("does not drop the time when formatting an ISO datetime string", () => {
    const result = formatDateTime("2026-12-31T14:30:00");
    expect(result.startsWith("12/31/2026")).toBe(true);
    expect(result).toMatch(/\d{1,2}:\d{2}\s*(AM|PM)/i);
  });
});

describe("assertNever", () => {
  it("throws when called", () => {
    // @ts-expect-error intentionally passing a value for the exhaustiveness check
    expect(() => assertNever("unexpected")).toThrow();
  });
});
