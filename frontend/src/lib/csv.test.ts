import { describe, expect, it } from "vitest";
import { toCsv, parseCsv, parseCsvNumber } from "./csv";

describe("toCsv", () => {
  it("builds a header row plus one row per record", () => {
    const csv = toCsv(["code", "name"], [["S01", "Dr Checkup"], ["S02", "ECG"]]);
    expect(csv).toBe("code,name\r\nS01,Dr Checkup\r\nS02,ECG");
  });

  it("quotes fields containing commas, quotes, or newlines", () => {
    const csv = toCsv(["name"], [['Says "hi", bye'], ["Multi\nline"]]);
    expect(csv).toBe('name\r\n"Says ""hi"", bye"\r\n"Multi\nline"');
  });

  it("renders null/undefined cells as empty", () => {
    const csv = toCsv(["a", "b"], [[null, undefined]]);
    expect(csv).toBe("a,b\r\n,");
  });
});

describe("parseCsv", () => {
  it("parses a simple CSV into header-keyed row objects", () => {
    const rows = parseCsv("code,name\nS01,Dr Checkup\nS02,ECG");
    expect(rows).toEqual([
      { code: "S01", name: "Dr Checkup" },
      { code: "S02", name: "ECG" },
    ]);
  });

  it("handles quoted fields with embedded commas and escaped quotes", () => {
    const rows = parseCsv('name,note\n"Dr Checkup","Says ""hi"", bye"');
    expect(rows).toEqual([{ name: "Dr Checkup", note: 'Says "hi", bye' }]);
  });

  it("handles CRLF line endings", () => {
    const rows = parseCsv("code,name\r\nS01,Dr Checkup\r\n");
    expect(rows).toEqual([{ code: "S01", name: "Dr Checkup" }]);
  });

  it("skips blank trailing lines", () => {
    const rows = parseCsv("code,name\nS01,Dr Checkup\n\n");
    expect(rows).toEqual([{ code: "S01", name: "Dr Checkup" }]);
  });

  it("returns an empty array for empty input", () => {
    expect(parseCsv("")).toEqual([]);
    expect(parseCsv("   ")).toEqual([]);
  });

  it("round-trips a value produced by toCsv", () => {
    const original = [{ name: 'Says "hi", bye\nnext line' }];
    const csv = toCsv(["name"], original.map((r) => [r.name]));
    expect(parseCsv(csv)).toEqual(original);
  });
});

describe("parseCsvNumber", () => {
  it("parses a plain number", () => {
    expect(parseCsvNumber("400")).toBe(400);
    expect(parseCsvNumber("400.50")).toBe(400.5);
  });

  it("strips thousands-separator commas", () => {
    expect(parseCsvNumber("1,200.00")).toBe(1200);
    expect(parseCsvNumber("1,234,567")).toBe(1234567);
  });

  it("strips currency symbols and surrounding whitespace", () => {
    expect(parseCsvNumber("₱ 300")).toBe(300);
    expect(parseCsvNumber("  400  ")).toBe(400);
    expect(parseCsvNumber("$1,200.00")).toBe(1200);
  });

  it("returns null for a blank field", () => {
    expect(parseCsvNumber("")).toBeNull();
    expect(parseCsvNumber("   ")).toBeNull();
    expect(parseCsvNumber(undefined)).toBeNull();
  });

  it("returns NaN for genuinely non-numeric input", () => {
    expect(Number.isNaN(parseCsvNumber("not a number"))).toBe(true);
  });
});
