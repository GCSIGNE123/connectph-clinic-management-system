import { describe, expect, it } from "vitest";
import { isValidCustomRange } from "@/features/analytics/lib/date-range";

describe("isValidCustomRange", () => {
  it("is always valid for non-custom presets regardless of start/end", () => {
    expect(isValidCustomRange("today")).toBe(true);
    expect(isValidCustomRange("last_7_days", undefined, undefined)).toBe(true);
  });

  it("rejects custom range with a missing start or end", () => {
    expect(isValidCustomRange("custom", undefined, "2026-01-05")).toBe(false);
    expect(isValidCustomRange("custom", "2026-01-01", undefined)).toBe(false);
    expect(isValidCustomRange("custom")).toBe(false);
  });

  it("rejects a custom range where start is after end", () => {
    expect(isValidCustomRange("custom", "2026-02-01", "2026-01-01")).toBe(false);
  });

  it("accepts a valid custom range", () => {
    expect(isValidCustomRange("custom", "2026-01-01", "2026-01-31")).toBe(true);
  });

  it("accepts a custom range where start equals end", () => {
    expect(isValidCustomRange("custom", "2026-01-01", "2026-01-01")).toBe(true);
  });
});
