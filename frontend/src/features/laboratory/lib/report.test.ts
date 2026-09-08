import { describe, expect, it } from "vitest";
import {
  buildAgeSexLine,
  buildCategoryHeading,
  buildReportRows,
  groupReportRowsBySection,
  isQualitativeCategoricalRow,
  reportResultValue,
} from "./report";
import type { LaboratoryOrder, LaboratoryResult, LaboratoryTemplateParameter } from "@/features/laboratory/types";

function result(overrides: Partial<LaboratoryResult> = {}): LaboratoryResult {
  return {
    id: "res-1", parameterName: "Hemoglobin", resultType: "Numeric", numericValue: 14, textValue: null,
    normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
    enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null, site: null,
    ...overrides,
  };
}

function param(overrides: Partial<LaboratoryTemplateParameter> = {}): LaboratoryTemplateParameter {
  return { parameterName: "Hemoglobin", resultType: "Numeric", displayOrder: 0, ...overrides };
}

function order(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-1", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: null, patientId: "patient-1", patientName: "Juan Dela Cruz", patientAge: null, patientSex: null, doctorId: null, doctorName: null,
    templateId: "template-1",
    template: {
      id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0,
      turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
      parameters: [param()],
    },
    testType: "CBC", priority: null, status: "Completed", scheduledDate: null, collectedAt: null,
    collectedBy: null, processingStartedAt: null, completedAt: "2026-01-02T00:00:00Z", releasedAt: null,
    releasedBy: null, invoiceItemId: null, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [result()], attachments: [], clinicName: "Test Clinic",
    ...overrides,
  };
}

