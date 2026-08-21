import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PatientLaboratoryHistory } from "./PatientLaboratoryHistory";
import type { LaboratoryOrder } from "@/features/laboratory/types";

const listForPatient = vi.fn();
const getOrder = vi.fn();

vi.mock("@/features/laboratory/api/laboratory-api", () => ({
  laboratoryApi: {
    listForPatient: (...args: unknown[]) => listForPatient(...args),
    getOrder: (id: string) => getOrder(id),
  },
}));

function labOrder(overrides: Partial<LaboratoryOrder> = {}): LaboratoryOrder {
  return {
    id: "lab-1", orderId: "order-1", orderNumber: "ORD-20260101-000001", visitId: "visit-1", visitNumber: "VIS-1",
    queueNumber: null, patientId: "patient-1", patientName: "Juan Dela Cruz", doctorId: "doctor-1", doctorName: "Jose Rizal",
    templateId: null, template: null, testType: "CBC", priority: "Routine", status: "Completed",
    scheduledDate: null, collectedAt: null, collectedBy: null, processingStartedAt: null,
    completedAt: "2026-01-01T00:00:00Z", releasedAt: null, releasedBy: null, invoiceItemId: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    results: [], attachments: [],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("PatientLaboratoryHistory", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when the patient has no laboratory orders", async () => {
    listForPatient.mockResolvedValueOnce([]);
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);
    expect(await screen.findByText(/no laboratory orders yet/i)).toBeInTheDocument();
  });

  it("renders the patient's laboratory history", async () => {
    listForPatient.mockResolvedValueOnce([labOrder()]);
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    expect(await screen.findByText("ORD-20260101-000001")).toBeInTheDocument();
    expect(screen.getByText("CBC")).toBeInTheDocument();
    expect(screen.getByText("Jose Rizal")).toBeInTheDocument();
  });

  it("shows a Print Results action for a Released historical result", async () => {
    listForPatient.mockResolvedValueOnce([labOrder({ status: "Released" })]);
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    await screen.findByText("ORD-20260101-000001");
    expect(screen.getByRole("button", { name: /print results/i })).toBeInTheDocument();
  });

  it("shows a Print Results action for a Completed historical result", async () => {
    listForPatient.mockResolvedValueOnce([labOrder({ status: "Completed" })]);
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    await screen.findByText("ORD-20260101-000001");
    expect(screen.getByRole("button", { name: /print results/i })).toBeInTheDocument();
  });

  it("does not show a Print Results action for a Pending/Processing historical entry", async () => {
    listForPatient.mockResolvedValueOnce([labOrder({ status: "Processing" })]);
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    await screen.findByText("ORD-20260101-000001");
    expect(screen.queryByRole("button", { name: /print results/i })).not.toBeInTheDocument();
    // View is still available, so the row isn't a dead end - just not printable.
    expect(screen.getByRole("button", { name: /^view$/i })).toBeInTheDocument();
  });

  it("clicking Print Results opens the existing LaboratoryReportDialog with the correct historical order id", async () => {
    listForPatient.mockResolvedValueOnce([labOrder({ id: "lab-42", status: "Released" })]);
    getOrder.mockResolvedValueOnce(labOrder({ id: "lab-42", status: "Released", clinicName: "Test Clinic" }));
    const user = userEvent.setup();
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    await screen.findByText("ORD-20260101-000001");
    await user.click(screen.getByRole("button", { name: /print results/i }));

    await waitFor(() => expect(getOrder).toHaveBeenCalledWith("lab-42"));
    expect(await screen.findByRole("heading", { name: /laboratory report/i })).toBeInTheDocument();
  });

  it("gives each of multiple historical results its own independent Print action", async () => {
    listForPatient.mockResolvedValueOnce([
      labOrder({ id: "lab-1", orderNumber: "ORD-1", status: "Released" }),
      labOrder({ id: "lab-2", orderNumber: "ORD-2", status: "Completed" }),
      labOrder({ id: "lab-3", orderNumber: "ORD-3", status: "Processing" }),
    ]);
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    await screen.findByText("ORD-1");
    // Two eligible (Released, Completed) + zero for the Processing one.
    expect(screen.getAllByRole("button", { name: /print results/i })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /^view$/i })).toHaveLength(3);
  });

  it("opening View still surfaces the order's own Print Report action (same underlying dialog as Visit History)", async () => {
    listForPatient.mockResolvedValueOnce([labOrder({ id: "lab-7", status: "Released" })]);
    const user = userEvent.setup();
    renderWithClient(<PatientLaboratoryHistory patientId="patient-1" />);

    await screen.findByText("ORD-20260101-000001");
    await user.click(screen.getByRole("button", { name: /^view$/i }));

    expect(await screen.findByRole("button", { name: /print report/i })).toBeInTheDocument();
  });
});
