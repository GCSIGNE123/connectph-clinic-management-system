import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ConsultationPage from "./page";
import type { Consultation } from "@/features/consultation/types";
import type { WorkspaceConfig } from "@/features/clinic-config/types";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "visit-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const useVisit = vi.fn();
vi.mock("@/features/visits/hooks/use-visit", () => ({ useVisit: (id: string) => useVisit(id) }));

const usePatient = vi.fn();
vi.mock("@/features/patients/hooks/use-patient", () => ({ usePatient: (id: string | undefined) => usePatient(id) }));

const useCurrentUser = vi.fn();
vi.mock("@/features/auth/hooks/use-current-user", () => ({ useCurrentUser: () => useCurrentUser() }));

const useOpenConsultation = vi.fn();
vi.mock("@/features/consultation/hooks/use-consultation", () => ({
  useOpenConsultation: (id: string) => useOpenConsultation(id),
  useCompleteConsultation: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/features/consultation/hooks/use-soap-autosave", () => ({
  useSoapAutosave: () => ({
    values: {}, setValues: vi.fn(), initialize: vi.fn(), saveNow: vi.fn(), isDirty: false, status: "idle",
  }),
}));

vi.mock("@/features/consultation/hooks/use-diagnoses", () => ({ useAddDiagnosis: () => ({ mutate: vi.fn(), isPending: false }) }));

vi.mock("@/features/consultation/hooks/use-attachments", () => ({
  useAttachments: () => ({ data: [] }),
  useUploadAttachment: () => ({ mutate: vi.fn(), isPending: false }),
}));

const clinicalOrdersProps: unknown[] = [];
vi.mock("@/features/clinical-orders/components/ClinicalOrdersTab", () => ({
  ClinicalOrdersTab: (props: unknown) => {
    clinicalOrdersProps.push(props);
    return <div data-testid="clinical-orders-tab" />;
  },
}));
vi.mock("@/features/clinical-orders/components/PrescriptionTab", () => ({
  PrescriptionTab: () => <div data-testid="prescription-tab" />,
}));
vi.mock("@/features/clinical-orders/components/MedicalCertificateTab", () => ({
  MedicalCertificateTab: () => <div data-testid="certificate-tab" />,
}));

function allSections(visible: boolean, required = false): WorkspaceConfig {
  return {
    sections: Object.fromEntries(
      ["vitals", "diagnosis", "prescription", "lab_requests", "certificate", "attachments"].map((id) => [id, { visible, required }])
    ),
  };
}

function buildConsultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
    id: "cons-1", visitId: "visit-1", branchId: "branch-1", doctorId: "doc-1", patientId: "patient-1",
    status: "InProgress", startedAt: "2026-08-01T00:00:00Z", completedAt: null, signedAt: null,
    doctorName: "Dr. Rizal", doctorPrcLicense: "123", doctorPtrNumber: "456",
    doctorWorkspaceConfig: allSections(true),
    patientName: "Juan Dela Cruz", patientNumber: "P-1", visitNumber: "VIS-1",
    soapNote: null, diagnoses: [], attachments: [],
    lock: { locked: true, lockedBy: "u1", lockedByName: "Dr. Rizal", lockedAt: "2026-08-01T00:00:00Z", isSelf: true },
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ConsultationPage />
    </QueryClientProvider>
  );
}

describe("ConsultationPage - Doctor Workspace Configuration (section show/hide)", () => {
  beforeEach(() => {
    useVisit.mockReturnValue({
      data: { id: "visit-1", visitNumber: "VIS-1", patientId: "patient-1", queueNumber: null, timeline: [] },
      isLoading: false,
    });
    usePatient.mockReturnValue({ data: { id: "patient-1", firstName: "Juan", lastName: "Dela Cruz", birthDate: "1990-01-01", gender: "Male" } });
    useCurrentUser.mockReturnValue({ data: { role: "Doctor" } });
    clinicalOrdersProps.length = 0;
  });

  it("shows every tab when the doctor has no custom configuration (all visible)", () => {
    useOpenConsultation.mockReturnValue({ data: buildConsultation(), isLoading: false, isError: false });
    renderPage();
    expect(screen.getByRole("tab", { name: "Diagnosis" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Prescription" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Medical Certificate" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Attachments" })).toBeInTheDocument();
  });

  it("hides the Diagnosis, Prescription, Medical Certificate, and Attachments tabs when their sections are not visible", () => {
    useOpenConsultation.mockReturnValue({
      data: buildConsultation({ doctorWorkspaceConfig: allSections(false) }),
      isLoading: false, isError: false,
    });
    renderPage();
    expect(screen.queryByRole("tab", { name: "Diagnosis" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Prescription" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Medical Certificate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Attachments" })).not.toBeInTheDocument();
    // Structural tabs, not gated by any section, always remain.
    expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Orders" })).toBeInTheDocument();
  });

  it("hides the Vitals card inside the SOAP tab when the vitals section is not visible", async () => {
    const user = userEvent.setup();
    useOpenConsultation.mockReturnValue({
      data: buildConsultation({ doctorWorkspaceConfig: allSections(false) }),
      isLoading: false, isError: false,
    });
    renderPage();
    await user.click(screen.getByRole("tab", { name: "SOAP" }));
    expect(screen.queryByText("Objective / Vitals")).not.toBeInTheDocument();
  });

  it("passes hideLaboratoryOption=true to ClinicalOrdersTab when lab_requests is hidden", async () => {
    const user = userEvent.setup();
    useOpenConsultation.mockReturnValue({
      data: buildConsultation({ doctorWorkspaceConfig: allSections(false) }),
      isLoading: false, isError: false,
    });
    renderPage();
    await user.click(screen.getByRole("tab", { name: "Orders" }));
    expect(clinicalOrdersProps.at(-1)).toMatchObject({ hideLaboratoryOption: true });
  });
});
