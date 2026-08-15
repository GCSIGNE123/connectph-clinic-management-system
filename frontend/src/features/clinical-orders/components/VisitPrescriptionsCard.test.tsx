import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { VisitPrescriptionsCard } from "./VisitPrescriptionsCard";
import type { Prescription } from "@/features/clinical-orders/types";

const listPrescriptionsForVisit = vi.fn();

vi.mock("@/features/clinical-orders/api/clinical-orders-api", () => ({
  clinicalOrdersApi: {
    listPrescriptionsForVisit: (...args: unknown[]) => listPrescriptionsForVisit(...args),
  },
}));

function prescription(overrides: Partial<Prescription> = {}): Prescription {
  return {
    id: "rx-1",
    consultationId: "consult-1",
    visitId: "visit-1",
    patientId: "patient-1",
    doctorId: "doctor-1",
    prescriptionNumber: "RX-20260101-000001",
    status: "Finalized",
    createdAt: "2026-01-01T00:00:00Z",
    items: [
      {
        id: "item-1", medicine: "Amoxicillin", strength: "500mg", dosage: "1 tab", route: "Oral",
        frequency: "TID", duration: "7 days", quantity: "21", instructions: "Take after meals", substitutionAllowed: true,
      },
    ],
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("VisitPrescriptionsCard", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when there are no prescriptions", async () => {
    listPrescriptionsForVisit.mockResolvedValueOnce([]);
    renderWithClient(<VisitPrescriptionsCard visitId="visit-1" />);
    expect(await screen.findByText(/no prescriptions yet/i)).toBeInTheDocument();
  });

  it("renders a prescription row as clickable with a visible affordance", async () => {
    listPrescriptionsForVisit.mockResolvedValueOnce([prescription()]);
    renderWithClient(<VisitPrescriptionsCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /RX-20260101-000001/i });
    expect(row).toHaveClass("cursor-pointer");
    expect(row.querySelector("svg")).toBeInTheDocument();
  });

  it("opens the prescription detail dialog on click, showing full item details", async () => {
    listPrescriptionsForVisit.mockResolvedValueOnce([prescription()]);
    renderWithClient(<VisitPrescriptionsCard visitId="visit-1" />);

    const row = await screen.findByRole("button", { name: /RX-20260101-000001/i });
    await userEvent.click(row);

    expect(await screen.findByRole("heading", { name: /prescription rx-20260101-000001/i })).toBeInTheDocument();
    expect(screen.getByText(/1\. Amoxicillin 500mg/)).toBeInTheDocument();
    expect(screen.getByText(/Sig: Take after meals/)).toBeInTheDocument();
  });
});
