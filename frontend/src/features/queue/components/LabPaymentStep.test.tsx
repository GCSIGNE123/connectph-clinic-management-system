import { StrictMode } from "react";
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

/** Renders under `React.StrictMode`, which double-invokes effects (mount ->
 * cleanup -> mount again) for the SAME component instance in dev - the
 * exact scenario that used to leave `LabPaymentStep` stuck forever on
 * "Preparing invoice..." (see the fix's comment in `LabPaymentStep.tsx`). */
function renderStepStrict(onPaid = vi.fn(), onBack = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const utils = render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <LabPaymentStep visitId="visit-1" onPaid={onPaid} onBack={onBack} />
      </QueryClientProvider>
    </StrictMode>
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

  describe("React 18 StrictMode regression (BUG: previously stuck forever on 'Preparing invoice...')", () => {
    it("A/B: under StrictMode, the invoice is created exactly once logically, 'Preparing invoice...' resolves, and payment UI becomes available", async () => {
      mockCreateInvoice.mockReset().mockResolvedValue(buildInvoice());
      renderStepStrict();

      // "Preparing invoice..." must not persist forever - it should resolve
      // to the real PaymentDialog once the (single) invoice-creation
      // request completes.
      expect(await screen.findByRole("heading", { name: "Record payment" })).toBeInTheDocument();
      expect(screen.queryByText("Preparing invoice...")).not.toBeInTheDocument();

      // Only one LOGICAL invoice-creation call: StrictMode may re-run the
      // effect, but the single-flight ref must dedupe the actual network
      // call to exactly one.
      expect(mockCreateInvoice).toHaveBeenCalledTimes(1);
      expect(mockCreateInvoice).toHaveBeenCalledWith("visit-1");
    });

    it("D: a zero-priced Laboratory invoice under StrictMode still skips payment and calls onPaid", async () => {
      mockCreateInvoice.mockReset().mockResolvedValue(
        buildInvoice({ status: "Paid", grandTotal: 0, balanceDue: 0, amountPaid: 0 })
      );
      const onPaid = vi.fn();
      renderStepStrict(onPaid);

      await waitFor(() => expect(onPaid).toHaveBeenCalledWith("invoice-1"));
      expect(screen.queryByRole("heading", { name: "Record payment" })).not.toBeInTheDocument();
      expect(mockCreateInvoice).toHaveBeenCalledTimes(1);
    });

    it("E: under StrictMode, a failed invoice creation still surfaces the error (not stuck) and Retry still works", async () => {
      mockCreateInvoice.mockReset().mockRejectedValue(new Error("network down"));
      const onPaid = vi.fn();
      const user = userEvent.setup();
      renderStepStrict(onPaid);

      expect(await screen.findByText(/Could not create the Laboratory invoice/i)).toBeInTheDocument();
      expect(onPaid).not.toHaveBeenCalled();

      mockCreateInvoice.mockResolvedValue(buildInvoice());
      await user.click(screen.getByRole("button", { name: "Retry" }));
      await waitFor(() => expect(screen.getByRole("heading", { name: "Record payment" })).toBeInTheDocument());
    });
  });
});
