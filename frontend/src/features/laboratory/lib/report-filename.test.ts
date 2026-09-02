import { describe, expect, it } from "vitest";
import { buildLaboratoryReportFilename } from "./report-filename";

describe("buildLaboratoryReportFilename", () => {
  it("builds <Patient_Name>-<last 4 order digits>.pdf, spaces replaced with underscores", () => {
    expect(buildLaboratoryReportFilename("Paul Test", "ORD-20260901-000007")).toBe("Paul_Test-0007.pdf");
  });

  it("a second, independent example (client-provided)", () => {
    expect(buildLaboratoryReportFilename("Richard Test", "ORD-20260901-000002")).toBe("Richard_Test-0002.pdf");
  });

  it("preserves leading zeroes in the last-4-digits suffix", () => {
    expect(buildLaboratoryReportFilename("Jane Doe", "ORD-20260101-000009")).toBe("Jane_Doe-0009.pdf");
    expect(buildLaboratoryReportFilename("Jane Doe", "ORD-20260101-000090")).toBe("Jane_Doe-0090.pdf");
  });

  it("a name with multiple consecutive spaces collapses to a single underscore per gap, not one per space", () => {
    expect(buildLaboratoryReportFilename("Paul   Test", "ORD-20260901-000007")).toBe("Paul_Test-0007.pdf");
  });

  it("a name with leading/trailing whitespace is trimmed before building the filename", () => {
    expect(buildLaboratoryReportFilename("  Paul Test  ", "ORD-20260901-000007")).toBe("Paul_Test-0007.pdf");
  });

  it("strips filesystem-invalid characters (< > : \" / \\ | ? *) from the patient name", () => {
    expect(buildLaboratoryReportFilename('Paul/Test:"Case"*?', "ORD-20260901-000007")).toBe("PaulTestCase-0007.pdf");
  });

  it("a three-part name with normal spacing produces exactly two underscores", () => {
    expect(buildLaboratoryReportFilename("Maria Dela Cruz", "ORD-20260901-000123")).toBe("Maria_Dela_Cruz-0123.pdf");
  });

  it("a missing/null order number omits the digit suffix entirely - never a fabricated -0000", () => {
    expect(buildLaboratoryReportFilename("Paul Test", null)).toBe("Paul_Test.pdf");
  });

  it("an order number with no digits at all also omits the suffix", () => {
    expect(buildLaboratoryReportFilename("Paul Test", "N/A")).toBe("Paul_Test.pdf");
  });

  it("an empty-string order number omits the suffix", () => {
    expect(buildLaboratoryReportFilename("Paul Test", "")).toBe("Paul_Test.pdf");
  });

  it("a missing/null patient name falls back to a generic, non-blank filename rather than an empty segment", () => {
    expect(buildLaboratoryReportFilename(null, "ORD-20260901-000007")).toBe("Laboratory_Report-0007.pdf");
  });

  it("an empty-string patient name also falls back to the generic filename", () => {
    expect(buildLaboratoryReportFilename("", "ORD-20260901-000007")).toBe("Laboratory_Report-0007.pdf");
  });

  it("a name that is ENTIRELY invalid characters falls back to the generic filename, not a bare '-0007.pdf'", () => {
    expect(buildLaboratoryReportFilename('///???', "ORD-20260901-000007")).toBe("Laboratory_Report-0007.pdf");
  });

  it("always ends in .pdf", () => {
    expect(buildLaboratoryReportFilename("Paul Test", "ORD-20260901-000007")).toMatch(/\.pdf$/);
    expect(buildLaboratoryReportFilename(null, null)).toMatch(/\.pdf$/);
  });

  it("never contains a filesystem-invalid character anywhere in the result, regardless of input", () => {
    const result = buildLaboratoryReportFilename('Weird<>:"/\\|?*Name', "ORD-20260901-000007");
    expect(result).not.toMatch(/[<>:"/\\|?*]/);
  });
});
