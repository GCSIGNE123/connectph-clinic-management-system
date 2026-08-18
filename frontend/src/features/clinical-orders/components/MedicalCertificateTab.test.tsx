import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MedicalCertificateTab } from "./MedicalCertificateTab";
import type { MedicalCertificate } from "@/features/clinical-orders/types";
import type { Diagnosis } from "@/features/consultation/types";

// `Label`/`Textarea` in this codebase are plain sibling elements (no
// `htmlFor`/`id` association), so `getByLabelText` doesn't work here -
// scope by the label's parent instead (each field is a
// `<div><Label/><Textarea/></div>`).
function getTextboxByLabel(labelText: string): HTMLElement {
  const label = screen.getByText(labelText, { selector: "label" });
  return within(label.parentElement as HTMLElement).getByRole("textbox");
}

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

const mockCreateDraft = vi.fn();
const mockUpdateDraft = vi.fn();
const mockIssue = vi.fn();
const mockCancel = vi.fn();
const mockReissue = vi.fn();
const mockRecordPrint = vi.fn();

let mockCertificates: MedicalCertificate[] = [];

vi.mock("@/features/clinical-orders/hooks/use-medical-certificates", () => ({
  useMedicalCertificatesForConsultation: () => ({ data: mockCertificates, isLoading: false }),
  useCreateMedicalCertificateDraft: () => ({ mutate: mockCreateDraft, isPending: false }),
  useUpdateMedicalCertificateDraft: () => ({ mutate: mockUpdateDraft, isPending: false }),
  useIssueMedicalCertificate: () => ({ mutate: mockIssue, isPending: false }),
  useCancelMedicalCertificate: () => ({ mutate: mockCancel, isPending: false }),
  useReissueMedicalCertificate: () => ({ mutate: mockReissue, isPending: false }),
  useRecordMedicalCertificatePrint: () => ({ mutate: mockRecordPrint }),
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: vi.fn().mockResolvedValue({ name: "Test Clinic" }) },
}));

function renderTab(props: Partial<React.ComponentProps<typeof MedicalCertificateTab>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MedicalCertificateTab
        consultationId="consult-1"
        visitId="visit-1"
        patientId="patient-1"
        canEdit={true}
        diagnoses={[]}
        visitNumber="VIS-000001"
        {...props}
      />
    </QueryClientProvider>
  );
}

describe("MedicalCertificateTab", () => {
  it("renders the tab's heading and an empty state when there are no certificates yet", () => {
    mockCertificates = [];
    renderTab();
    expect(screen.getByText("Medical Certificates")).toBeInTheDocument();
    expect(screen.getByText(/no medical certificates yet/i)).toBeInTheDocument();
  });

  it("draft form: shows type-specific fields only for Sick Leave", async () => {
    mockCertificates = [];
    const user = userEvent.setup();
    renderTab();

    expect(screen.queryByText("Rest days (optional)")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByDisplayValue("Medical Certificate"), "SickLeave");
    expect(screen.getByText("Rest days (optional)")).toBeInTheDocument();
    expect(screen.getByText("From (optional)")).toBeInTheDocument();
    expect(screen.getByText("To (optional)")).toBeInTheDocument();
  });

  it("diagnosis prefill: joins Primary/Final diagnoses into the findings field for a new draft", () => {
    const diagnoses: Diagnosis[] = [
      { id: "d1", consultationId: "consult-1", diagnosisType: "Primary", status: "Final", notes: "Acute pharyngitis", icd10Code: "J02.9", icd10Description: null, createdAt: "", updatedAt: "" },
      { id: "d2", consultationId: "consult-1", diagnosisType: "Secondary", status: "Working", notes: "Should not appear", icd10Code: null, icd10Description: null, createdAt: "", updatedAt: "" },
    ];
    mockCertificates = [];
    renderTab({ diagnoses });

    const findingsField = getTextboxByLabel("Findings") as HTMLTextAreaElement;
    expect(findingsField.value).toContain("Acute pharyngitis");
    expect(findingsField.value).not.toContain("Should not appear");
  });

  it("save draft calls the create-draft mutation with the form's contents", async () => {
    mockCertificates = [];
    mockCreateDraft.mockReset();
    const user = userEvent.setup();
    renderTab();

    await user.type(getTextboxByLabel("Findings"), "Test findings");
    await user.click(screen.getByRole("button", { name: "Save Draft" }));

    expect(mockCreateDraft).toHaveBeenCalledWith(
      expect.objectContaining({ findings: expect.stringContaining("Test findings") }),
      expect.anything()
    );
  });

  it("shows an Issue Certificate action for a Draft when canEdit is true, and calls issue on click", async () => {
    mockCertificates = [buildCertificate({ status: "Draft", certificateNumber: null, issuedAt: null })];
    mockIssue.mockReset();
    const user = userEvent.setup();
    renderTab();

    const issueButton = screen.getByRole("button", { name: "Issue Certificate" });
    await user.click(issueButton);
    expect(mockIssue).toHaveBeenCalledWith("cert-1");
  });

  it("issued certificate is not editable - no Edit action, only Print/Correct/Cancel", () => {
    mockCertificates = [buildCertificate({ status: "Issued" })];
    renderTab();

    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Print" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correct (Reissue)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("print opens the printable dialog and records the print", async () => {
    mockCertificates = [buildCertificate()];
    mockRecordPrint.mockReset();
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Print" }));

    expect(mockRecordPrint).toHaveBeenCalledWith("cert-1");
    expect(await screen.findAllByText("MC-20260818-000001")).not.toHaveLength(0);
    expect(screen.getAllByText(/Dr\. Jose Rizal/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/PRC License No\. 0123456/).length).toBeGreaterThan(0);
  });

  it("cancellation requires a reason before the Confirm button is enabled, then calls cancel", async () => {
    mockCertificates = [buildCertificate({ status: "Issued" })];
    mockCancel.mockReset();
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    const confirmButton = screen.getByRole("button", { name: "Confirm Cancel" });
    expect(confirmButton).toBeDisabled();

    await user.type(getTextboxByLabel("Reason (required)"), "Wrong patient");
    expect(confirmButton).not.toBeDisabled();
    await user.click(confirmButton);

    expect(mockCancel).toHaveBeenCalledWith({ certificateId: "cert-1", reason: "Wrong patient" }, expect.anything());
  });

  it("hides all edit/issue/cancel actions when canEdit is false (Receptionist/Cashier view+reprint only)", () => {
    mockCertificates = [buildCertificate({ status: "Issued" }), buildCertificate({ id: "draft-1", status: "Draft", certificateNumber: null })];
    renderTab({ canEdit: false });

    expect(screen.queryByRole("button", { name: "Issue Certificate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Correct (Reissue)" })).not.toBeInTheDocument();
    // Print/reprint remains available.
    expect(screen.getAllByRole("button", { name: "Print" }).length).toBeGreaterThan(0);
  });
});
