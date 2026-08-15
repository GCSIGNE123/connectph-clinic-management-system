import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PrescriptionTab } from "./PrescriptionTab";
import type { Prescription } from "@/features/clinical-orders/types";

const mockPrescription: Prescription = {
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
      id: "item-1",
      medicine: "Amoxicillin",
      strength: "500mg",
      dosage: "1 tab",
      frequency: "TID",
      duration: "7 days",
      quantity: "21 tabs",
      route: "Oral",
      instructions: null,
      substitutionAllowed: true,
    },
  ],
};

vi.mock("@/features/clinical-orders/hooks/use-clinical-orders", () => ({
  usePrescriptionsForConsultation: () => ({ data: [mockPrescription], isLoading: false }),
  useCreatePrescription: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn().mockResolvedValue({}) },
}));

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("PrescriptionTab print output", () => {
  it("prints the doctor's PRC license and PTR number directly below the doctor's name", async () => {
    renderWithClient(
      <PrescriptionTab
        consultationId="consult-1"
        visitId="visit-1"
        canEdit={false}
        doctorName="Jose Rizal"
        doctorPrcLicense="0123456"
        doctorPtrNumber="9876543"
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /print/i }));

    const signatureBlock = screen.getByTestId("prescription-signature-block");
    expect(signatureBlock).toHaveTextContent("Dr. Jose Rizal");
    expect(signatureBlock).toHaveTextContent("PRC License No. 0123456");
    expect(signatureBlock).toHaveTextContent("PTR No. 9876543");
  });

  it("omits PRC/PTR lines when the doctor record has none on file", async () => {
    renderWithClient(
      <PrescriptionTab consultationId="consult-1" visitId="visit-1" canEdit={false} doctorName="Jose Rizal" />
    );

    await userEvent.click(screen.getByRole("button", { name: /print/i }));

    const signatureBlock = screen.getByTestId("prescription-signature-block");
    expect(signatureBlock).not.toHaveTextContent("PRC License No.");
    expect(signatureBlock).not.toHaveTextContent("PTR No.");
  });
});
