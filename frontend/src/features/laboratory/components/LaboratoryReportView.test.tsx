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
    // #3 (Result/Unit split): Result and Unit are separate cells now, not
    // one combined "14 g/dL" string.
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("g/dL")).toBeInTheDocument();
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

  it("#9: interpretation (Assessment) is shown only when present", () => {
    const { rerender } = render(
      <LaboratoryReportView order={order({ results: [result({ interpretation: "Normal" })] })} />
    );
    expect(screen.getByText("✓ Normal")).toBeInTheDocument();

    rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: null })] })} />);
    expect(screen.queryByText("✓ Normal")).not.toBeInTheDocument();
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

  describe("Laboratory Report print redesign (five-column result table)", () => {
    it("1: renders all five required column headers", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      expect(screen.getByRole("columnheader", { name: "Test" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Result" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Unit" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Normal Values" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Assessment" })).toBeInTheDocument();
    });

    it("2: Result and Unit are separate cells, not one combined string", () => {
      render(
        <LaboratoryReportView
          order={order({ results: [result({ numericValue: 10, units: "10^3/L" })] })}
        />
      );
      expect(screen.getByText("10")).toBeInTheDocument();
      expect(screen.getByText("10^3/L")).toBeInTheDocument();
      expect(screen.queryByText("10 10^3/L")).not.toBeInTheDocument();
    });

    it("3: the persisted normal/reference range appears in the Normal Values column", () => {
      render(<LaboratoryReportView order={order({ results: [result({ normalRange: "70-105 mg/dL" })] })} />);
      expect(screen.getByText("70-105 mg/dL")).toBeInTheDocument();
    });

    it("4: the existing interpretation/status appears in Assessment, reusing the existing label text", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "High" })] })} />);
      expect(screen.getByText("↑ High")).toBeInTheDocument();
    });

    it("5: a result with no unit leaves the Unit cell blank rather than fabricating one", () => {
      render(<LaboratoryReportView order={order({ results: [result({ units: null })] })} />);
      const unitCell = screen.getByRole("columnheader", { name: "Unit" });
      const table = unitCell.closest("table") as HTMLTableElement;
      const dataRow = table.querySelectorAll("tbody tr")[0];
      expect(dataRow.children[2]).toHaveTextContent("");
    });

    it("6: a result with no assessment/interpretation leaves the Assessment cell blank", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: null })] })} />);
      const assessmentHeader = screen.getByRole("columnheader", { name: "Assessment" });
      const table = assessmentHeader.closest("table") as HTMLTableElement;
      const dataRow = table.querySelectorAll("tbody tr")[0];
      expect(dataRow.children[4]).toHaveTextContent("");
    });

    it("7: multiple laboratory sections each render their own five-column table", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "Urinalysis",
            template: {
              id: "t-ua", testName: "Urinalysis", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [
                param({ parameterName: "Color", resultType: "Text", section: "Physical Examination" }),
                param({ parameterName: "Protein", resultType: "Categorical", section: "Chemical Examination" }),
              ],
            },
            results: [
              result({ parameterName: "Color", resultType: "Text", textValue: "Straw" }),
              result({ parameterName: "Protein", resultType: "Categorical", structuredValue: { value: "Negative" } }),
            ],
          })}
        />
      );
      const headers = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
      expect(headers).toEqual(["Physical Examination", "Chemical Examination"]);
      // Each section still uses the same five-column structure, not a
      // different table shape per section.
      expect(screen.getAllByRole("columnheader", { name: "Assessment" })).toHaveLength(2);
    });

    it("8: prints the historical result's own persisted normal range, not one recalculated from the current template", () => {
      // The template parameter below carries no range at all (as if the
      // template's configured range changed/was removed after this result
      // was released) - the printed report must still show the value that
      // was actually persisted on the result at the time.
      render(
        <LaboratoryReportView
          order={order({
            template: {
              id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [param()],
            },
            results: [result({ normalRange: "12.0-16.0 (historical)" })],
          })}
        />
      );
      expect(screen.getByText("12.0-16.0 (historical)")).toBeInTheDocument();
    });

    it("10: the result table is styled to span the full available width (table-layout: fixed, width 100%)", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      expect(table.style.tableLayout).toBe("fixed");
      expect(table.className).toContain("w-full");
    });

    it("11: long test names and reference ranges wrap instead of breaking the table layout", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: null,
            results: [
              result({
                parameterName: "A Very Long Laboratory Parameter Name That Should Wrap Onto Multiple Lines",
                normalRange: "A very long reference range description that should also wrap cleanly",
              }),
            ],
          })}
        />
      );
      const cell = screen.getByText("A Very Long Laboratory Parameter Name That Should Wrap Onto Multiple Lines");
      expect(cell.className).toContain("whitespace-normal");
      expect(cell.className).toContain("break-words");
    });
  });

  describe("Laboratory Report print redesign, round 2 (clinic-approved compact reference layout)", () => {
    it("3: columns render in the required left-to-right order Test/Result/Unit/Normal Values/Assessment", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Assessment"]);
    });

    it("8: uses compact table styling - a dense navy header band and tight row padding, not the airier first-pass spacing", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const headerRow = screen.getByRole("columnheader", { name: "Test" }).closest("tr") as HTMLTableRowElement;
      expect(headerRow.className).toContain("bg-slate-800");
      expect(headerRow.className).toContain("text-white");

      const dataRow = screen.getByText("Hemoglobin").closest("tr") as HTMLTableRowElement;
      // Tight ~4px (py-1) row padding, not the previous py-1.5.
      expect(dataRow.querySelector("td")?.className).toContain("py-1 ");
      expect(dataRow.querySelector("td")?.className).not.toContain("py-1.5");
    });

    it("compact patient/order info block always shows a value (falls back to '-'), matching the approved reference rather than hiding empty fields", () => {
      render(<LaboratoryReportView order={order({ doctorName: null, results: [result()] })} />);
      expect(screen.getByText("Requesting Doctor")).toBeInTheDocument();
      // The InfoRow next to "Requesting Doctor" shows "-", not a blank gap.
      const row = screen.getByText("Requesting Doctor").closest("div") as HTMLDivElement;
      expect(row).toHaveTextContent("-");
    });

    it("renders the clinic-approved administrative note (system-generated, no signature required; ranges may vary)", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      expect(screen.getByText(/system-generated and does not require a signature/i)).toBeInTheDocument();
      expect(screen.getByText(/reference ranges may vary/i)).toBeInTheDocument();
    });

    it("tags each result row and section heading with the classes the print pagination CSS targets (report-row / section-heading)", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "Urinalysis",
            template: {
              id: "t-ua", testName: "Urinalysis", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [param({ parameterName: "Color", resultType: "Text", section: "Physical Examination" })],
            },
            results: [result({ parameterName: "Color", resultType: "Text", textValue: "Straw" })],
          })}
        />
      );
      expect(screen.getByRole("heading", { level: 3 }).className).toContain("section-heading");
      expect(screen.getByText("Straw").closest("tr")?.className).toContain("report-row");
    });
  });

  describe("Laboratory Report print redesign, round 3 (column/date clipping fix)", () => {
    it("1: the ASSESSMENT header renders the full word, not a truncated fragment", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const header = screen.getByRole("columnheader", { name: "Assessment" });
      expect(header).toHaveTextContent("Assessment");
      expect(screen.queryByText(/^Assessm$/)).not.toBeInTheDocument();
      expect(screen.queryByText(/…/)).not.toBeInTheDocument(); // no ellipsis character anywhere
    });

    it("2/3: the five column widths sum to exactly 100% (fit within the report width, no forced overflow)", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      const widths = Array.from(table.querySelectorAll("colgroup col")).map(
        (col) => Number((col as HTMLElement).style.width.replace("%", ""))
      );
      expect(widths).toHaveLength(5);
      expect(widths.reduce((sum, w) => sum + w, 0)).toBe(100);
      // ASSESSMENT is wide enough on its own that the single word "Assessment"
      // is not relying purely on mid-word breaking in the common case.
      expect(widths[4]).toBeGreaterThanOrEqual(18);
    });

    it("3: every header cell can wrap (whitespace-normal + break-words), the actual fix for a header word overflowing its fixed column", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      for (const header of screen.getAllByRole("columnheader")) {
        expect(header.className).toContain("whitespace-normal");
        expect(header.className).toContain("break-words");
      }
    });

    it("4/5: Collected/Completed/Released render the full timestamp in the DOM, never truncated or ellipsized", () => {
      render(
        <LaboratoryReportView
          order={order({
            results: [result()],
            collectedAt: "2026-08-22T09:59:00Z",
            completedAt: "2026-08-22T10:06:00Z",
            releasedAt: "2026-08-22T10:06:00Z",
          })}
        />
      );
      // "Completed" also appears as the default order's Status *value*, so
      // scope to the InfoRow *label* span specifically (the fixed-width
      // `w-[88px]` label, not the value span next to it).
      const labelRow = (label: string) =>
        screen
          .getAllByText(label)
          .find((el) => el.className.includes("w-[88px]"))
          ?.closest("div") as HTMLDivElement;
      const collectedRow = labelRow("Collected");
      const completedRow = labelRow("Completed");
      const releasedRow = labelRow("Released");
      // Full date + full time (with AM/PM), not a truncated prefix.
      expect(collectedRow.textContent).toMatch(/\d{2}\/\d{2}\/\d{4}.*\d{1,2}:\d{2}\s?(AM|PM)/i);
      expect(completedRow.textContent).toMatch(/\d{2}\/\d{2}\/\d{4}.*\d{1,2}:\d{2}\s?(AM|PM)/i);
      expect(releasedRow.textContent).toMatch(/\d{2}\/\d{2}\/\d{4}.*\d{1,2}:\d{2}\s?(AM|PM)/i);
      expect(collectedRow.textContent).not.toMatch(/…/);
    });

    it("the info-block value can wrap onto a second line instead of overflowing (min-w-0 on a flex item, the actual date-clipping fix)", () => {
      render(<LaboratoryReportView order={order({ results: [result()], doctorName: "Dr. A Very Long Requesting Doctor Full Name" })} />);
      const value = screen.getByText("Dr. A Very Long Requesting Doctor Full Name");
      expect(value.className).toContain("min-w-0");
      expect(value.className).toContain("whitespace-normal");
      expect(value.className).toContain("break-words");
    });

    it("6: a long test name wraps rather than forcing horizontal overflow", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: null,
            results: [result({ parameterName: "A Very Long Laboratory Parameter Name For The Assessment Column Fix Regression Test" })],
          })}
        />
      );
      const cell = screen.getByText("A Very Long Laboratory Parameter Name For The Assessment Column Fix Regression Test");
      expect(cell.className).toContain("whitespace-normal");
      expect(cell.className).toContain("break-words");
    });

    it("7: a long normal-values range wraps rather than forcing horizontal overflow", () => {
      render(
        <LaboratoryReportView
          order={order({ results: [result({ normalRange: "A very long persisted historical reference range description string" })] })}
        />
      );
      const cell = screen.getByText("A very long persisted historical reference range description string");
      expect(cell.className).toContain("whitespace-normal");
      expect(cell.className).toContain("break-words");
    });

    it("9: the table stays constrained to the report width (width: 100%, max-width: 100%, table-layout: fixed)", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      expect(table.className).toContain("w-full");
      expect(table.className).toContain("max-w-full");
      expect(table.style.tableLayout).toBe("fixed");
    });

    it("9: historical persisted values are still used unchanged (not recalculated) after the column/spacing fix", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: { id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z", parameters: [param()] },
            results: [result({ normalRange: "12.0-16.0 (historical)", units: "g/dL", interpretation: "Normal" })],
          })}
        />
      );
      expect(screen.getByText("12.0-16.0 (historical)")).toBeInTheDocument();
      expect(screen.getByText("g/dL")).toBeInTheDocument();
      expect(screen.getByText("✓ Normal")).toBeInTheDocument();
    });
  });
});
