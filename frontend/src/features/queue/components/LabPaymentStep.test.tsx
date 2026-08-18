import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LabPaymentStep } from "./LabPaymentStep";

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const mockCreateInvoice = vi.fn();
vi.mock("@/features/billing/api/billing-api", () => ({
  billingApi: {
    createLaboratoryInvoiceForVisit: (...args: unknown[]) => mockCreateInvoice(...args),
  },
}));

function buildInvoice(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "invoice-1",
    invoiceNumber: "INV-000001",
    visitId: "visit-1",
    clinicId: "clinic-1",
    branchId: "branch-1",
    patientId: "pat-1",
    doctorId: null,
    invoiceDate: "2026-08-18",
    status: "PendingPayment",
    subtotal: 250,
    discountTotal: 0,
    taxTotal: null,
    grandTotal: 250,
    amountPaid: 0,
    balanceDue: 250,
    createdAt: "2026-08-18T00:00:00Z",
    updatedAt: "2026-08-18T00:00:00Z",
    patientName: "Maria Santos",
    patientNumber: "PAT-002",
    doctorName: null,
    visitNumber: "VIS-000001",
    branchName: "Main Branch",
    items: [
      {
        id: "item-1", invoiceId: "invoice-1", description: "BLOOD CHEMISTRY", itemType: "Laboratory",
        quantity: 1, unitPrice: 250, discountAmount: 0, taxAmount: null, lineTotal: 250, notes: null,
      },
    ],
    discounts: [],
    payments: [],
    ...overrides,
  };
}

function renderStep(onPaid = vi.fn(), onBack = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <LabPaymentStep visitId="visit-1" onPaid={onPaid} onBack={onBack} />
    </QueryClientProvider>
  );
  return { ...utils, onPaid, onBack };
}

describe("LabPaymentStep", () => {
  it("C: creates the invoice and opens the real PaymentDialog when payment is actually required (balance > 0)", async () => {
    mockCreateInvoice.mockReset().mockResolvedValue(buildInvoice());
    renderStep();

    // The real PaymentDialog (not a stub) renders once the invoice is
    // created with a positive balance due.
    expect(await screen.findByRole("heading", { name: "Record payment" })).toBeInTheDocument();
    expect(screen.getByText(/Balance due:/)).toBeInTheDocument();
    expect(mockCreateInvoice).toHaveBeenCalledWith("visit-1");
  });

  it("I: a zero-priced Laboratory service is already Paid on creation - no payment dialog, onPaid fires directly", async () => {
    mockCreateInvoice.mockReset().mockResolvedValue(
      buildInvoice({ status: "Paid", grandTotal: 0, balanceDue: 0, amountPaid: 0 })
    );
    const onPaid = vi.fn();
    renderStep(onPaid);

    await waitFor(() => expect(onPaid).toHaveBeenCalledWith("invoice-1"));
    // No "Record payment" dialog should ever have been shown for this case.
    expect(screen.queryByRole("heading", { name: "Record payment" })).not.toBeInTheDocument();
  });

  it("does not call onPaid while the invoice is still unpaid, and shows the invoice-preparation failure clearly", async () => {
    mockCreateInvoice.mockReset().mockRejectedValue(new Error("network down"));
    const onPaid = vi.fn();
    const user = userEvent.setup();
    renderStep(onPaid);

    expect(await screen.findByText(/Could not create the Laboratory invoice/i)).toBeInTheDocument();
    expect(onPaid).not.toHaveBeenCalled();

    // Retry re-attempts invoice creation rather than silently doing nothing.
    mockCreateInvoice.mockResolvedValue(buildInvoice());
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mockCreateInvoice).toHaveBeenCalledTimes(2));
  });

  it("Cancel (onBack) does not itself create a queue ticket - it only signals the parent to go back", async () => {
    mockCreateInvoice.mockReset().mockResolvedValue(buildInvoice());
    const onBack = vi.fn();
    const user = userEvent.setup();
    renderStep(vi.fn(), onBack);

    await screen.findByRole("heading", { name: "Record payment" });
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(onBack).toHaveBeenCalled();
  });
});
