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
});
