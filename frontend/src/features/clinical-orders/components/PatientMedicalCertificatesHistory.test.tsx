import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PatientMedicalCertificatesHistory } from "./PatientMedicalCertificatesHistory";
import type { MedicalCertificate } from "@/features/clinical-orders/types";

function buildCertificate(overrides: Partial<MedicalCertificate> = {}): MedicalCertificate {
  return {
    id: "cert-1", consultationId: "consult-1", visitId: "visit-1", patientId: "patient-1", doctorId: "doctor-1",
    certificateNumber: "MC-20260818-000001", certificateType: "MedicalCertificate", status: "Issued",
    findings: "Upper respiratory tract infection", recommendation: "Rest advised", restDays: null,
    dateFrom: null, dateTo: null, notes: null, issuedAt: "2026-08-18T00:00:00Z", cancelledAt: null,
    cancelledReason: null, cancelledBy: null, supersededById: null,
    createdAt: "2026-08-18T00:00:00Z", updatedAt: "2026-08-18T00:00:00Z",
    patientName: "Juan Dela Cruz", patientAge: 36, patientSex: "Male",
    doctorName: "Jose Rizal", doctorPrcLicense: "0123456", doctorPtrNumber: "9876543",
    clinicName: "Test Clinic", clinicLogoUrl: null, clinicAddress: "123 Rizal St.", clinicLicenseNumber: null,
    visitNumber: "VIS-000001",
    ...overrides,
  };
}

let mockCertificates: MedicalCertificate[] = [];
const mockRecordPrint = vi.fn();

vi.mock("@/features/clinical-orders/hooks/use-medical-certificates", () => ({
  useMedicalCertificatesForPatient: () => ({ data: mockCertificates, isLoading: false }),
  useRecordMedicalCertificatePrint: () => ({ mutate: mockRecordPrint }),
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn().mockResolvedValue({ name: "Test Clinic" }) },
}));

function renderHistory() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <PatientMedicalCertificatesHistory patientId="patient-1" />
    </QueryClientProvider>
  );
}

describe("PatientMedicalCertificatesHistory", () => {
  it("shows the doctor's PRC license and PTR number alongside the doctor name", () => {
    mockCertificates = [buildCertificate()];
    renderHistory();

    expect(screen.getByText(/PRC 0123456/)).toBeInTheDocument();
    expect(screen.getByText(/PTR 9876543/)).toBeInTheDocument();
  });

  it("allows reprinting an issued certificate from the patient's history", async () => {
    mockCertificates = [buildCertificate()];
    mockRecordPrint.mockReset();
    const user = userEvent.setup();
    renderHistory();

    await user.click(screen.getByRole("button", { name: "Print" }));

    expect(mockRecordPrint).toHaveBeenCalledWith("cert-1");
    expect(await screen.findAllByText("MC-20260818-000001")).not.toHaveLength(0);
    expect(screen.getAllByText(/PRC License No\. 0123456/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/PTR No\. 9876543/).length).toBeGreaterThan(0);
  });

  it("allows reprinting a cancelled certificate too (audit trail stays reprintable)", async () => {
    mockCertificates = [buildCertificate({ status: "Cancelled", cancelledReason: "Wrong patient" })];
    mockRecordPrint.mockReset();
    const user = userEvent.setup();
    renderHistory();

    await user.click(screen.getByRole("button", { name: "Print" }));
    expect(mockRecordPrint).toHaveBeenCalledWith("cert-1");
  });

  it("does not show a Print action for an unissued Draft (nothing to reprint yet)", () => {
    mockCertificates = [buildCertificate({ status: "Draft", certificateNumber: null, issuedAt: null })];
    renderHistory();

    expect(screen.queryByRole("button", { name: "Print" })).not.toBeInTheDocument();
  });

  it("shows the empty state when the patient has no certificates", () => {
    mockCertificates = [];
    renderHistory();
    expect(screen.getByText(/no medical certificates yet/i)).toBeInTheDocument();
  });
});
