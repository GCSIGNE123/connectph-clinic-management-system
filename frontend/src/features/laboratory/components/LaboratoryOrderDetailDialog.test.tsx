import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaboratoryOrderDetailDialog } from "./LaboratoryOrderDetailDialog";
import type { LaboratoryOrder } from "@/features/laboratory/types";

const getOrder = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    getOrder: (id: string) => getOrder(id),
  },
}));

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-1", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: null, patientId: "patient-1", patientName: "Juan Dela Cruz", doctorId: null, doctorName: null,
    templateId: null, template: null, testType: "CBC", priority: null, status: "Completed",
    scheduledDate: null, collectedAt: null, collectedBy: null, processingStartedAt: null, completedAt: null,
    releasedAt: null, releasedBy: null, invoiceItemId: null, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [], attachments: [],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("LaboratoryOrderDetailDialog: Phase 4G Print Report entry point", () => {
  it("shows Print Report for a Completed order", () => {
    renderWithClient(<LaboratoryOrderDetailDialog order={labOrder({ status: "Completed" })} open onOpenChange={() => {}} />);
    expect(screen.getByRole("button", { name: /print report/i })).toBeInTheDocument();
  });

  it("shows Print Report for a Released order", () => {
    renderWithClient(<LaboratoryOrderDetailDialog order={labOrder({ status: "Released" })} open onOpenChange={() => {}} />);
    expect(screen.getByRole("button", { name: /print report/i })).toBeInTheDocument();
  });

  it("hides Print Report for a Processing order (results not yet final)", () => {
    renderWithClient(<LaboratoryOrderDetailDialog order={labOrder({ status: "Processing" })} open onOpenChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /print report/i })).not.toBeInTheDocument();
  });

  it("clicking Print Report fetches the order fresh (for clinicName) and opens the report", async () => {
    const order = labOrder({
      status: "Completed",
      results: [
        {
          id: "res-1", parameterName: "Hemoglobin", resultType: "Numeric", numericValue: 14, textValue: null,
          normalRange: null, units: null, interpretation: null, remarks: null, rangeLow: null, rangeHigh: null,
          enteredBy: "user-1", enteredAt: "2026-01-01T00:00:00Z", structuredValue: null, site: null,
        },
      ],
      clinicName: "Test Clinic",
    });
    getOrder.mockResolvedValue(order);
    renderWithClient(<LaboratoryOrderDetailDialog order={order} open onOpenChange={() => {}} />);

    await userEvent.click(screen.getByRole("button", { name: /print report/i }));
    await waitFor(() => expect(getOrder).toHaveBeenCalledWith("lab-1"));
    expect(await screen.findByText("Test Clinic")).toBeInTheDocument();
  });
});
