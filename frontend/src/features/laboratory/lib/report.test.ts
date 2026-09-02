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
    // template.parameters is already backend-sorted by display_order - the
    // fixture lists "Second" first to prove buildReportRows follows
    // template order, not array-declaration order.
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

  // Client-reported "blank FLAG column" investigation: confirms
  // `buildReportRows` never reads/drops/recalculates `interpretation` - it
  // carries the whole `LaboratoryResult` object through untouched, so
  // whatever the backend computed (or didn't compute - see
  // `interpret_result`'s "never guess" contract) survives verbatim into
  // the row the report renders. Data-driven over every interpretation this
  // codebase produces, not just Low/High.
  it.each([
    ["Low", "Low"],
    ["High", "High"],
    ["Normal", "Normal"],
    ["Abnormal", "Abnormal"],
    [null, null],
  ] as const)("a Numeric result's interpretation (%s) passes through buildReportRows unchanged", (stored, expected) => {
    const o = order({ results: [result({ resultType: "Numeric", interpretation: stored })] });
    const rows = buildReportRows(o);
    expect(rows[0].results[0].interpretation).toBe(expected);
  });

  it("an untemplated order lists results as-is with no section", () => {
    const o = order({ template: null, templateId: null });
    const rows = buildReportRows(o);
    expect(rows).toEqual([{ parameterName: "Hemoglobin", section: null, results: [result()], options: null }]);
  });

  it("a templated row carries its parameter's configured options (needed to decide the qualitative matrix layout)", () => {
    const o = order({
      template: {
        id: "t", testName: "HBsAg", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [param({ parameterName: "HBsAg", resultType: "Categorical", options: ["Positive", "Negative"] })],
      },
      results: [result({ parameterName: "HBsAg", resultType: "Categorical", structuredValue: { value: "Positive" } })],
    });
    const rows = buildReportRows(o);
    expect(rows[0].options).toEqual(["Positive", "Negative"]);
  });

  it("#11: multiple site-specific results for the same parameter name stay independent, not collapsed", () => {
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
  it("#2: sectioned rows group contiguously in order, header shown once per run", () => {
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

  it("#1: no sections produces a single unheaded group", () => {
    const rows = buildReportRows(order());
    const groups = groupReportRowsBySection(rows);
    expect(groups).toEqual([{ section: null, rows }]);
  });
});

describe("reportResultValue", () => {
  it("#3: Numeric renders the numeric value", () => {
    expect(reportResultValue(result({ resultType: "Numeric", numericValue: 14 }))).toBe("14");
  });

  it("#4: Text renders textValue", () => {
    expect(reportResultValue(result({ resultType: "Text", textValue: "Straw" }))).toBe("Straw");
  });

  it("#5: Categorical reads structuredValue.value", () => {
    expect(reportResultValue(result({ resultType: "Categorical", structuredValue: { value: "O" } }))).toBe("O");
  });

  it("#6: Titer renders from textValue", () => {
    expect(reportResultValue(result({ resultType: "Titer", textValue: "1:160" }))).toBe("1:160");
  });

  it("#7: Microscopy renders from textValue, never an invented structured shape", () => {
    expect(reportResultValue(result({ resultType: "Microscopy", textValue: "Gram-positive cocci" }))).toBe("Gram-positive cocci");
  });

  it("returns null (not a fabricated placeholder) when the value is genuinely absent", () => {
    expect(reportResultValue(result({ resultType: "Numeric", numericValue: null }))).toBeNull();
  });
});

describe("isQualitativeCategoricalRow", () => {
  it("a Categorical row with configured options qualifies for the matrix layout", () => {
    const row = {
      parameterName: "NS1", section: null,
      results: [result({ resultType: "Categorical", structuredValue: { value: "Negative" } })],
      options: ["Positive", "Negative"],
    };
    expect(isQualitativeCategoricalRow(row)).toBe(true);
  });

  it("a Categorical row with NO configured options does not qualify (existing full-grid layout)", () => {
    const row = {
      parameterName: "Protein", section: null,
      results: [result({ resultType: "Categorical", structuredValue: { value: "Negative" } })],
      options: null,
    };
    expect(isQualitativeCategoricalRow(row)).toBe(false);
  });

  it("a Numeric row never qualifies, regardless of options", () => {
    const row = {
      parameterName: "Hemoglobin", section: null,
      results: [result({ resultType: "Numeric", numericValue: 14 })],
      options: null,
    };
    expect(isQualitativeCategoricalRow(row)).toBe(false);
  });

  it("a row with zero results does not qualify", () => {
    const row = { parameterName: "NS1", section: null, results: [], options: ["Positive", "Negative"] };
    expect(isQualitativeCategoricalRow(row)).toBe(false);
  });
});

describe("buildCategoryHeading", () => {
  it("renders the Hematology category as HEMATOLOGY TEST", () => {
    expect(buildCategoryHeading("Hematology")).toBe("HEMATOLOGY TEST");
  });

  it("renders a multi-word category (Blood Chemistry) as BLOOD CHEMISTRY TEST", () => {
    expect(buildCategoryHeading("Blood Chemistry")).toBe("BLOOD CHEMISTRY TEST");
  });

  it("renders Serology as SEROLOGY TEST", () => {
    expect(buildCategoryHeading("Serology")).toBe("SEROLOGY TEST");
  });

  it("does not double an already-present TEST suffix", () => {
    expect(buildCategoryHeading("Hematology Test")).toBe("HEMATOLOGY TEST");
    expect(buildCategoryHeading("HEMATOLOGY TEST")).toBe("HEMATOLOGY TEST");
  });

  it("returns null for a null, undefined, empty, or whitespace-only category", () => {
    expect(buildCategoryHeading(null)).toBeNull();
    expect(buildCategoryHeading(undefined)).toBeNull();
    expect(buildCategoryHeading("")).toBeNull();
    expect(buildCategoryHeading("   ")).toBeNull();
  });

  it("suppresses the heading when it would exactly repeat the adjacent matrix label", () => {
    expect(buildCategoryHeading("Serology", "SEROLOGY TEST")).toBeNull();
    expect(buildCategoryHeading("Serology", "Serology Test")).toBeNull();
  });

  it("still renders the heading when the adjacent label does not match", () => {
    expect(buildCategoryHeading("Serology", "Dengue Rapid Test")).toBe("SEROLOGY TEST");
  });

  it("ignores an empty/whitespace adjacent label and renders normally", () => {
    expect(buildCategoryHeading("Hematology", "")).toBe("HEMATOLOGY TEST");
    expect(buildCategoryHeading("Hematology", "   ")).toBe("HEMATOLOGY TEST");
    expect(buildCategoryHeading("Hematology", null)).toBe("HEMATOLOGY TEST");
  });
});

describe("buildAgeSexLine", () => {
  it("formats a Male patient with a known age as '22 yrs / M'", () => {
    expect(buildAgeSexLine(22, "Male")).toBe("22 yrs / M");
  });

  it("formats a Female patient with a known age as '35 yrs / F'", () => {
    expect(buildAgeSexLine(35, "Female")).toBe("35 yrs / F");
  });

  it("maps an Other sex value to 'O'", () => {
    expect(buildAgeSexLine(40, "Other")).toBe("40 yrs / O");
  });

  it("renders '- / M' when age is missing but sex is known", () => {
    expect(buildAgeSexLine(null, "Male")).toBe("- / M");
    expect(buildAgeSexLine(undefined, "Male")).toBe("- / M");
  });

  it("renders '22 yrs / -' when sex is missing but age is known", () => {
    expect(buildAgeSexLine(22, null)).toBe("22 yrs / -");
    expect(buildAgeSexLine(22, undefined)).toBe("22 yrs / -");
  });

  it("collapses to a single '-' when both age and sex are missing - never '- / -'", () => {
    expect(buildAgeSexLine(null, null)).toBe("-");
    expect(buildAgeSexLine(undefined, undefined)).toBe("-");
  });

  it("age 0 (a newborn) is a real value, not treated as missing", () => {
    expect(buildAgeSexLine(0, "Female")).toBe("0 yrs / F");
  });
});
