import { describe, expect, it } from "vitest";
import { nextActionFor, validateResultRows } from "@/features/laboratory/types";
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
});
