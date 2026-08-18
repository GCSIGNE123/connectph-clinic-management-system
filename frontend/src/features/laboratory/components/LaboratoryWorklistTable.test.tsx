import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import { LaboratoryWorklistTable } from "./LaboratoryWorklistTable";
import type { LaboratoryOrder } from "@/features/laboratory/types";

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    collectSpecimen: vi.fn(),
    startProcessing: vi.fn(),
    releaseResults: vi.fn(),
  },
}));

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-20260101-000001", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: "L003",
    patientId: "patient-1", patientName: "Juana Dela Cruz", doctorId: "doctor-1", doctorName: "Jose Rizal",
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
});