describe("buildReportRows", () => {
  it("#1: a template with no sections produces rows with section=null, no section invented", () => {
    const rows = buildReportRows(order());
    expect(rows).toEqual([{ parameterName: "Hemoglobin", section: null, results: [result()], options: null }]);
  });

  it("#2: rows follow template display order, not result array order", () => {
    const o = order({
      template: {
        id: "t", testName: "Panel", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [
          param({ parameterName: "Second", displayOrder: 1 }),
          param({ parameterName: "First", displayOrder: 0 }),
        ],
      },
      results: [
        result({ id: "r1", parameterName: "First" }),
        result({ id: "r2", parameterName: "Second" }),
      ],
    });
    const rows = buildReportRows(o);
    expect(rows.map((r) => r.parameterName)).toEqual(["Second", "First"]);
  });

  it("a template parameter with no submitted result is excluded (never invents a blank row)", () => {
    const o = order({
      template: {
        id: "t", testName: "Panel", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [param({ parameterName: "Hemoglobin" }), param({ parameterName: "Never Entered" })],
      },
    });
    const rows = buildReportRows(o);
    expect(rows.map((r) => r.parameterName)).toEqual(["Hemoglobin"]);
  });

  it.each([
    ["Low", "Low"], ["High", "High"], ["Normal", "Normal"], ["Abnormal", "Abnormal"], [null, null],
  ] as const)("a Numeric result's interpretation (%s) passes through buildReportRows unchanged", (stored, expected) => {
    const o = order({ results: [result({ resultType: "Numeric", interpretation: stored })] });
    expect(buildReportRows(o)[0].results[0].interpretation).toBe(expected);
  });

  it("an untemplated order lists results as-is with no section", () => {
    const o = order({ template: null, templateId: null });
    expect(buildReportRows(o)).toEqual([{ parameterName: "Hemoglobin", section: null, results: [result()], options: null }]);
  });

  it("a templated row carries its parameter's configured options", () => {
    const o = order({
      template: {
        id: "t", testName: "HBsAg", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [param({ parameterName: "HBsAg", resultType: "Categorical", options: ["Positive", "Negative"] })],
      },
      results: [result({ parameterName: "HBsAg", resultType: "Categorical", structuredValue: { value: "Positive" } })],
    });
    expect(buildReportRows(o)[0].options).toEqual(["Positive", "Negative"]);
  });

  it("multiple site-specific results for the same parameter name stay independent", () => {
    const o = order({
      template: {
        id: "t", testName: "KOH Mount", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [param({ parameterName: "Result", resultType: "Categorical", requiresSite: true })],
      },
      results: [
        result({ id: "r-skin", parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Positive" }, site: "Skin" }),
        result({ id: "r-vaginal", parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Negative" }, site: "Vaginal" }),
      ],
    });
    const rows = buildReportRows(o);
    expect(rows).toHaveLength(1);
    expect(rows[0].results).toHaveLength(2);
    expect(rows[0].results.map((r) => r.site)).toEqual(["Skin", "Vaginal"]);
  });
});

describe("groupReportRowsBySection", () => {
  it("sectioned rows group contiguously in order, header shown once per run", () => {
    const rows = [
      { parameterName: "Color", section: "Physical", results: [result({ parameterName: "Color" })] },
      { parameterName: "pH", section: "Physical", results: [result({ parameterName: "pH" })] },
      { parameterName: "Protein", section: "Chemical", results: [result({ parameterName: "Protein" })] },
    ];
    const groups = groupReportRowsBySection(rows);
    expect(groups.map((g) => g.section)).toEqual(["Physical", "Chemical"]);
    expect(groups[0].rows).toHaveLength(2);
    expect(groups[1].rows).toHaveLength(1);
  });

  it("no sections produces a single unheaded group", () => {
    const rows = buildReportRows(order());
    expect(groupReportRowsBySection(rows)).toEqual([{ section: null, rows }]);
  });
});

describe("reportResultValue", () => {
  it("Numeric renders the numeric value", () => expect(reportResultValue(result({ resultType: "Numeric", numericValue: 14 }))).toBe("14"));
  it("Text renders textValue", () => expect(reportResultValue(result({ resultType: "Text", textValue: "Straw" }))).toBe("Straw"));
  it("Categorical reads structuredValue.value", () => expect(reportResultValue(result({ resultType: "Categorical", structuredValue: { value: "O" } }))).toBe("O"));
  it("Titer renders from textValue", () => expect(reportResultValue(result({ resultType: "Titer", textValue: "1:160" }))).toBe("1:160"));
  it("Microscopy renders from textValue", () => expect(reportResultValue(result({ resultType: "Microscopy", textValue: "Gram-positive cocci" }))).toBe("Gram-positive cocci"));
  it("returns null when the value is genuinely absent", () => expect(reportResultValue(result({ resultType: "Numeric", numericValue: null }))).toBeNull());
});

describe("isQualitativeCategoricalRow", () => {
  it("qualifies a Positive categorical result even without configured options", () => {
    const row = { parameterName: "NS1", section: null, results: [result({ resultType: "Categorical", structuredValue: { value: "Positive" } })], options: null };
    expect(isQualitativeCategoricalRow(row)).toBe(true);
  });

  it("qualifies a Negative categorical result with configured options", () => {
    const row = { parameterName: "IgM", section: null, results: [result({ resultType: "Categorical", structuredValue: { value: "Negative" } })], options: ["Positive", "Negative"] };
    expect(isQualitativeCategoricalRow(row)).toBe(true);
  });

  it("does not qualify other categorical values such as blood type", () => {
    const row = { parameterName: "Blood Type", section: null, results: [result({ resultType: "Categorical", structuredValue: { value: "O" } })], options: ["A", "B", "AB", "O"] };
    expect(isQualitativeCategoricalRow(row)).toBe(false);
  });

  it("a Numeric row never qualifies", () => {
    const row = { parameterName: "Hemoglobin", section: null, results: [result({ resultType: "Numeric", numericValue: 14 })], options: null };
    expect(isQualitativeCategoricalRow(row)).toBe(false);
  });

  it("a row with zero results does not qualify", () => {
    const row = { parameterName: "NS1", section: null, results: [], options: ["Positive", "Negative"] };
    expect(isQualitativeCategoricalRow(row)).toBe(false);
  });
});

describe("buildCategoryHeading", () => {
  it("renders the Hematology category as HEMATOLOGY TEST", () => expect(buildCategoryHeading("Hematology")).toBe("HEMATOLOGY TEST"));
  it("renders a multi-word category as BLOOD CHEMISTRY TEST", () => expect(buildCategoryHeading("Blood Chemistry")).toBe("BLOOD CHEMISTRY TEST"));
  it("renders Serology as SEROLOGY TEST", () => expect(buildCategoryHeading("Serology")).toBe("SEROLOGY TEST"));
  it("does not double an already-present TEST suffix", () => {
    expect(buildCategoryHeading("Hematology Test")).toBe("HEMATOLOGY TEST");
    expect(buildCategoryHeading("HEMATOLOGY TEST")).toBe("HEMATOLOGY TEST");
  });
  it("returns null for an empty category", () => {
    expect(buildCategoryHeading(null)).toBeNull(); expect(buildCategoryHeading(undefined)).toBeNull();
    expect(buildCategoryHeading("")).toBeNull(); expect(buildCategoryHeading("   ")).toBeNull();
  });
  it("suppresses an exact adjacent matrix duplicate", () => {
    expect(buildCategoryHeading("Serology", "SEROLOGY TEST")).toBeNull();
    expect(buildCategoryHeading("Serology", "Serology Test")).toBeNull();
  });
  it("still renders when adjacent label differs", () => expect(buildCategoryHeading("Serology", "Dengue Rapid Test")).toBe("SEROLOGY TEST"));
  it("renders normally with empty adjacent label", () => {
    expect(buildCategoryHeading("Hematology", "")).toBe("HEMATOLOGY TEST");
    expect(buildCategoryHeading("Hematology", "   ")).toBe("HEMATOLOGY TEST");
    expect(buildCategoryHeading("Hematology", null)).toBe("HEMATOLOGY TEST");
  });
});

describe("buildAgeSexLine", () => {
  it("formats a Male patient with a known age as '22 yrs / M'", () => expect(buildAgeSexLine(22, "Male")).toBe("22 yrs / M"));
  it("formats a Female patient with a known age as '35 yrs / F'", () => expect(buildAgeSexLine(35, "Female")).toBe("35 yrs / F"));
  it("maps Other to O", () => expect(buildAgeSexLine(40, "Other")).toBe("40 yrs / O"));
  it("renders '- / M' when age is missing", () => { expect(buildAgeSexLine(null, "Male")).toBe("- / M"); expect(buildAgeSexLine(undefined, "Male")).toBe("- / M"); });
  it("renders '22 yrs / -' when sex is missing", () => { expect(buildAgeSexLine(22, null)).toBe("22 yrs / -"); expect(buildAgeSexLine(22, undefined)).toBe("22 yrs / -"); });
  it("collapses to '-' when both are missing", () => { expect(buildAgeSexLine(null, null)).toBe("-"); expect(buildAgeSexLine(undefined, undefined)).toBe("-"); });
  it("age 0 is a real value", () => expect(buildAgeSexLine(0, "Female")).toBe("0 yrs / F"));
});
