import { describe, expect, it, vi } from "vitest";
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

describe("LaboratoryReportDialog print redesign (Short Bond / Letter portrait, full page width)", () => {
  it("9: defaults to Letter paper size, whose print CSS carries an explicit 'Letter portrait' @page size", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);

    await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());
    // The paper-size selector (from the shared PrintableDocumentDialog)
    // reflects the Laboratory Report's own default, not the clinic-wide
    // stored preference (which defaults to A4).
    expect(screen.getByLabelText(/paper size/i)).toHaveValue("Letter");

    const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
    expect(printCss).toMatch(/@page\s*\{[^}]*size:\s*Letter portrait/);
  });

  it("10: the print CSS forces the printable container to full width, not the narrow on-screen preview box", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

    const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
    expect(printCss).toMatch(/#laboratory-report-printable\s*\{[^}]*width:\s*100%\s*!important/);
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

    expect(await screen.findByText("Test Clinic")).toBeInTheDocument();
    expect(screen.getByText("Hemoglobin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^print$/i })).toBeInTheDocument();
  });

  it("round 2: forces print color-adjust so the navy table-header band actually prints (not dropped to save ink)", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

    const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
    expect(printCss).toMatch(/#laboratory-report-printable[^{]*\{[^}]*print-color-adjust:\s*exact/);
  });

  it("round 2: print CSS repeats the table header and avoids splitting a result row or stranding a section heading across pages", async () => {
    useLaboratoryOrder.mockReturnValue({ data: labOrder() });
    renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
    await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

    const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
    expect(printCss).toMatch(/#laboratory-report-printable thead\s*\{[^}]*display:\s*table-header-group/);
    expect(printCss).toMatch(/#laboratory-report-printable \.report-row\s*\{[^}]*break-inside:\s*avoid/);
    expect(printCss).toMatch(/#laboratory-report-printable \.section-heading\s*\{[^}]*break-after:\s*avoid/);
  });

  // --- Bug fix: a single laboratory report printed as a duplicate 2-page
  // PDF (the identical report on both pages). Root cause: the shared
  // `PrintableDocumentDialog` hides the rest of the page via `visibility:
  // hidden` (not `display: none`, which would also hide the printable
  // descendant it can't un-hide) - `visibility: hidden` doesn't remove
  // that hidden content from layout, so a tall page behind the dialog
  // (e.g. a long worklist) still forces a second physical print page to
  // exist, and because the printable element is `position: fixed` (a
  // "repeats on every page" declaration, same mechanism as a running
  // print header/footer), the whole report reprints itself onto that
  // extra page. Fix: collapse `<html>`/`<body>` to zero height at print
  // time, scoped with `:has(#laboratory-report-printable)` so it can
  // never affect Receipt/Queue Slip/Prescription/Referral/Lab Request
  // printing (same shared dialog, different `printableId`, never open at
  // the same time as this one). Data-driven across every report shape the
  // client asked to verify: CBC (standard/numeric), Dengue Rapid Test
  // (multi-parameter matrix), and HBsAg (single-parameter matrix). ---
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
    ])("%s: the printable element renders exactly once in the DOM - never mounted/duplicated twice", async (_label, order) => {
      useLaboratoryOrder.mockReturnValue({ data: order });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

      expect(document.querySelectorAll("#laboratory-report-printable")).toHaveLength(1);
      // The clinic name only appears inside the report body itself (never
      // in the surrounding dialog chrome, which uses "Laboratory Report"
      // as its own, separate title heading) - proves the report content
      // isn't duplicated inside or alongside that single printable
      // container.
      expect(screen.getAllByText("Test Clinic")).toHaveLength(1);
    });

    it("the print CSS collapses html/body height so a tall hidden page behind the dialog can't force a duplicate second print page", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

      const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
      expect(printCss).toMatch(/html:has\(#laboratory-report-printable\)/);
      expect(printCss).toMatch(/body:has\(#laboratory-report-printable\)/);
      expect(printCss).toMatch(/#laboratory-report-printable\)\s*\{[^}]*height:\s*0\s*!important/);
      expect(printCss).toMatch(/#laboratory-report-printable\)\s*\{[^}]*overflow:\s*hidden\s*!important/);
    });

    it("the collapse rule is scoped to :has(#laboratory-report-printable) - never a bare, unscoped html/body rule that could leak to other printable documents", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

      const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
      // Every html/body selector in this component's print CSS carries the
      // :has(#laboratory-report-printable) guard - stripping out those two
      // guarded selectors must leave no leftover bare "html {" / "body {"
      // rule that would apply unconditionally to every other printable
      // document sharing the same `PrintableDocumentDialog`.
      const withGuardedSelectorsRemoved = printCss
        .replaceAll("html:has(#laboratory-report-printable)", "")
        .replaceAll("body:has(#laboratory-report-printable)", "");
      expect(withGuardedSelectorsRemoved).not.toMatch(/\bhtml\s*\{/);
      expect(withGuardedSelectorsRemoved).not.toMatch(/\bbody\s*\{/);
    });

    it("existing pagination rules (repeated header, no split rows, no stranded section heading, print color-adjust) remain unchanged alongside the new fix", async () => {
      useLaboratoryOrder.mockReturnValue({ data: labOrder() });
      renderWithClient(<LaboratoryReportDialog orderId="lab-1" open onOpenChange={() => {}} />);
      await waitFor(() => expect(screen.getByText("Test Clinic")).toBeInTheDocument());

      const printCss = Array.from(document.querySelectorAll("style")).map((s) => s.textContent).join("\n");
      expect(printCss).toMatch(/#laboratory-report-printable thead\s*\{[^}]*display:\s*table-header-group/);
      expect(printCss).toMatch(/#laboratory-report-printable \.report-row\s*\{[^}]*break-inside:\s*avoid/);
      expect(printCss).toMatch(/#laboratory-report-printable \.section-heading\s*\{[^}]*break-after:\s*avoid/);
      expect(printCss).toMatch(/#laboratory-report-printable[^{]*\{[^}]*print-color-adjust:\s*exact/);
    });
  });
});
