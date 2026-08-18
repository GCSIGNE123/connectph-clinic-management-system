import { describe, expect, it } from "vitest";
import { interpretResult, nextActionFor, validateResultRows } from "@/features/laboratory/types";
import type { LaboratoryResultInput } from "@/features/laboratory/types";

describe("nextActionFor", () => {
  it("maps each in-progress status to its contextual worklist action", () => {
    expect(nextActionFor("Requested")).toEqual({ label: "Collect Specimen", action: "collect" });
    expect(nextActionFor("Collected")).toEqual({ label: "Start Processing", action: "process" });
    expect(nextActionFor("Processing")).toEqual({ label: "Enter Results", action: "results" });
    expect(nextActionFor("Completed")).toEqual({ label: "Release Results", action: "release" });
  });

  it("returns null for terminal statuses (no further action)", () => {
    expect(nextActionFor("Released")).toBeNull();
    expect(nextActionFor("Cancelled")).toBeNull();
  });
});

describe("validateResultRows", () => {
  function row(overrides: Partial<LaboratoryResultInput> = {}): LaboratoryResultInput {
    return { parameterName: "Hemoglobin", resultType: "Numeric", numericValue: 14, ...overrides };
  }

  it("accepts a valid set of numeric and text rows", () => {
    expect(
      validateResultRows([row(), row({ parameterName: "Remarks", resultType: "Text", textValue: "Normal", numericValue: undefined })])
    ).toEqual([]);
  });

  it("requires at least one parameter row", () => {
    expect(validateResultRows([{ parameterName: "", resultType: "Numeric" }])).toContain(
      "At least one result parameter is required."
    );
  });

  it("flags a numeric row missing its value", () => {
    const warnings = validateResultRows([row({ numericValue: null })]);
    expect(warnings).toContain("Missing numeric value for 'Hemoglobin'.");
  });

  it("flags a text row missing its value", () => {
    const warnings = validateResultRows([row({ resultType: "Text", numericValue: undefined, textValue: "" })]);
    expect(warnings).toContain("Missing text value for 'Hemoglobin'.");
  });

  it("flags duplicate parameter names", () => {
    const warnings = validateResultRows([row(), row()]);
    expect(warnings).toContain("Duplicate parameter entry: 'hemoglobin' appears 2 times.");
  });

  it("Phase 4H: does NOT flag two site-differentiated rows for the same requiresSite parameter as a duplicate", () => {
    const warnings = validateResultRows([
      row({ parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Positive" }, site: "Skin" }),
      row({ parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Negative" }, site: "Vaginal" }),
    ]);
    expect(warnings.some((w) => w.includes("Duplicate parameter entry"))).toBe(false);
  });

  it("Phase 4H: still flags two rows with the same parameter name AND the same site as a real duplicate", () => {
    const warnings = validateResultRows([
      row({ parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Positive" }, site: "Skin" }),
      row({ parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Negative" }, site: "Skin" }),
    ]);
    expect(warnings).toContain("Duplicate parameter entry: 'result' appears 2 times.");
  });
});

describe("interpretResult", () => {
  function numeric(value: number | null, low: number | null = 12, high: number | null = 16) {
    return interpretResult({ resultType: "Numeric", numericValue: value, textValue: null, rangeLow: low, rangeHigh: high, expectedNormalText: null });
  }

  function text(value: string | null, expected: string | null = "Negative") {
    return interpretResult({ resultType: "Text", numericValue: null, textValue: value, rangeLow: null, rangeHigh: null, expectedNormalText: expected });
  }

  it("returns Low for a value below the range", () => {
    expect(numeric(10)).toBe("Low");
  });

  it("returns Normal for a value within (and on) the range bounds", () => {
    expect(numeric(12)).toBe("Normal");
    expect(numeric(14)).toBe("Normal");
    expect(numeric(16)).toBe("Normal");
  });

  it("returns High for a value above the range", () => {
    expect(numeric(18)).toBe("High");
  });

  it("returns null when the lower bound is missing", () => {
    expect(numeric(14, null, 16)).toBeNull();
  });

  it("returns null when the upper bound is missing", () => {
    expect(numeric(14, 12, null)).toBeNull();
  });

  it("returns null when the range is missing entirely", () => {
    expect(numeric(14, null, null)).toBeNull();
  });

  it("returns null when the numeric value is missing, even with a valid range", () => {
    expect(numeric(null)).toBeNull();
  });

  it("returns Normal for a case-insensitive exact qualitative match", () => {
    expect(text("negative")).toBe("Normal");
    expect(text("NEGATIVE")).toBe("Normal");
    expect(text("  Negative  ")).toBe("Normal");
  });

  it("returns Abnormal for a qualitative mismatch", () => {
    expect(text("Trace")).toBe("Abnormal");
  });

  it("returns null for a qualitative result with no expected value configured", () => {
    expect(text("Straw", null)).toBeNull();
  });

  it("returns null when the text value is missing", () => {
    expect(text(null)).toBeNull();
  });
});
