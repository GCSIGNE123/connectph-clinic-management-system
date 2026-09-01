import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { isValidCustomRange, resolveRecordDateRange, toIsoDate } from "@/lib/date-range";

describe("resolveRecordDateRange", () => {
  beforeEach(() => {
    // Wednesday, 2026-06-17 (UTC), so "This Week" spans Mon 06-15..Sun 06-21
    // and "This Month" spans 06-01..06-30 - fixed so the tests are stable.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-17T12:00:00.000Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("'all' returns no bounds", () => {
    expect(resolveRecordDateRange("all")).toEqual({});
  });

  it("'today' returns the same date for both bounds", () => {
    expect(resolveRecordDateRange("today")).toEqual({ dateFrom: "2026-06-17", dateTo: "2026-06-17" });
  });

  it("'this_week' spans Monday through Sunday", () => {
    expect(resolveRecordDateRange("this_week")).toEqual({ dateFrom: "2026-06-15", dateTo: "2026-06-21" });
  });

  it("'this_week' still resolves to the same Monday when today IS a Sunday", () => {
    vi.setSystemTime(new Date("2026-06-21T12:00:00.000Z")); // Sunday
    expect(resolveRecordDateRange("this_week")).toEqual({ dateFrom: "2026-06-15", dateTo: "2026-06-21" });
  });

  it("'this_week' still resolves to the same Monday when today IS a Monday", () => {
    vi.setSystemTime(new Date("2026-06-15T00:30:00.000Z")); // Monday, just after UTC midnight
    expect(resolveRecordDateRange("this_week")).toEqual({ dateFrom: "2026-06-15", dateTo: "2026-06-21" });
  });

  it("'this_month' spans the first through last day of the current month", () => {
    expect(resolveRecordDateRange("this_month")).toEqual({ dateFrom: "2026-06-01", dateTo: "2026-06-30" });
  });

  it("'this_month' correctly finds the last day of a shorter month (February)", () => {
    vi.setSystemTime(new Date("2026-02-10T12:00:00.000Z"));
    expect(resolveRecordDateRange("this_month")).toEqual({ dateFrom: "2026-02-01", dateTo: "2026-02-28" });
  });

  it("'custom' passes through the given bounds", () => {
    expect(resolveRecordDateRange("custom", "2026-01-01", "2026-01-31")).toEqual({
      dateFrom: "2026-01-01",
      dateTo: "2026-01-31",
    });
  });

  it("'custom' with missing bounds returns undefined for the missing side", () => {
    expect(resolveRecordDateRange("custom", "2026-01-01", undefined)).toEqual({ dateFrom: "2026-01-01", dateTo: undefined });
  });
});

describe("isValidCustomRange", () => {
  it("is always valid for non-custom presets regardless of bounds", () => {
    expect(isValidCustomRange("all")).toBe(true);
    expect(isValidCustomRange("today", undefined, undefined)).toBe(true);
  });

  it("rejects custom with a missing From or To", () => {
    expect(isValidCustomRange("custom", undefined, "2026-01-05")).toBe(false);
    expect(isValidCustomRange("custom", "2026-01-01", undefined)).toBe(false);
    expect(isValidCustomRange("custom")).toBe(false);
  });

  it("rejects custom where From is after To", () => {
    expect(isValidCustomRange("custom", "2026-02-01", "2026-01-01")).toBe(false);
  });

  it("accepts a valid custom range", () => {
    expect(isValidCustomRange("custom", "2026-01-01", "2026-01-31")).toBe(true);
  });

  it("accepts a custom range where From equals To", () => {
    expect(isValidCustomRange("custom", "2026-01-01", "2026-01-01")).toBe(true);
  });
});

describe("toIsoDate", () => {
  it("formats a Date as YYYY-MM-DD using its UTC calendar day", () => {
    expect(toIsoDate(new Date("2026-03-05T23:59:59.000Z"))).toBe("2026-03-05");
  });
});
