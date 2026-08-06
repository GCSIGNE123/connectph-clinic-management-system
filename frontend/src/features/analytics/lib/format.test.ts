import { describe, expect, it } from "vitest";
import { formatCurrency, formatDuration, formatNumber, formatPercent } from "@/features/analytics/lib/format";

describe("formatCurrency", () => {
  it("formats a positive number as PHP currency", () => {
    expect(formatCurrency(1234.5)).toContain("1,234.50");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatCurrency(null)).toBe("-");
    expect(formatCurrency(undefined)).toBe("-");
  });

  it("formats zero correctly", () => {
    expect(formatCurrency(0)).toContain("0.00");
  });
});

describe("formatNumber", () => {
  it("formats large numbers with thousands separators", () => {
    expect(formatNumber(12345)).toBe("12,345");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatNumber(null)).toBe("-");
  });
});

describe("formatPercent", () => {
  it("converts a 0-1 fraction to a percentage string", () => {
    expect(formatPercent(0.5)).toBe("50%");
    expect(formatPercent(0.333, 1)).toBe("33.3%");
  });

  it("returns a dash for null/undefined", () => {
    expect(formatPercent(null)).toBe("-");
  });
});

describe("formatDuration", () => {
  it("formats seconds under a minute as Xs", () => {
    expect(formatDuration(45)).toBe("45s");
  });

  it("formats minutes and seconds", () => {
    expect(formatDuration(125)).toBe("2m 5s");
  });

  it("formats whole minutes without a seconds suffix", () => {
    expect(formatDuration(180)).toBe("3m");
  });

  it("formats hours and minutes", () => {
    expect(formatDuration(3725)).toBe("1h 2m");
  });

  it("formats whole hours without a minutes suffix", () => {
    expect(formatDuration(7200)).toBe("2h");
  });

  it("returns a dash for null/undefined/negative", () => {
    expect(formatDuration(null)).toBe("-");
    expect(formatDuration(undefined)).toBe("-");
    expect(formatDuration(-5)).toBe("-");
  });
});
