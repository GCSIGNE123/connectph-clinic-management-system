import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LaboratoryReportView } from "./LaboratoryReportView";
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
    queueNumber: null, patientId: "patient-1", patientName: "Juan Dela Cruz", doctorId: "doc-1", doctorName: "Jose Rizal",
    templateId: "template-1",
    template: {
      id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0,
      turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
      parameters: [param()],
    },
    testType: "CBC", priority: null, status: "Completed", scheduledDate: null, collectedAt: "2026-01-01T08:00:00Z",
    collectedBy: null, processingStartedAt: null, completedAt: "2026-01-01T09:00:00Z", releasedAt: null,
    releasedBy: null, invoiceItemId: null, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [result()], attachments: [], clinicName: "Test Clinic",
    ...overrides,
  };
}

describe("LaboratoryReportView", () => {
  it("#1/#12: CBC (no sections) renders header info, clinic name, and the numeric result with unit/range", () => {
    render(
      <LaboratoryReportView
        order={order({
          results: [result({ units: "g/dL", normalRange: "12.0-16.0" })],
        })}
      />
    );
    expect(screen.getByText("Test Clinic")).toBeInTheDocument();
    expect(screen.getByText("Laboratory Report")).toBeInTheDocument();
    expect(screen.getByText("Juan Dela Cruz")).toBeInTheDocument();
    expect(screen.getByText("Hemoglobin")).toBeInTheDocument();
    expect(screen.getByText("14 g/dL")).toBeInTheDocument();
    expect(screen.getByText("12.0-16.0")).toBeInTheDocument();
  });

  it("#13: Blood Typing (Categorical) renders structuredValue.value", () => {
    render(
      <LaboratoryReportView
        order={order({
          testType: "Blood Typing",
          template: {
            id: "t-bt", testName: "Blood Typing", testCategory: null, specimenType: null, defaultPrice: 0,
            turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
            parameters: [param({ parameterName: "ABO Group", resultType: "Categorical" })],
          },
          results: [result({ parameterName: "ABO Group", resultType: "Categorical", structuredValue: { value: "O" } })],
        })}
      />
    );
    expect(screen.getByText("ABO Group")).toBeInTheDocument();
    expect(screen.getByText("O")).toBeInTheDocument();
  });

  it("#2/#14: Urinalysis-style sectioned template renders section headers in template order", () => {
    render(
      <LaboratoryReportView
        order={order({
          testType: "Urinalysis",
          template: {
            id: "t-ua", testName: "Urinalysis", testCategory: null, specimenType: null, defaultPrice: 0,
            turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
            parameters: [
              param({ parameterName: "Color", resultType: "Text", section: "Physical Examination" }),
              param({ parameterName: "pH", resultType: "Numeric", section: "Physical Examination" }),
              param({ parameterName: "Protein", resultType: "Categorical", section: "Chemical Examination" }),
            ],
          },
          results: [
            result({ parameterName: "Color", resultType: "Text", textValue: "Straw" }),
            result({ parameterName: "pH", resultType: "Numeric", numericValue: 6.0 }),
            result({ parameterName: "Protein", resultType: "Categorical", structuredValue: { value: "Negative" } }),
          ],
        })}
      />
    );
    const headers = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headers).toEqual(["Physical Examination", "Chemical Examination"]);
  });

  it("#15: a Phase 4C/4D-style template (Titer + multi-site Categorical) renders both generically", () => {
    render(
      <LaboratoryReportView
        order={order({
          testType: "KOH Mount",
          template: {
            id: "t-koh", testName: "KOH Mount", testCategory: null, specimenType: null, defaultPrice: 0,
            turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
            parameters: [
              param({ parameterName: "Titer", resultType: "Titer" }),
              param({ parameterName: "Result", resultType: "Categorical", requiresSite: true }),
            ],
          },
          results: [
            result({ id: "r-titer", parameterName: "Titer", resultType: "Titer", textValue: "1:160" }),
            result({ id: "r-skin", parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Positive" }, site: "Skin" }),
            result({ id: "r-vaginal", parameterName: "Result", resultType: "Categorical", structuredValue: { value: "Negative" }, site: "Vaginal" }),
          ],
        })}
      />
    );
    expect(screen.getByText("1:160")).toBeInTheDocument();
    // #10/#11: both sites shown, independently, with their own value.
    expect(screen.getByText("(Skin)")).toBeInTheDocument();
    expect(screen.getByText("(Vaginal)")).toBeInTheDocument();
    expect(screen.getByText("Positive")).toBeInTheDocument();
    expect(screen.getByText("Negative")).toBeInTheDocument();
  });

  it("#9: interpretation is shown only when present", () => {
    const { rerender } = render(
      <LaboratoryReportView order={order({ results: [result({ interpretation: "Normal" })] })} />
    );
    expect(screen.getByText(/normal/i)).toBeInTheDocument();

    rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: null })] })} />);
    expect(screen.queryByText(/normal/i)).not.toBeInTheDocument();
  });

  it("#8: reference range is shown only when configured", () => {
    const { rerender } = render(
      <LaboratoryReportView order={order({ results: [result({ normalRange: "12.0-16.0" })] })} />
    );
    expect(screen.getByText("12.0-16.0")).toBeInTheDocument();

    rerender(<LaboratoryReportView order={order({ results: [result({ normalRange: null })] })} />);
    expect(screen.queryByText("12.0-16.0")).not.toBeInTheDocument();
  });

  it("#16: rendering is driven entirely by generic metadata, not a test-name check - an unrecognized synthetic test name renders identically", () => {
    render(
      <LaboratoryReportView
        order={order({
          testType: "Completely Synthetic Future Test",
          template: {
            id: "t-synthetic", testName: "Completely Synthetic Future Test", testCategory: null, specimenType: null,
            defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
            parameters: [param({ parameterName: "Made Up Parameter", resultType: "Text" })],
          },
          results: [result({ parameterName: "Made Up Parameter", resultType: "Text", textValue: "Some value" })],
        })}
      />
    );
    expect(screen.getByText("Made Up Parameter")).toBeInTheDocument();
    expect(screen.getByText("Some value")).toBeInTheDocument();
  });

  it("renders 'No results entered yet.' rather than an empty report for an order with no results", () => {
    render(<LaboratoryReportView order={order({ results: [] })} />);
    expect(screen.getByText(/no results entered yet/i)).toBeInTheDocument();
  });
});
