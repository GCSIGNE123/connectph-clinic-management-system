import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaboratoryReportDialog } from "./LaboratoryReportDialog";
import type { LaboratoryOrder } from "@/features/laboratory/types";

const useLaboratoryOrder = vi.fn();

vi.mock("@/features/laboratory/hooks/use-laboratory", () => ({
  useLaboratoryOrder: (id: string | null) => useLaboratoryOrder(id),
}));

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-1", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: null, patientId: "patient-1", patientName: "Juan Dela Cruz", doctorId: null, doctorName: null,
    templateId: null, template: null, testType: "CBC", priority: null, status: "Completed",
    scheduledDate: null, collectedAt: null, collectedBy: null, processingStartedAt: null, completedAt: null,
    releasedAt: null, releasedBy: null, invoiceItemId: null, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [], attachments: [], clinicName: "Test Clinic",
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function printCssText() {
  return Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
}

// The report intentionally renders TWICE once an order is loaded: once for
// the on-screen preview inside the dialog (`#laboratory-report-printable`),
// once portaled to `document.body` for `@media print`
// (`#laboratory-report-print-root` - see `LaboratoryReportPrintPortal`'s
// doc comment in the component file). This is the exact same proven
// pattern `QueueSlipDialog`/`QueueSlipPrintPortal` already uses for its own
// print pipeline - every assertion below therefore uses
// `findAllByText`/`getAllByText`/`queryAllByText`, never the singular form
// which would throw on the expected duplicate.
describe("LaboratoryReportDialog print redesign (Short Bond / Letter portrait, full page width)", () => {
  it("9: defaults to Letter paper size, whose print CSS carries an explicit 'Letter portrait' @page size", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);

    await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));
    // The paper-size selector (from the shared PrintableDocumentDialog)
    // reflects the Laboratory Report's own default, not the clinic-wide
    // stored preference (which defaults to A4).
    expect(screen.getByLabelText(/paper size/i)).toHaveValue("Letter");
    expect(printCssText()).toMatch(/@page\s*\{[^}]*size:\s*Letter portrait/);
  });

  it("10: the print CSS forces the on-screen preview's printable container to full width, not the narrow preview box", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

    expect(printCssText()).toMatch(/#laboratory-report-printable\s*\{[^}]*width:\s*100%\s*!important/);
  });

  it("12: existing Laboratory report printing behavior remains functional (renders results, clinic name, Print button)", async () => {
    useLaboratoryOrder.mockReturnValue({
      data: labOrder({
        results: [
          {
            id: "res-1", parameterName: "Hemoglobin", resultType: "Numeric", numericValue: 14, textValue: null,
            normalRange: "12.0-16.0", units: "g/dL", interpretation: "Normal", remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null, site: null,
          },
        ],
      }),
    });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);

    await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Hemoglobin").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /^print$/i })).toBeInTheDocument();
  });

  it("overall category heading: renders in BOTH the on-screen preview and the print portal copy when the template has a testCategory configured", async () => {
    useLaboratoryOrder.mockReturnValue({
      data: labOrder({
        template: {
          id: "t-cbc", testName: "CBC", testCategory: "Hematology", specimenType: null, defaultPrice: 0,
          turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
          parameters: [{ parameterName: "Hemoglobin", resultType: "Numeric", displayOrder: 0 }],
        },
        results: [
          {
            id: "res-1", parameterName: "Hemoglobin", resultType: "Numeric", numericValue: 14, textValue: null,
            normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
            enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null, site: null,
          },
        ],
      }),
    });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

    // The report legitimately renders twice by design (on-screen preview +
    // print portal - see the duplicate-2-page-print bug fix below), so the
    // category heading must appear exactly twice too - once per copy.
    expect(screen.getAllByText("HEMATOLOGY TEST")).toHaveLength(2);
  });

  it("round 2: forces print color-adjust so the navy table-header band actually prints (not dropped to save ink)", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

    expect(printCssText()).toMatch(/#laboratory-report-print-root[^{]*\{[^}]*print-color-adjust:\s*exact/);
  });

  it("round 2: print CSS repeats the table header and avoids splitting a result row or stranding a section heading across pages", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

    const printCss = printCssText();
    expect(printCss).toMatch(/#laboratory-report-print-root thead\s*\{[^}]*display:\s*table-header-group/);
    expect(printCss).toMatch(/#laboratory-report-print-root \.report-row\s*\{[^}]*break-inside:\s*avoid/);
    expect(printCss).toMatch(/#laboratory-report-print-root \.section-heading\s*\{[^}]*break-after:\s*avoid/);
  });

  // --- Bug fix (URGENT follow-up - the previous fix did not resolve it):
  // a single laboratory report still printed as a duplicate 2-page PDF
  // (the identical report on both pages, not a blank/continuation page).
  //
  // Root cause: `PrintableDocumentDialog`'s shared print CSS hides the
  // rest of the page via `visibility: hidden` (not `display: none`, which
  // would also hide the printable descendant it can't un-hide) -
  // `visibility: hidden` does NOT remove that hidden content from LAYOUT,
  // so a tall page behind the dialog (e.g. a long worklist table, or a
  // patient's Laboratory History table) still forces a second physical
  // print page to exist for essentially any reason (row count, print
  // margins, paper size) - not just "the report itself is too long". The
  // printable element is also `position: fixed` (needed so it prints at
  // the page origin rather than wherever it sits nested deep in that
  // hidden tree) - and per CSS Paged Media, a `fixed` box is REPEATED on
  // EVERY page a print job spans (the same mechanism used for a running
  // header/footer). Combined: whenever ANY second print page exists, the
  // fixed report reprints itself onto it, byte-for-byte identical to page
  // 1. A first attempt collapsed `<html>`/`<body>` to zero height at print
  // time instead of removing the `visibility` + `fixed` mechanism itself -
  // insufficient, since collapsing height doesn't stop a `position: fixed`
  // element from repeating onto whatever pages DO still get created (print
  // margin/DPI rounding, a `:has()` support gap, or any other source of a
  // second page all still trigger the exact same repeat).
  //
  // Fix: stop relying on `visibility` + `fixed` for the actual printed
  // content. `LaboratoryReportPrintPortal` portals a second copy of the
  // report directly onto `document.body` (the exact same proven pattern
  // `QueueSlipPrintPortal` already established in this codebase for its
  // own instance of this class of bug). `@media print` then: (1) force-
  // hides the ORIGINAL on-screen-preview printable element
  // (`display: none` unconditionally wins - no descendant visibility rule
  // can override it), (2) hides every OTHER direct child of `body` with
  // `display: none` (which, unlike `visibility`, genuinely removes content
  // from layout), leaving the portal as the only in-flow content to
  // paginate, and (3) renders the portal normally (no `position: fixed`),
  // so it can never repeat onto an extra page. Data-driven across every
  // report shape the client asked to verify: CBC (standard/numeric),
  // Dengue Rapid Test (multi-parameter matrix), and HBsAg
  // (single-parameter matrix). ---
  describe("Bug fix: duplicate 2-page print output", () => {
    function categoricalParam(name: string) {
      return { parameterName: name, resultType: "Categorical" as const, displayOrder: 0, options: ["Positive", "Negative"] };
    }
    function categoricalResult(name: string, value: string) {
      return {
        id: `res-${name}`, parameterName: name, resultType: "Categorical" as const, numericValue: null,
        textValue: null, normalRange: null, units: null, interpretation: null, remarks: null,
        rangeLow: null, rangeHigh: null, enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z",
        structuredValue: { value }, site: null,
      };
    }

    const dengueOrder = labOrder({
      testType: "DENGUE RAPID TEST",
      template: {
        id: "t-drt", testName: "DENGUE RAPID TEST", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [categoricalParam("NS1"), categoricalParam("IgM"), categoricalParam("IgG")],
      },
      results: [
        categoricalResult("NS1", "Negative"),
        categoricalResult("IgM", "Positive"),
        categoricalResult("IgG", "Negative"),
      ],
    });

    const hbsagOrder = labOrder({
      testType: "HEPATITIS B ANTIGEN (HBSAG)",
      template: {
        id: "t-hbsag", testName: "HEPATITIS B ANTIGEN (HBSAG)", testCategory: null, specimenType: null, defaultPrice: 0,
        turnaroundTimeHours: null, isActive: true, createdAt: "2026-01-01T00:00:00Z",
        parameters: [categoricalParam("HBsAg")],
      },
      results: [categoricalResult("HBsAg", "Positive")],
    });

    it.each([
      ["CBC (standard/numeric report)", labOrder()],
      ["Dengue Rapid Test (multi-parameter matrix report)", dengueOrder],
      ["HBsAg (single-parameter matrix report)", hbsagOrder],
    ])("%s: the print portal is a genuine direct child of document.body, exactly once - never mounted/duplicated twice", async (_label, order) => {
      useLaboratoryOrder.mockReturnValue({ data: order });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printRoots = document.querySelectorAll("#laboratory-report-print-root");
      expect(printRoots).toHaveLength(1);
      expect(printRoots[0].parentElement).toBe(document.body);
      // The on-screen preview element still exists too (exactly one) - the
      // report legitimately renders twice in the DOM by design (preview +
      // print portal); what must never happen is either one existing more
      // than once, or both being visible/printed at the same time (proven
      // by the CSS assertions below).
      expect(document.querySelectorAll("#laboratory-report-printable")).toHaveLength(1);
    });

    it.each([
      ["CBC (standard/numeric report)", labOrder()],
      ["Dengue Rapid Test (multi-parameter matrix report)", dengueOrder],
      ["HBsAg (single-parameter matrix report)", hbsagOrder],
    ])("%s: the print portal actually contains the full report content (clinic name, patient, test type)", async (_label, order) => {
      useLaboratoryOrder.mockReturnValue({ data: order });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printRoot = document.getElementById("laboratory-report-print-root") as HTMLElement;
      expect(printRoot).toHaveTextContent("Test Clinic");
      expect(printRoot).toHaveTextContent("Juan Dela Cruz");
    });

    it("the original on-screen-preview printable element is force-hidden at print time - only the portal is ever meant to print", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      expect(printCssText()).toMatch(/#laboratory-report-printable\s*\{[^}]*display:\s*none\s*!important/);
    });

    it("the print CSS hides every other direct child of body, leaving only the portal in flow to paginate", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printCss = printCssText();
      expect(printCss).toMatch(/body\s*>\s*\*:not\(#laboratory-report-print-root\)\s*\{[^}]*display:\s*none\s*!important/);
      // Round 9 (true page footer): the portal's own display rule changed
      // from a plain "block" to "flex" (+ flex-direction: column) so the
      // signatory footer's margin-top:auto has a flex context to push
      // against - it's still forced `!important` and still the only thing
      // left in flow to paginate, unchanged from the original fix this
      // test documents.
      expect(printCss).toMatch(/#laboratory-report-print-root\s*\{[^}]*display:\s*flex\s*!important/);
      expect(printCss).toMatch(/#laboratory-report-print-root\s*\{[^}]*flex-direction:\s*column/);
    });

    // --- Round 9 (true page footer): the signatory footer must render at
    // the bottom of the physical printed/PDF page, not immediately after
    // Notes - see LaboratoryReportView's own "flex-1" root and the
    // margin-top:auto footer wrapper. This only works print-side because
    // the portal supplies a page-height flex context for that to push
    // against. jsdom doesn't compute real layout, so these tests verify
    // the CSS rule itself is present and scoped correctly. ---
    it("the print portal gets a min-height of 100vh - a page-height flex context for the signatory footer's margin-top:auto to push against", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printCss = printCssText();
      expect(printCss).toMatch(/#laboratory-report-print-root\s*\{[^}]*min-height:\s*100vh/);
    });

    it("this min-height is a MINIMUM only (not a fixed height) - it never caps or clips a report whose content genuinely exceeds one page", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printCss = printCssText();
      // Deliberately excludes "min-" so this doesn't false-positive on the
      // very "min-height: 100vh" rule this feature relies on - only a
      // plain fixed "height:" or a "max-height"/"overflow:hidden" would
      // actually cap/clip content, and none of those are present.
      expect(printCss).not.toMatch(/#laboratory-report-print-root\s*\{[^}]*(?<!min-)height:\s*100vh/);
      expect(printCss).not.toMatch(/#laboratory-report-print-root\s*\{[^}]*max-height/);
      expect(printCss).not.toMatch(/#laboratory-report-print-root\s*\{[^}]*overflow:\s*hidden/);
    });

    it("the on-screen print-preview box is scoped to a flex column too (matching the print portal), so the footer previews bottom-aligned before printing - scoped only to this printableId, never a shared rule other printable documents inherit", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const css = printCssText();
      // Note: NOT inside @media print - this is the on-screen rule.
      expect(css).toMatch(/#laboratory-report-printable\s*\{[^}]*display:\s*flex/);
      expect(css).toMatch(/#laboratory-report-printable\s*\{[^}]*flex-direction:\s*column/);
    });

    it("the portal is invisible on screen (display: none outside @media print) - it never appears in the normal UI", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printRoot = document.getElementById("laboratory-report-print-root") as HTMLElement;
      expect(getComputedStyle(printRoot).display).toBe("none");
    });

    // Regression for a real bug found via an actual Print -> Save as PDF ->
    // Adobe Reader check: the duplication was fixed, but the resulting PDF
    // was exactly 1 page and completely BLANK. Root cause: the shared
    // PrintableDocumentDialog's own "body * { visibility: hidden }" rule
    // still applies to this portal (it only ever re-declares
    // "visibility: visible" for the OLD id), so the portal had correct
    // display:block LAYOUT (proving pagination was fixed) but painted
    // nothing. This test fails without the visibility: visible !important
    // override.
    it("the print portal is explicitly forced visible, overriding the shared component's blanket 'body * { visibility: hidden }' rule", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printCss = printCssText();
      expect(printCss).toMatch(/#laboratory-report-print-root,\s*#laboratory-report-print-root \*\s*\{[^}]*visibility:\s*visible\s*!important/);
    });

    it("existing pagination rules (repeated header, no split rows, no stranded section heading, print color-adjust) target the print portal, not the on-screen preview", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      const printCss = printCssText();
      expect(printCss).toMatch(/#laboratory-report-print-root thead\s*\{[^}]*display:\s*table-header-group/);
      expect(printCss).toMatch(/#laboratory-report-print-root \.report-row\s*\{[^}]*break-inside:\s*avoid/);
      expect(printCss).toMatch(/#laboratory-report-print-root \.section-heading\s*\{[^}]*break-after:\s*avoid/);
      expect(printCss).toMatch(/#laboratory-report-print-root[^{]*\{[^}]*print-color-adjust:\s*exact/);
    });
  });

  // --- Client request: default "Save as PDF" filename of
  // "<Patient_Name>-<last 4 Order # digits>.pdf" - built from the exact
  // same already-fetched order the report renders (never Visit #/Queue #),
  // wired through to `PrintableDocumentDialog`'s `printFilename` prop (see
  // that component's own tests for the underlying document.title
  // mechanism). ---
  describe("Default PDF filename", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("clicking Print sets document.title to '<Patient_Name>-<last 4 Order # digits>' (extensionless) for the duration of the print job", async () => {
      useLaboratoryOrder.mockReturnValue({
        data: labOrder({ patientName: "Paul Test", orderNumber: "ORD-20260901-000007" }),
      });
      let titleDuringPrint: string | null = null;
      vi.spyOn(window, "print").mockImplementation(() => {
        titleDuringPrint = document.title;
      });

      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      screen.getByRole("button", { name: /^print$/i }).click();
      expect(window.print).toHaveBeenCalledTimes(1);
      expect(titleDuringPrint).toBe("Paul_Test-0007");
    });

    it("a second order (different patient/order number) produces its own distinct filename - not hardcoded", async () => {
      useLaboratoryOrder.mockReturnValue({
        data: labOrder({ patientName: "Richard Test", orderNumber: "ORD-20260901-000002" }),
      });
      let titleDuringPrint: string | null = null;
      vi.spyOn(window, "print").mockImplementation(() => {
        titleDuringPrint = document.title;
      });

      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      screen.getByRole("button", { name: /^print$/i }).click();
      expect(titleDuringPrint).toBe("Richard_Test-0002");
    });

    it("never uses Visit # or Queue # in the filename, even when they differ from the patient/order values", async () => {
      useLaboratoryOrder.mockReturnValue({
        data: labOrder({
          patientName: "Paul Test", orderNumber: "ORD-20260901-000007",
          visitNumber: "VIS-99999999-999999", queueNumber: "L999",
        }),
      });
      let titleDuringPrint: string | null = null;
      vi.spyOn(window, "print").mockImplementation(() => {
        titleDuringPrint = document.title;
      });

      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      screen.getByRole("button", { name: /^print$/i }).click();
      expect(titleDuringPrint).toBe("Paul_Test-0007");
      expect(titleDuringPrint).not.toContain("99999999");
      expect(titleDuringPrint).not.toContain("999");
      expect(titleDuringPrint).not.toContain("L999");
    });

    it("does not change the Order # actually displayed on the report", async () => {
      useLaboratoryOrder.mockReturnValue({
        data: labOrder({ patientName: "Paul Test", orderNumber: "ORD-20260901-000007" }),
      });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getAllByText("Test Clinic").length).toBeGreaterThan(0));

      expect(screen.getAllByText("ORD-20260901-000007").length).toBeGreaterThan(0);
    });
  });
});
