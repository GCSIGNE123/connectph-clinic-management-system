import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaboratoryReportView } from "./LaboratoryReportView";
import type { LaboratoryOrder, LaboratoryResult, LaboratoryTemplateParameter } from "@/features/laboratory/types";

URL.createObjectURL = vi.fn(() => "blob:mock-url");
URL.revokeObjectURL = vi.fn();

const mockFetchBlob = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiFetchBlob: (...args: unknown[]) => mockFetchBlob(...args),
}));

vi.mock("@/lib/api-url", () => ({
  resolveMediaUrl: (path: string | null | undefined) => (path ? `http://api.test${path}` : null),
}));

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

  it("#9: the Flag column shows 'L' only for a Low interpretation, blank for Normal/missing", () => {
    const { rerender } = render(
      <LaboratoryReportView order={order({ results: [result({ interpretation: "Low" })] })} />
    );
    expect(screen.getByText("L")).toBeInTheDocument();

    rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: "Normal" })] })} />);
    expect(screen.queryByText("L")).not.toBeInTheDocument();
    expect(screen.queryByText("H")).not.toBeInTheDocument();

    rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: null })] })} />);
    expect(screen.queryByText("L")).not.toBeInTheDocument();
    expect(screen.queryByText("H")).not.toBeInTheDocument();
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
      expect(screen.getByRole("columnheader", { name: "Flag" })).toBeInTheDocument();
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

    it("4: the existing interpretation/status is normalized to a bare Flag character - High prints as 'H', not the full word/arrow", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "High" })] })} />);
      expect(screen.getByText("H")).toBeInTheDocument();
      expect(screen.queryByText("↑ High")).not.toBeInTheDocument();
      expect(screen.queryByText("High")).not.toBeInTheDocument();
    });

    it("5: a result with no unit leaves the Unit cell blank rather than fabricating one", () => {
      render(<LaboratoryReportView order={order({ results: [result({ units: null })] })} />);
      const unitCell = screen.getByRole("columnheader", { name: "Unit" });
      const table = unitCell.closest("table") as HTMLTableElement;
      const dataRow = table.querySelectorAll("tbody tr")[0];
      expect(dataRow.children[2]).toHaveTextContent("");
    });

    it("6: a result with no interpretation leaves the Flag cell blank", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: null })] })} />);
      const flagHeader = screen.getByRole("columnheader", { name: "Flag" });
      const table = flagHeader.closest("table") as HTMLTableElement;
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
      expect(screen.getAllByRole("columnheader", { name: "Flag" })).toHaveLength(2);
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
    it("3: columns render in the required left-to-right order Test/Result/Unit/Normal Values/Flag", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
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

    it("renders the clinic-approved administrative note (system-generated; ranges may vary)", () => {
      // Round 6: "does not require a signature" was removed from this note
      // now that the report actually supports real Med Tech/Pathologist
      // signatures - see the Round 6 implementation report.
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      expect(screen.getByText(/this report is system-generated/i)).toBeInTheDocument();
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
    it("1: the FLAG header renders the full word, not a truncated fragment", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const header = screen.getByRole("columnheader", { name: "Flag" });
      expect(header).toHaveTextContent("Flag");
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
      // FLAG only ever holds a single character, so it's deliberately the
      // narrowest column now (round 4: Assessment -> Flag).
      expect(widths[4]).toBeLessThanOrEqual(10);
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
            results: [result({ parameterName: "A Very Long Laboratory Parameter Name For The Flag Column Fix Regression Test" })],
          })}
        />
      );
      const cell = screen.getByText("A Very Long Laboratory Parameter Name For The Flag Column Fix Regression Test");
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
            results: [result({ normalRange: "12.0-16.0 (historical)", units: "g/dL", interpretation: "Low" })],
          })}
        />
      );
      expect(screen.getByText("12.0-16.0 (historical)")).toBeInTheDocument();
      expect(screen.getByText("g/dL")).toBeInTheDocument();
      expect(screen.getByText("L")).toBeInTheDocument();
    });
  });

  describe("Laboratory Report print redesign, round 4 (Assessment -> Flag)", () => {
    it("1: the printed header is exactly 'Flag', not 'Assessment'", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      expect(screen.getByRole("columnheader", { name: "Flag" })).toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Assessment" })).not.toBeInTheDocument();
    });

    it("2: a below-normal-range result renders 'L'", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "Low" })] })} />);
      expect(screen.getByText("L")).toBeInTheDocument();
    });

    it("3: an above-normal-range result renders 'H'", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "High" })] })} />);
      expect(screen.getByText("H")).toBeInTheDocument();
    });

    it("4: a within-range (Normal) result renders blank - no letter, no word", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "Normal" })] })} />);
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
      expect(screen.queryByText("Normal")).not.toBeInTheDocument();
      expect(screen.queryByText("✓ Normal")).not.toBeInTheDocument();
    });

    it("5: the 'H' character carries a color class (Round 7 changes this to blue - see the round 7 describe block below)", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "High" })] })} />);
      expect(screen.getByText("H").className).toMatch(/text-(destructive|primary)/);
    });

    it("6: the 'L' character carries the red/destructive color class", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "Low" })] })} />);
      expect(screen.getByText("L").className).toContain("text-destructive");
    });

    it("7: a Normal row's Flag cell contains no flag text at all", () => {
      render(<LaboratoryReportView order={order({ results: [result({ parameterName: "Hemoglobin", interpretation: "Normal" })] })} />);
      const flagHeader = screen.getByRole("columnheader", { name: "Flag" });
      const table = flagHeader.closest("table") as HTMLTableElement;
      const dataRow = screen.getByText("Hemoglobin").closest("tr") as HTMLTableRowElement;
      expect(table.contains(dataRow)).toBe(true);
      expect(dataRow.children[4]).toHaveTextContent("");
    });

    it("8: only the Flag character is red - the Result value itself carries no destructive color class", () => {
      render(
        <LaboratoryReportView
          order={order({ template: null, results: [result({ parameterName: "Platelet Count", numericValue: 149, interpretation: "Low" })] })}
        />
      );
      const resultCell = screen.getByText("149");
      expect(resultCell.className).not.toContain("text-destructive");
    });

    it("9: only the Flag character is red - the Normal Values (reference range) cell carries no destructive color class", () => {
      render(
        <LaboratoryReportView
          order={order({ template: null, results: [result({ parameterName: "Platelet Count", normalRange: "150-400", interpretation: "Low" })] })}
        />
      );
      const rangeCell = screen.getByText("150-400");
      expect(rangeCell.className).not.toContain("text-destructive");
    });

    it("10: only the Flag character is red - the entire row is not colored red", () => {
      render(
        <LaboratoryReportView
          order={order({ template: null, results: [result({ parameterName: "Platelet Count", numericValue: 149, interpretation: "Low" })] })}
        />
      );
      const row = screen.getByText("Platelet Count").closest("tr") as HTMLTableRowElement;
      expect(row.className).not.toContain("text-destructive");
      expect(row.className).not.toContain("bg-red");
      expect(row.className).not.toContain("bg-destructive");
    });

    it("11: the five columns remain exactly Test/Result/Unit/Normal Values/Flag", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
    });

    it("12: an ad-hoc (non-template) result with no range/interpretation still prints, with a blank Flag rather than a fabricated one", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: null,
            results: [result({ parameterName: "Ad-hoc Parameter", normalRange: null, interpretation: null })],
          })}
        />
      );
      const row = screen.getByText("Ad-hoc Parameter").closest("tr") as HTMLTableRowElement;
      expect(row).toBeInTheDocument();
      expect(row.children[4]).toHaveTextContent("");
    });

    it("13: historical persisted normal range/units continue to print unchanged under the Flag column", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: { id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z", parameters: [param()] },
            results: [result({ normalRange: "12.0-16.0 (historical)", units: "g/dL", interpretation: "High" })],
          })}
        />
      );
      expect(screen.getByText("12.0-16.0 (historical)")).toBeInTheDocument();
      expect(screen.getByText("g/dL")).toBeInTheDocument();
      expect(screen.getByText("H")).toBeInTheDocument();
    });

    it("14: the table still fits the report width with zero forced overflow after rebalancing for the narrower Flag column", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      const widths = Array.from(table.querySelectorAll("colgroup col")).map(
        (col) => Number((col as HTMLElement).style.width.replace("%", ""))
      );
      expect(widths.reduce((sum, w) => sum + w, 0)).toBe(100);
      expect(table.className).toContain("w-full");
      expect(table.className).toContain("max-w-full");
    });

    it("a persisted 'Abnormal' (non-directional, qualitative) interpretation on a Text result prints blank rather than guessing H or L", () => {
      render(<LaboratoryReportView order={order({ results: [result({ resultType: "Text", interpretation: "Abnormal" })] })} />);
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();
      expect(screen.queryByText("Abnormal")).not.toBeInTheDocument();
    });
  });

  // --- HBsAg PDF Flag fix: a Categorical Positive/Negative result's
  // `Abnormal`/`Normal` interpretation now maps to a distinct "A" flag
  // (Categorical only) - separate from L/H (numeric direction, unchanged)
  // and separate from Text's own still-blank `Abnormal` convention above.
  describe("Laboratory Report print redesign - Categorical Positive/Negative Flag ('A')", () => {
    it("1: a Categorical result with Abnormal interpretation (e.g. HBsAg Positive) renders 'A'", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: null,
            results: [result({ parameterName: "HBsAg", resultType: "Categorical", structuredValue: { value: "Positive" }, interpretation: "Abnormal" })],
          })}
        />
      );
      expect(screen.getByText("A")).toBeInTheDocument();
    });

    it("2: the 'A' flag carries the red/destructive color class, same urgency tier as 'L'", () => {
      render(
        <LaboratoryReportView
          order={order({ results: [result({ resultType: "Categorical", structuredValue: { value: "Positive" }, interpretation: "Abnormal" })] })}
        />
      );
      expect(screen.getByText("A").className).toContain("text-destructive");
    });

    it("3: a Categorical result with Normal interpretation (e.g. HBsAg Negative) renders blank, not 'A'", () => {
      render(
        <LaboratoryReportView
          order={order({
            template: null,
            results: [result({ parameterName: "HBsAg", resultType: "Categorical", structuredValue: { value: "Negative" }, interpretation: "Normal" })],
          })}
        />
      );
      expect(screen.queryByText("A")).not.toBeInTheDocument();
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
    });

    it("4: the FLAG column never prints the word 'Abnormal' for a Categorical result - only the single character 'A'", () => {
      render(
        <LaboratoryReportView
          order={order({ results: [result({ resultType: "Categorical", structuredValue: { value: "Positive" }, interpretation: "Abnormal" })] })}
        />
      );
      expect(screen.queryByText("Abnormal")).not.toBeInTheDocument();
      expect(screen.getByText("A")).toBeInTheDocument();
    });

    it("5: Numeric Low/High/Normal flags are unaffected by the Categorical 'A' addition", () => {
      const { rerender } = render(<LaboratoryReportView order={order({ results: [result({ resultType: "Numeric", interpretation: "Low" })] })} />);
      expect(screen.getByText("L")).toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();

      rerender(<LaboratoryReportView order={order({ results: [result({ resultType: "Numeric", interpretation: "High" })] })} />);
      expect(screen.getByText("H")).toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();

      rerender(<LaboratoryReportView order={order({ results: [result({ resultType: "Numeric", interpretation: "Normal" })] })} />);
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();
    });

    it("6: a Text result's Abnormal interpretation still renders blank, not 'A' - the Round 4 Text convention is untouched", () => {
      render(<LaboratoryReportView order={order({ results: [result({ resultType: "Text", interpretation: "Abnormal" })] })} />);
      expect(screen.queryByText("A")).not.toBeInTheDocument();
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
    });
  });

  // --- Client-reported "FLAG column is blank on a standard report" bug
  // investigation. Root cause (see the implementation report): NOT a code
  // defect in this pipeline - `interpret_result` (backend), the API
  // response, `report.ts`, and `FlagText` all already round-trip
  // Low/High/Normal correctly (proven by the pre-existing Round 4 suite
  // above, still 100% passing). The live blank flags were traced to one
  // specific lab template whose parameters had only the legacy free-text
  // `normal_range` string configured, with no structured `range_low`/
  // `range_high` - `interpret_result` correctly refuses to guess an
  // interpretation from unparsed text (documented "never guess"
  // contract), so `interpretation` was `null` for that data, and `null`
  // has always rendered blank. This describe block is a regression lock,
  // not a bug fix - it renders a MULTI-ROW numeric panel (deliberately
  // NOT named "CBC" - `isQualitativeCategoricalRow`/`FlagText` are driven
  // purely by `resultType`/`interpretation`, never by test/parameter name)
  // and proves every row's FLAG cell matches its already-computed,
  // already-persisted `interpretation`, data-driven over a table rather
  // than one hardcoded assertion. ---
  describe("Laboratory Report FLAG column - standard numeric report, data-driven Low/High/Normal", () => {
    // Mirrors the exact values from the client's reported screenshot (a
    // CBC-style panel), but the template/test name is deliberately generic
    // ("Generic Numeric Panel") - this suite is proving the flag pipeline
    // is name-agnostic, not re-testing CBC specifically.
    const rows: { parameterName: string; numericValue: number; interpretation: "Low" | "High" | "Normal"; expectedFlag: "L" | "H" | null }[] = [
      { parameterName: "Param A (in range)", numericValue: 22, interpretation: "Normal", expectedFlag: null },
      { parameterName: "Param B (below range)", numericValue: 5, interpretation: "Low", expectedFlag: "L" },
      { parameterName: "Param C (above range)", numericValue: 6, interpretation: "High", expectedFlag: "H" },
      { parameterName: "Param D (below range)", numericValue: 115, interpretation: "Low", expectedFlag: "L" },
      { parameterName: "Param E (above range)", numericValue: 0.3, interpretation: "High", expectedFlag: "H" },
    ];

    function buildPanelOrder() {
      return order({
        testType: "Generic Numeric Panel",
        template: {
          id: "t-panel", testName: "Generic Numeric Panel", testCategory: null, specimenType: null, defaultPrice: 0,
          turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: rows.map((r) => param({ parameterName: r.parameterName })),
        },
        results: rows.map((r) =>
          result({ parameterName: r.parameterName, numericValue: r.numericValue, interpretation: r.interpretation })
        ),
      });
    }

    it.each(rows)("$parameterName: interpretation '$interpretation' renders FLAG '$expectedFlag' (blank when null)", ({ parameterName, expectedFlag }) => {
      render(<LaboratoryReportView order={buildPanelOrder()} />);
      const dataRow = screen.getByText(parameterName).closest("tr") as HTMLTableRowElement;
      const flagCell = dataRow.children[4];
      expect(flagCell).toHaveTextContent(expectedFlag ?? "");
    });

    it("a full multi-row standard report renders every row's flag independently, in template order", () => {
      render(<LaboratoryReportView order={buildPanelOrder()} />);
      for (const r of rows) {
        const dataRow = screen.getByText(r.parameterName).closest("tr") as HTMLTableRowElement;
        expect(dataRow.children[4]).toHaveTextContent(r.expectedFlag ?? "");
      }
      // Sanity: the panel's own out-of-range rows produced visible L/H
      // text somewhere in the document (proves this isn't a false-positive
      // "no flag anywhere is blank" check).
      expect(screen.getAllByText("L").length).toBeGreaterThan(0);
      expect(screen.getAllByText("H").length).toBeGreaterThan(0);
    });

    it("a qualitative Positive/Negative matrix report is unaffected - still no FLAG column, no L/H/A for Positive/Negative", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "Generic Serology Panel",
            template: {
              id: "t-matrix-panel", testName: "Generic Serology Panel", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [param({ parameterName: "Marker", resultType: "Categorical", options: ["Positive", "Negative"] })],
            },
            results: [
              result({ parameterName: "Marker", resultType: "Categorical", structuredValue: { value: "Positive" }, interpretation: "Abnormal" }),
            ],
          })}
        />
      );
      // No standard 5-column Flag header exists on a pure-matrix report.
      expect(screen.queryByRole("columnheader", { name: "Flag" })).not.toBeInTheDocument();
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();
      expect(screen.getByText("Positive")).toBeInTheDocument();
    });
  });

  // --- Qualitative Positive/Negative MATRIX layout (client reference:
  // the parent test name as the matrix's own first cell/row label - "TEST
  // | NS1 | IgM | IgG" / "DENGUE RAPID TEST | Negative | Positive |
  // Negative" - never Unit/Normal Values/Flag/Interpretation for this
  // layout. The report header's "Test: <name>" InfoRow is hidden for a
  // matrix report specifically to avoid showing the parent test name
  // twice - it stays exactly as before for every standard report.
  // Selected purely by `isQualitativeCategoricalRow` (resultType +
  // configured `options`), never by test name - every test below uses a
  // different, fictional parameter set to prove that. ---
  describe("Laboratory Report print redesign - qualitative Positive/Negative MATRIX layout", () => {
    function categoricalParam(name: string) {
      return param({ parameterName: name, resultType: "Categorical", options: ["Positive", "Negative"] });
    }
    function categoricalResult(name: string, value: string) {
      return result({ parameterName: name, resultType: "Categorical", structuredValue: { value }, interpretation: value === "Positive" ? "Abnormal" : "Normal", normalRange: "Negative", units: null });
    }

    it("A: a 3-parameter test (Dengue-style) renders a TEST column plus one column per parameter, with matching results, and hides the header's Test field", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "DENGUE RAPID TEST (DRT)",
            template: {
              id: "t-drt", testName: "DENGUE RAPID TEST (DRT)", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("NS1"), categoricalParam("IgM"), categoricalParam("IgG")],
            },
            results: [
              categoricalResult("NS1", "Negative"),
              categoricalResult("IgM", "Negative"),
              categoricalResult("IgG", "Negative"),
            ],
          })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "NS1", "IgM", "IgG"]);
      // The header's own "Test" InfoRow label is gone for a matrix report -
      // "Test" now appears exactly ONCE (the matrix's own column heading,
      // already counted in `headers` above), not twice. "DENGUE RAPID TEST
      // (DRT)" appears exactly ONCE, as the matrix's own parent-test cell,
      // never duplicated in the info block above it.
      expect(screen.getAllByText("Test")).toHaveLength(1);
      expect(screen.getAllByText("DENGUE RAPID TEST (DRT)")).toHaveLength(1);
      const negatives = screen.getAllByText("Negative");
      expect(negatives).toHaveLength(3);
      // No Unit/Normal Values/Flag/Interpretation columns for this layout.
      expect(screen.queryByRole("columnheader", { name: "Unit" })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Normal Values" })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Flag" })).not.toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();
    });

    it("B: a 2-parameter test (Typhoid-style) renders IgM/IgG columns with Positive results, still with the TEST column", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "S TYPHI TYPHOID",
            template: {
              id: "t-typhoid", testName: "S TYPHI TYPHOID", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("IgM"), categoricalParam("IgG")],
            },
            results: [categoricalResult("IgM", "Positive"), categoricalResult("IgG", "Positive")],
          })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "IgM", "IgG"]);
      // "S TYPHI TYPHOID" appears exactly once - only as the matrix's own
      // parent-test cell; "Test" appears exactly once too (the matrix's
      // own column heading), proving the header's "Test" field is hidden.
      expect(screen.getAllByText("Test")).toHaveLength(1);
      expect(screen.getAllByText("S TYPHI TYPHOID")).toHaveLength(1);
      expect(screen.getAllByText("Positive")).toHaveLength(2);
      expect(screen.queryByRole("columnheader", { name: "Unit" })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Normal Values" })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Flag" })).not.toBeInTheDocument();
    });

    it("C: a single-parameter test (HBsAg-style) uses the parameter name itself as the column heading, not a generic 'Result'", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "HEPATITIS B ANTIGEN (HBSAG)",
            template: {
              id: "t-hbsag", testName: "HEPATITIS B ANTIGEN (HBSAG)", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("HBsAg")],
            },
            results: [categoricalResult("HBsAg", "Positive")],
          })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "HBsAg"]);
      expect(screen.queryByText("Result")).not.toBeInTheDocument();
      // "HEPATITIS B ANTIGEN (HBSAG)" appears exactly once - as the
      // matrix's own parent-test cell; "Test" appears exactly once too
      // (the matrix's own column heading), proving the header's own
      // "Test" InfoRow is hidden.
      expect(screen.getAllByText("Test")).toHaveLength(1);
      expect(screen.getAllByText("HEPATITIS B ANTIGEN (HBSAG)")).toHaveLength(1);
      expect(screen.getByText("Positive")).toBeInTheDocument();
    });

    it("D: a 4-parameter test is fully dynamic - not assuming exactly 1/2/3 columns", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "Fictional 4-Analyte Panel",
            template: {
              id: "t-four", testName: "Fictional 4-Analyte Panel", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("A"), categoricalParam("B"), categoricalParam("C"), categoricalParam("D")],
            },
            results: [
              categoricalResult("A", "Negative"), categoricalResult("B", "Positive"),
              categoricalResult("C", "Negative"), categoricalResult("D", "Positive"),
            ],
          })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "A", "B", "C", "D"]);
      expect(screen.getAllByText("Fictional 4-Analyte Panel")).toHaveLength(1);
    });

    it("I: a standard (non-matrix) report still renders the header's Test field exactly as before", () => {
      render(
        <LaboratoryReportView
          order={order({ testType: "CBC", results: [result({ units: "g/dL", numericValue: 14 })] })}
        />
      );
      // "Test" appears twice for a standard report - the header's own
      // InfoRow label, plus the unrelated five-column table's "Test"
      // column heading - both already existed before this change.
      expect(screen.getAllByText("Test")).toHaveLength(2);
      expect(screen.getByText("CBC")).toBeInTheDocument();
    });

    it("E: Numeric reports are completely unaffected by the matrix layout - Unit/Normal Values/Flag still render", () => {
      render(
        <LaboratoryReportView
          order={order({ results: [result({ units: "g/dL", normalRange: "12.0-16.0", interpretation: "High" })] })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
      expect(screen.getByText("g/dL")).toBeInTheDocument();
      expect(screen.getByText("12.0-16.0")).toBeInTheDocument();
      expect(screen.getByText("H")).toBeInTheDocument();
    });

    it("F: an unconfigured Categorical result (no options) keeps the existing full-grid layout, never the matrix", () => {
      render(
        <LaboratoryReportView
          order={order({
            testType: "Urinalysis",
            template: {
              id: "t-ua2", testName: "Urinalysis", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [param({ parameterName: "Protein", resultType: "Categorical" })],
            },
            results: [result({ parameterName: "Protein", resultType: "Categorical", structuredValue: { value: "Negative" } })],
          })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
      expect(screen.getByText("Protein")).toBeInTheDocument();
    });

    it("G: interpretation remains available on the underlying result even though the matrix never prints it", () => {
      const drtResult = categoricalResult("NS1", "Positive");
      expect(drtResult.interpretation).toBe("Abnormal");
      render(
        <LaboratoryReportView
          order={order({
            template: {
              id: "t-drt2", testName: "Dengue NS1", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("NS1")],
            },
            results: [drtResult],
          })}
        />
      );
      // The matrix never renders the word "Abnormal" or a flag character,
      // even though the underlying data object above still carries it.
      expect(screen.queryByText("Abnormal")).not.toBeInTheDocument();
      expect(screen.queryByText("A")).not.toBeInTheDocument();
    });

    it("H: the MedTech and Pathologist signature blocks still render alongside a qualitative matrix report", () => {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
        <LaboratoryReportView
          order={order({
            medTechNameSnapshot: "Aijilie Mosquite",
            medTechLicenseSnapshot: "123456",
            pathologistNameSnapshot: "Dr. Santos",
            pathologistLicenseSnapshot: "PRC-SANTOS-001",
            template: {
              id: "t-hbsag2", testName: "HEPATITIS B ANTIGEN (HBSAG)", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("HBsAg")],
            },
            results: [categoricalResult("HBsAg", "Positive")],
          })}
        />
        </QueryClientProvider>
      );
      expect(screen.getByTestId("med-tech-signatory")).toBeInTheDocument();
      expect(screen.getByTestId("pathologist-signatory")).toBeInTheDocument();
      expect(screen.getByText("Aijilie Mosquite")).toBeInTheDocument();
      expect(screen.getByText("Dr. Santos")).toBeInTheDocument();
      // Client feedback: the "MED TECHNOLOGIST IN CHARGE" / "PATHOLOGIST"
      // role headings are redundant (the name, license, and role line
      // already identify the signatory) - removed from every report type,
      // matrix included (see the standard-report equivalent test below).
      expect(screen.queryByText("Med Technologist in Charge")).not.toBeInTheDocument();
      expect(screen.queryByText("MED TECHNOLOGIST IN CHARGE")).not.toBeInTheDocument();
      expect(screen.queryByText(/^Pathologist$/i, { selector: "p.mb-1" })).not.toBeInTheDocument();
      // Everything below the (now-removed) heading still renders: name,
      // license number (each signatory's own convention), and role line.
      expect(screen.getByText("RMT No. 123456")).toBeInTheDocument();
      expect(screen.getByText("Lic. No. PRC-SANTOS-001")).toBeInTheDocument();
      expect(screen.getByText("Medical Technologist")).toBeInTheDocument();
      expect(screen.getByTestId("pathologist-signatory")).toHaveTextContent("Pathologist");
    });

    it("also prints the 'refer to your doctor' note only for a qualitative matrix report, not for a purely quantitative one", () => {
      const { rerender } = render(
        <LaboratoryReportView
          order={order({
            template: {
              id: "t-hbsag3", testName: "HEPATITIS B ANTIGEN (HBSAG)", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [categoricalParam("HBsAg")],
            },
            results: [categoricalResult("HBsAg", "Positive")],
          })}
        />
      );
      expect(screen.getByText("Please refer to your doctor for interpretation of the results.")).toBeInTheDocument();

      rerender(<LaboratoryReportView order={order({ results: [result()] })} />);
      expect(screen.queryByText("Please refer to your doctor for interpretation of the results.")).not.toBeInTheDocument();
    });
  });

  describe("Laboratory Report print redesign, round 5 (clinic contact info in header)", () => {
    it("1: the clinic address appears in the header when configured", () => {
      render(<LaboratoryReportView order={order({ clinicAddress: "123 Main Street, Ormoc City, Leyte" })} />);
      expect(screen.getByText(/123 Main Street, Ormoc City, Leyte/)).toBeInTheDocument();
    });

    it("2: the clinic contact number appears when configured", () => {
      render(<LaboratoryReportView order={order({ clinicPhone: "0917-123-4567" })} />);
      expect(screen.getByText(/0917-123-4567/)).toBeInTheDocument();
    });

    it("3: the clinic email appears when configured", () => {
      render(<LaboratoryReportView order={order({ clinicEmail: "clinic@canora.com" })} />);
      expect(screen.getByText(/clinic@canora.com/)).toBeInTheDocument();
    });

    it("4: all three appear together, in order, between the clinic name and 'Laboratory Report'", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicName: "Canora Medical Clinic & Laboratory",
            clinicAddress: "123 Main Street, Ormoc City, Leyte",
            clinicPhone: "0917-123-4567",
            clinicEmail: "clinic@canora.com",
          })}
        />
      );
      const contactLine = screen.getByText("123 Main Street, Ormoc City, Leyte • 0917-123-4567 • clinic@canora.com");
      expect(contactLine).toBeInTheDocument();
      const clinicName = screen.getByText("Canora Medical Clinic & Laboratory");
      const reportTitle = screen.getByText("Laboratory Report");
      // DOM order within the same container proves the required visual
      // order: clinic name, then contact line, then "Laboratory Report".
      const position = (node: Element) =>
        Array.from(node.parentElement!.children).indexOf(node);
      expect(position(clinicName)).toBeLessThan(position(contactLine));
      expect(position(contactLine)).toBeLessThan(position(reportTitle));
    });

    // Client feedback: the printed address must read "<address>, <barangay>,
    // <city>, <province>" - the join itself happens server-side (see
    // `laboratory.py`'s `get_order`), so this component just needs to keep
    // rendering `order.clinicAddress` verbatim, in whatever already-joined
    // form the backend sends, unchanged by this feature.
    it("4b: the full address including Barangay renders verbatim, in the client's reference order", () => {
      render(
        <LaboratoryReportView
          order={order({ clinicAddress: "123 Rizal St., Brgy. Poblacion, Mabini, Leyte" })}
        />
      );
      expect(screen.getByText(/123 Rizal St\., Brgy\. Poblacion, Mabini, Leyte/)).toBeInTheDocument();
    });

    it("4c: an address string with a component omitted upstream never shows a malformed/dangling comma", () => {
      // Simulates the backend's own "omit, don't fabricate" join for a
      // clinic missing one component (e.g. no Barangay configured) -
      // proves this component doesn't add its own separators/formatting
      // on top of the already-joined string.
      render(<LaboratoryReportView order={order({ clinicAddress: "123 Main Street, Ormoc City, Leyte" })} />);
      const addressText = screen.getByText(/123 Main Street, Ormoc City, Leyte/).textContent ?? "";
      expect(addressText).not.toMatch(/,\s*,/);
      expect(addressText).not.toMatch(/^\s*,|,\s*$/);
    });

    it("4d: clinic name, logo-fallback icon, and the 'Laboratory Report' title are unaffected by the Barangay-inclusive address", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicName: "Canora Medical Clinic & Laboratory",
            clinicAddress: "123 Rizal St., Brgy. Poblacion, Mabini, Leyte",
          })}
        />
      );
      expect(screen.getByText("Canora Medical Clinic & Laboratory")).toBeInTheDocument();
      expect(screen.getByText("Laboratory Report")).toBeInTheDocument();
    });

    it("4e: the Barangay-inclusive address renders identically for a qualitative matrix report", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicAddress: "123 Rizal St., Brgy. Poblacion, Mabini, Leyte",
            testType: "HEPATITIS B ANTIGEN (HBSAG)",
            template: {
              id: "t-hbsag-addr", testName: "HEPATITIS B ANTIGEN (HBSAG)", testCategory: null, specimenType: null, defaultPrice: 0,
              turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
              parameters: [param({ parameterName: "HBsAg", resultType: "Categorical", options: ["Positive", "Negative"] })],
            },
            results: [result({ parameterName: "HBsAg", resultType: "Categorical", structuredValue: { value: "Positive" }, interpretation: "Abnormal", normalRange: "Negative", units: null })],
          })}
        />
      );
      expect(screen.getByText(/123 Rizal St\., Brgy\. Poblacion, Mabini, Leyte/)).toBeInTheDocument();
      // Matrix-report requirements from the prior change remain intact:
      // parent test name inside the matrix, no duplicate header "Test" row.
      expect(screen.getAllByText("Test")).toHaveLength(1);
      expect(screen.getByText("HEPATITIS B ANTIGEN (HBSAG)")).toBeInTheDocument();
    });

    it("5: values are read from the order's existing clinic configuration fields, not hard-coded", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicAddress: "456 Different Avenue, Tacloban City",
            clinicPhone: "032-888-9999",
            clinicEmail: "other@differentclinic.ph",
          })}
        />
      );
      expect(screen.getByText(/456 Different Avenue, Tacloban City/)).toBeInTheDocument();
      expect(screen.getByText(/032-888-9999/)).toBeInTheDocument();
      expect(screen.getByText(/other@differentclinic\.ph/)).toBeInTheDocument();
      // Proves nothing static/hard-coded is rendered instead - a
      // differently-configured clinic's own values show up verbatim.
      expect(screen.queryByText(/123 Main Street/)).not.toBeInTheDocument();
    });

    it("6: a missing clinic address does not render fake/placeholder address text", () => {
      render(
        <LaboratoryReportView
          order={order({ clinicAddress: null, clinicPhone: "0917-123-4567", clinicEmail: "clinic@canora.com" })}
        />
      );
      expect(screen.getByText("0917-123-4567 • clinic@canora.com")).toBeInTheDocument();
      expect(screen.queryByText(/N\/A|Not configured|Unknown address/i)).not.toBeInTheDocument();
    });

    it("7: a missing clinic phone does not render fake/placeholder contact text", () => {
      render(
        <LaboratoryReportView
          order={order({ clinicAddress: "123 Main Street, Ormoc City, Leyte", clinicPhone: null, clinicEmail: "clinic@canora.com" })}
        />
      );
      expect(screen.getByText("123 Main Street, Ormoc City, Leyte • clinic@canora.com")).toBeInTheDocument();
      expect(screen.queryByText(/N\/A|Not configured|Unknown/i)).not.toBeInTheDocument();
    });

    it("8: a missing clinic email does not render fake/placeholder email text", () => {
      render(
        <LaboratoryReportView
          order={order({ clinicAddress: "123 Main Street, Ormoc City, Leyte", clinicPhone: "0917-123-4567", clinicEmail: null })}
        />
      );
      expect(screen.getByText("123 Main Street, Ormoc City, Leyte • 0917-123-4567")).toBeInTheDocument();
      expect(screen.queryByText(/N\/A|Not configured|Unknown/i)).not.toBeInTheDocument();
    });

    it("9: separator formatting stays clean (no double/dangling bullets) with only one field configured, and no line at all with zero configured", () => {
      const { rerender, container } = render(
        <LaboratoryReportView order={order({ clinicAddress: "Only Address Here", clinicPhone: null, clinicEmail: null })} />
      );
      expect(screen.getByText("Only Address Here")).toBeInTheDocument();
      expect(container.textContent).not.toMatch(/•\s*•/);
      expect(container.textContent).not.toMatch(/^\s*•|•\s*$/);

      rerender(<LaboratoryReportView order={order({ clinicAddress: null, clinicPhone: null, clinicEmail: null })} />);
      expect(container.querySelector("#laboratory-report-body")?.textContent).not.toContain("•");
    });

    it("10: the existing clinic name still renders correctly alongside the new contact line", () => {
      render(<LaboratoryReportView order={order({ clinicName: "Canora Medical Clinic & Laboratory", clinicAddress: "Some Address" })} />);
      expect(screen.getByText("Canora Medical Clinic & Laboratory")).toBeInTheDocument();
    });

    it("11: 'Laboratory Report' remains present in the header", () => {
      render(<LaboratoryReportView order={order({ clinicAddress: "Some Address", clinicPhone: "0917-000-0000" })} />);
      expect(screen.getByText("Laboratory Report")).toBeInTheDocument();
    });

    it("12: the existing five-column result table is unaffected by the new header line", () => {
      render(<LaboratoryReportView order={order({ clinicAddress: "Some Address", results: [result()] })} />);
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
    });

    it("13: table width still sums to 100% and carries no horizontal-overflow classes with the contact line present", () => {
      render(<LaboratoryReportView order={order({ clinicAddress: "Some Address", clinicPhone: "0917-000-0000", clinicEmail: "a@b.com", results: [result()] })} />);
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      const widths = Array.from(table.querySelectorAll("colgroup col")).map(
        (col) => Number((col as HTMLElement).style.width.replace("%", ""))
      );
      expect(widths.reduce((sum, w) => sum + w, 0)).toBe(100);
      expect(table.className).toContain("w-full");
      expect(table.className).toContain("max-w-full");
    });

    it("14: historical results still print their own persisted values unchanged, regardless of the new contact line", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicAddress: "Some Address",
            template: { id: "template-1", testName: "CBC", testCategory: null, specimenType: null, defaultPrice: 0, turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z", parameters: [param()] },
            results: [result({ normalRange: "12.0-16.0 (historical)", units: "g/dL", interpretation: "Low" })],
          })}
        />
      );
      expect(screen.getByText("12.0-16.0 (historical)")).toBeInTheDocument();
      expect(screen.getByText("g/dL")).toBeInTheDocument();
      expect(screen.getByText("L")).toBeInTheDocument();
    });
  });

  describe("Laboratory Report print redesign, round 6 (Med Tech + Pathologist signatories)", () => {
    function renderWithClient(ui: React.ReactElement) {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
    }

    it("5: the signatory block renders in the report when a Med Tech was captured at release", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView order={order({ medTechNameSnapshot: "Maria Cruz", medTechLicenseSnapshot: "MT-001" })} />
      );
      expect(screen.getByTestId("med-tech-signatory")).toBeInTheDocument();
      expect(screen.getByText("Maria Cruz")).toBeInTheDocument();
      expect(screen.getByText("Medical Technologist")).toBeInTheDocument();
      // Med Tech's license line uses "RMT No." (not the Pathologist's
      // "Lic. No.") per the client's reference format.
      expect(screen.getByText("RMT No. MT-001")).toBeInTheDocument();
      // Client feedback (round 2): the "MED TECHNOLOGIST IN CHARGE" heading
      // is redundant on EVERY report, including this standard (non-matrix)
      // one (default `order()` here has no qualitative rows) - it was
      // previously removed ONLY for a matrix report, which is exactly why
      // it kept reappearing on a standard CBC-style report. See the
      // dedicated regression test below for the full before/after proof.
      expect(screen.queryByText("Med Technologist in Charge")).not.toBeInTheDocument();
    });

    it("5e (regression - client-reported 'heading reappeared on the standard report'): neither 'MED TECHNOLOGIST IN CHARGE' nor 'PATHOLOGIST' renders on a standard CBC-style report, while every other signatory field still does", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({
            testType: "CBC",
            medTechNameSnapshot: "Aijilie Mosquite", medTechLicenseSnapshot: "123456",
            pathologistNameSnapshot: "Dr. Santos", pathologistLicenseSnapshot: "PRC-SANTOS-001",
          })}
        />
      );
      // The two redundant headings must not render anywhere in the report.
      expect(screen.queryByText("Med Technologist in Charge")).not.toBeInTheDocument();
      expect(screen.queryByText("MED TECHNOLOGIST IN CHARGE")).not.toBeInTheDocument();
      expect(screen.queryByText(/^Pathologist$/i, { selector: "p.mb-1" })).not.toBeInTheDocument();
      // Everything else the signatory footer is required to keep still
      // renders: names, both license-number conventions, and both role
      // lines (the role line and the removed heading share the word
      // "Pathologist" - `toHaveTextContent` below proves it's still
      // present on the column, distinct from the heading-specific query
      // above which targets only the `p.mb-1` heading element).
      expect(screen.getByText("Aijilie Mosquite")).toBeInTheDocument();
      expect(screen.getByText("Dr. Santos")).toBeInTheDocument();
      expect(screen.getByText("RMT No. 123456")).toBeInTheDocument();
      expect(screen.getByText("Lic. No. PRC-SANTOS-001")).toBeInTheDocument();
      expect(screen.getByText("Medical Technologist")).toBeInTheDocument();
      expect(screen.getByTestId("pathologist-signatory")).toHaveTextContent("Pathologist");
    });

    it("5b: the Pathologist's license line uses 'Lic. No.', distinct from the Med Tech's 'RMT No.'", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({
            medTechNameSnapshot: "Maria Cruz", medTechLicenseSnapshot: "MT-001",
            pathologistNameSnapshot: "Dr. Santos", pathologistLicenseSnapshot: "85469",
          })}
        />
      );
      const pathologistColumn = screen.getByTestId("pathologist-signatory");
      expect(pathologistColumn).toHaveTextContent("Dr. Santos");
      expect(pathologistColumn).toHaveTextContent("Pathologist");
      expect(screen.getByText("Lic. No. 85469")).toBeInTheDocument();
      expect(screen.queryByText("RMT No. 85469")).not.toBeInTheDocument();
      // Both license lines coexist without colliding.
      expect(screen.getByText("RMT No. MT-001")).toBeInTheDocument();
    });

    it("5c: a Med Tech with no license number configured omits the 'RMT No.' line entirely - name/role still render, never a blank 'RMT No.'", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({ medTechNameSnapshot: "Maria Cruz", medTechLicenseSnapshot: null })}
        />
      );
      const medTechColumn = screen.getByTestId("med-tech-signatory");
      expect(medTechColumn).toHaveTextContent("Maria Cruz");
      expect(medTechColumn).toHaveTextContent("Medical Technologist");
      expect(screen.queryByText(/RMT No\./)).not.toBeInTheDocument();
    });

    it("5d: a Pathologist with no license number configured omits the 'Lic. No.' line entirely - name/role still render, never a blank 'Lic. No.'", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({ pathologistNameSnapshot: "Dr. Santos", pathologistLicenseSnapshot: null })}
        />
      );
      const pathologistColumn = screen.getByTestId("pathologist-signatory");
      expect(pathologistColumn).toHaveTextContent("Dr. Santos");
      expect(pathologistColumn).toHaveTextContent("Pathologist");
      expect(screen.queryByText(/Lic\. No\./)).not.toBeInTheDocument();
    });

    it("6: the signature image is fetched and rendered ABOVE the printed name", async () => {
      mockFetchBlob.mockReset().mockResolvedValue(new Blob(["png"], { type: "image/png" }));
      renderWithClient(
        <LaboratoryReportView
          order={order({
            medTechNameSnapshot: "Maria Cruz",
            medTechSignatureSnapshotUrl: "sig-abc.png",
          })}
        />
      );
      await waitFor(() => expect(mockFetchBlob).toHaveBeenCalledWith("/laboratory/orders/lab-1/med-tech-signature/file"));
      const img = await screen.findByAltText("Med Technologist in Charge signature");
      const name = screen.getByText("Maria Cruz");
      const column = screen.getByTestId("med-tech-signatory");
      const position = (node: Element) => Array.from(column.querySelectorAll("*")).indexOf(node);
      expect(position(img)).toBeLessThan(position(name));
    });

    it("7/8: Med Tech renders in the LEFT column, Pathologist in the RIGHT column", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({ medTechNameSnapshot: "Maria Cruz", pathologistNameSnapshot: "Dr. Santos" })}
        />
      );
      const medTechColumn = screen.getByTestId("med-tech-signatory");
      const pathologistColumn = screen.getByTestId("pathologist-signatory");
      const grid = medTechColumn.parentElement as HTMLElement;
      const children = Array.from(grid.children);
      expect(children.indexOf(medTechColumn)).toBeLessThan(children.indexOf(pathologistColumn));
      expect(medTechColumn).toHaveTextContent("Maria Cruz");
      expect(pathologistColumn).toHaveTextContent("Dr. Santos");
    });

    it("9: a missing Med Tech signature image shows the name/role with a blank signature area, not a crash or fabricated image", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView order={order({ medTechNameSnapshot: "Maria Cruz", medTechSignatureSnapshotUrl: null })} />
      );
      expect(mockFetchBlob).not.toHaveBeenCalled();
      expect(screen.queryByAltText("Med Technologist in Charge signature")).not.toBeInTheDocument();
      expect(screen.getByText("Maria Cruz")).toBeInTheDocument();
    });

    it("9b: a not-yet-released order (no signatories captured) renders no signatory block at all - never fabricated", () => {
      mockFetchBlob.mockReset();
      renderWithClient(<LaboratoryReportView order={order()} />);
      expect(screen.queryByTestId("med-tech-signatory")).not.toBeInTheDocument();
      expect(screen.queryByTestId("pathologist-signatory")).not.toBeInTheDocument();
    });

    it("9c: a Pathologist selected with no signature configured shows the name but no fabricated image", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({ pathologistNameSnapshot: "Dr. Santos", pathologistSignatureSnapshotUrl: null })}
        />
      );
      expect(screen.queryByAltText("Pathologist signature")).not.toBeInTheDocument();
      expect(screen.getByText("Dr. Santos")).toBeInTheDocument();
    });

    it("15: the existing five-column Flag format is unaffected by the new signatory block", () => {
      mockFetchBlob.mockReset();
      renderWithClient(
        <LaboratoryReportView
          order={order({ medTechNameSnapshot: "Maria Cruz", results: [result({ interpretation: "Low" })] })}
        />
      );
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
      expect(screen.getByText("L")).toBeInTheDocument();
    });
  });

  describe("Laboratory Report print redesign, round 7 (flag colors: L red, H blue)", () => {
    it("1: L renders red (text-destructive)", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "Low" })] })} />);
      expect(screen.getByText("L").className).toContain("text-destructive");
      expect(screen.getByText("L").className).not.toContain("text-primary");
    });

    it("2: H renders blue (text-primary), not red", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "High" })] })} />);
      expect(screen.getByText("H").className).toContain("text-primary");
      expect(screen.getByText("H").className).not.toContain("text-destructive");
    });

    it("3: a normal flag remains blank - no color, no text", () => {
      render(<LaboratoryReportView order={order({ results: [result({ interpretation: "Normal" })] })} />);
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
    });

    it("4: the Result cell is never colored red or blue due to the flag", () => {
      render(
        <LaboratoryReportView
          order={order({ template: null, results: [result({ parameterName: "MCH", numericValue: 33, interpretation: "High" })] })}
        />
      );
      const resultCell = screen.getByText("33");
      expect(resultCell.className).not.toContain("text-destructive");
      expect(resultCell.className).not.toContain("text-primary");
    });

    it("5: the Normal Values cell is never colored red or blue due to the flag", () => {
      render(
        <LaboratoryReportView
          order={order({ template: null, results: [result({ parameterName: "MCH", normalRange: "26.0-32.0", interpretation: "High" })] })}
        />
      );
      const rangeCell = screen.getByText("26.0-32.0");
      expect(rangeCell.className).not.toContain("text-destructive");
      expect(rangeCell.className).not.toContain("text-primary");
    });

    it("6: the Flag column header is still exactly 'FLAG'", () => {
      render(<LaboratoryReportView order={order({ results: [result()] })} />);
      expect(screen.getByRole("columnheader", { name: "Flag" })).toBeInTheDocument();
    });

    it("7: existing H/L/blank logic is unchanged - only the color mapping changed", () => {
      const { rerender } = render(<LaboratoryReportView order={order({ results: [result({ interpretation: "Low" })] })} />);
      expect(screen.getByText("L")).toBeInTheDocument();

      rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: "High" })] })} />);
      expect(screen.getByText("H")).toBeInTheDocument();

      rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: "Normal" })] })} />);
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();

      rerender(<LaboratoryReportView order={order({ results: [result({ interpretation: "Abnormal" })] })} />);
      expect(screen.queryByText("L")).not.toBeInTheDocument();
      expect(screen.queryByText("H")).not.toBeInTheDocument();
    });
  });

  describe("Laboratory Report print redesign, round 7 (clinic logo header)", () => {
    it("8: shows the clinic logo BEFORE the clinic name when configured", () => {
      const { container } = render(
        <LaboratoryReportView
          order={order({ clinicName: "Canora Medical Clinic & Laboratory", clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png" })}
        />
      );
      const img = container.querySelector("img") as HTMLImageElement;
      expect(img).not.toBeNull();
      expect(img).toHaveAttribute("src", "http://api.test/media/clinic-logo/clinic-1/logo-abc.png");
      const clinicName = screen.getByText("Canora Medical Clinic & Laboratory");
      const header = img.closest("div")!.parentElement as HTMLElement;
      const children = Array.from(header.querySelectorAll("*"));
      expect(children.indexOf(img)).toBeLessThan(children.indexOf(clinicName));
    });

    it("preserves the existing text-only header (no fabricated logo) when no logo is configured", () => {
      const { container } = render(<LaboratoryReportView order={order({ clinicName: "Canora Medical Clinic & Laboratory", clinicLogoUrl: null })} />);
      expect(container.querySelector("img")).toBeNull();
      expect(screen.getByText("Canora Medical Clinic & Laboratory")).toBeInTheDocument();
    });

    it("logo uses object-contain so it cannot be distorted/stretched", () => {
      const { container } = render(<LaboratoryReportView order={order({ clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png" })} />);
      expect((container.querySelector("img") as HTMLImageElement).className).toContain("object-contain");
    });

    it("9: adding the logo does not cause horizontal overflow - table widths still sum to 100%", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png",
            clinicAddress: "Some Address", clinicPhone: "0917-000-0000", clinicEmail: "a@b.com",
            results: [result()],
          })}
        />
      );
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      const widths = Array.from(table.querySelectorAll("colgroup col")).map(
        (col) => Number((col as HTMLElement).style.width.replace("%", ""))
      );
      expect(widths.reduce((sum, w) => sum + w, 0)).toBe(100);
      expect(table.className).toContain("w-full");
      expect(table.className).toContain("max-w-full");
    });

    it("preserves the contact/address line and report title alongside the logo", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png",
            clinicAddress: "123 Main Street", clinicPhone: "0917-000-0000", clinicEmail: "clinic@canora.com",
          })}
        />
      );
      expect(screen.getByText("123 Main Street • 0917-000-0000 • clinic@canora.com")).toBeInTheDocument();
      expect(screen.getByText("Laboratory Report")).toBeInTheDocument();
    });

    it("preserves the existing five-column Flag table structure with a logo present", () => {
      render(<LaboratoryReportView order={order({ clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png", results: [result({ interpretation: "Low" })] })} />);
      const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
      expect(headers).toEqual(["Test", "Result", "Unit", "Normal Values", "Flag"]);
      expect(screen.getByText("L")).toBeInTheDocument();
    });
  });

  describe("Laboratory Report clinic logo size increase (Round 7 follow-up)", () => {
    it("1: renders the clinic logo", () => {
      const { container } = render(<LaboratoryReportView order={order({ clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png" })} />);
      expect(container.querySelector("img")).not.toBeNull();
    });

    it("2: the logo uses the larger target dimensions (h-12, up from the old h-8) rather than icon-sized classes", () => {
      const { container } = render(<LaboratoryReportView order={order({ clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png" })} />);
      const img = container.querySelector("img") as HTMLImageElement;
      expect(img.className).toContain("h-12");
      expect(img.className).toContain("w-12");
      expect(img.className).not.toContain("h-8");
      expect(img.className).not.toContain("w-8");
    });

    it("3: the logo still uses object-contain (no distortion) at the larger size", () => {
      const { container } = render(<LaboratoryReportView order={order({ clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png" })} />);
      expect((container.querySelector("img") as HTMLImageElement).className).toContain("object-contain");
    });

    it("4: the clinic name remains present and prominent alongside the larger logo", () => {
      render(<LaboratoryReportView order={order({ clinicName: "Canora Medical Clinic & Laboratory", clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png" })} />);
      expect(screen.getByText("Canora Medical Clinic & Laboratory")).toBeInTheDocument();
    });

    it("5: the header contact line remains present alongside the larger logo", () => {
      render(
        <LaboratoryReportView
          order={order({
            clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png",
            clinicAddress: "123 Main Street", clinicPhone: "0917-000-0000", clinicEmail: "clinic@canora.com",
          })}
        />
      );
      expect(screen.getByText("123 Main Street • 0917-000-0000 • clinic@canora.com")).toBeInTheDocument();
    });

    it("6: the table still fits the report width with zero forced overflow at the larger logo size", () => {
      render(<LaboratoryReportView order={order({ clinicLogoUrl: "/media/clinic-logo/clinic-1/logo-abc.png", results: [result()] })} />);
      const table = screen.getByRole("columnheader", { name: "Test" }).closest("table") as HTMLTableElement;
      const widths = Array.from(table.querySelectorAll("colgroup col")).map(
        (col) => Number((col as HTMLElement).style.width.replace("%", ""))
      );
      expect(widths.reduce((sum, w) => sum + w, 0)).toBe(100);
      expect(table.className).toContain("w-full");
      expect(table.className).toContain("max-w-full");
    });
  });
});
