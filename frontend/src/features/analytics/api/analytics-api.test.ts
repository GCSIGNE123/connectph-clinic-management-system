import { describe, expect, it } from "vitest";
import { toSeries } from "@/features/analytics/api/analytics-api";

describe("toSeries", () => {
  it("maps raw {label, value} wire objects to typed SeriesPoint entries", () => {
    const raw = [
      { label: "2026-07-26", value: "12" },
      { label: "2026-07-27", value: 5.5 },
    ];
    expect(toSeries(raw)).toEqual([
      { label: "2026-07-26", value: 12 },
      { label: "2026-07-27", value: 5.5 },
    ]);
  });

  it("returns an empty array for null/undefined/empty input", () => {
    expect(toSeries(undefined as unknown as never[])).toEqual([]);
    expect(toSeries(null as unknown as never[])).toEqual([]);
    expect(toSeries([])).toEqual([]);
  });

  it("coerces numeric-string values to numbers", () => {
    const raw = [{ label: "Cash", value: "140.00" }];
    expect(toSeries(raw)[0].value).toBe(140);
  });
});
