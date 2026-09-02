import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import { LaboratoryWorklistTable } from "./LaboratoryWorklistTable";
import type { LaboratoryOrder } from "@/features/laboratory/types";

const getOrder = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    collectSpecimen: vi.fn(),
    startProcessing: vi.fn(),
    releaseResults: vi.fn(),
    getOrder: (id: string) => getOrder(id),
  },
}));

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-20260101-000001", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: "L003",
    patientId: "patient-1", patientName: "Juana Dela Cruz", patientAge: null, patientSex: null, doctorId: "doctor-1", doctorName: "Jose Rizal",
    templateId: null, template: null, testType: "CBC", priority: "Routine", status: "Requested",
    scheduledDate: null, collectedAt: null, collectedBy: null, processingStartedAt: null,
    completedAt: null, releasedAt: null, releasedBy: null, invoiceItemId: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [],
    attachments: [],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

describe("LaboratoryWorklistTable", () => {
  it("renders a Queue # column header near Order #/Visit #", () => {
    renderWithClient(<LaboratoryWorklistTable orders={[labOrder()]} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toContain("Queue #");
    expect(headers.indexOf("Queue #")).toBeGreaterThan(headers.indexOf("Order #"));
    expect(headers.indexOf("Queue #")).toBeLessThan(headers.indexOf("Visit #"));
  });

  it("A: displays the associated Reception Queue number for an order that has one", () => {
    renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ queueNumber: "L003" })]} />);
    expect(screen.getByText("L003")).toBeInTheDocument();
  });

  it("B: shows a neutral placeholder instead of crashing when an order has no queue", () => {
    renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ queueNumber: null })]} />);
    // Order # and Visit # columns still render fine alongside the "-" Queue # cell.
    expect(screen.getByText("ORD-20260101-000001")).toBeInTheDocument();
    expect(screen.getByText("VIS-1")).toBeInTheDocument();
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
  });

  it("C: preserves existing worklist columns and content for unrelated fields", () => {
    renderWithClient(<LaboratoryWorklistTable orders={[labOrder()]} />);
    expect(screen.getByText("Juana Dela Cruz")).toBeInTheDocument();
    expect(screen.getByText("Jose Rizal")).toBeInTheDocument();
    expect(screen.getByText("CBC")).toBeInTheDocument();
  });

  describe("Print Results directly from the worklist", () => {
    function withinRow(patientName: string) {
      const row = screen.getByText(patientName).closest("tr") as HTMLTableRowElement;
      return within(row);
    }

    it("1: a Released order shows Print Results", () => {
      renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ status: "Released" })]} />);
      expect(withinRow("Juana Dela Cruz").getByRole("button", { name: "Print Results" })).toBeInTheDocument();
    });

    it("2: a Completed order shows Print Results (alongside the existing Release Results action, not instead of it)", () => {
      renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ status: "Completed" })]} />);
      const row = withinRow("Juana Dela Cruz");
      expect(row.getByRole("button", { name: "Print Results" })).toBeInTheDocument();
      expect(row.getByRole("button", { name: "Release Results" })).toBeInTheDocument();
    });

    it("3: a Processing order does not show Print Results", () => {
      renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ status: "Processing" })]} />);
      expect(withinRow("Juana Dela Cruz").queryByRole("button", { name: "Print Results" })).not.toBeInTheDocument();
    });

    it("4: a Requested order does not show Print Results", () => {
      renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ status: "Requested" })]} />);
      expect(withinRow("Juana Dela Cruz").queryByRole("button", { name: "Print Results" })).not.toBeInTheDocument();
    });

    it("5: clicking Print Results opens LaboratoryReportDialog for the correct laboratory order id", async () => {
      getOrder.mockReset().mockResolvedValue(labOrder({ id: "lab-1", status: "Released", clinicName: "Test Clinic" }));
      const user = userEvent.setup();
      renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ id: "lab-1", status: "Released" })]} />);

      await user.click(withinRow("Juana Dela Cruz").getByRole("button", { name: "Print Results" }));
      await waitFor(() => expect(getOrder).toHaveBeenCalledWith("lab-1"));
      expect(await screen.findByText("Test Clinic")).toBeInTheDocument();
    });

    it("6: multiple Released rows each print their own order - clicking row #2 prints row #2, not row #1", async () => {
      getOrder.mockReset().mockImplementation((id: string) =>
        Promise.resolve(labOrder({ id, status: "Released", clinicName: id === "lab-1" ? "Clinic For Row One" : "Clinic For Row Two" }))
      );
      const user = userEvent.setup();
      renderWithClient(
        <LaboratoryWorklistTable
          orders={[
            labOrder({ id: "lab-1", patientName: "Patient Row One", patientAge: null, patientSex: null, status: "Released" }),
            labOrder({ id: "lab-2", patientName: "Patient Row Two", patientAge: null, patientSex: null, status: "Released" }),
          ]}
        />
      );

      await user.click(withinRow("Patient Row Two").getByRole("button", { name: "Print Results" }));
      await waitFor(() => expect(getOrder).toHaveBeenCalledWith("lab-2"));
      expect(getOrder).not.toHaveBeenCalledWith("lab-1");
      expect(await screen.findByText("Clinic For Row Two")).toBeInTheDocument();
      expect(screen.queryByText("Clinic For Row One")).not.toBeInTheDocument();
    });

    it("8/9: existing Collect Specimen and Enter Results actions remain unaffected by the new Print Results action", () => {
      renderWithClient(
        <LaboratoryWorklistTable
          orders={[
            labOrder({ id: "lab-1", patientName: "Requested Patient", patientAge: null, patientSex: null, status: "Requested" }),
            labOrder({ id: "lab-2", patientName: "Processing Patient", patientAge: null, patientSex: null, status: "Processing" }),
          ]}
        />
      );
      expect(withinRow("Requested Patient").getByRole("button", { name: "Collect Specimen" })).toBeInTheDocument();
      expect(withinRow("Processing Patient").getByRole("button", { name: "Enter Results" })).toBeInTheDocument();
    });

    it("11: a Cancelled order (no next action, not print-eligible) still shows the neutral '-' placeholder, not a stray Print Results button", () => {
      renderWithClient(<LaboratoryWorklistTable orders={[labOrder({ status: "Cancelled" })]} />);
      const row = withinRow("Juana Dela Cruz");
      expect(row.queryByRole("button", { name: "Print Results" })).not.toBeInTheDocument();
      expect(row.getByText("-")).toBeInTheDocument();
    });
  });
});
