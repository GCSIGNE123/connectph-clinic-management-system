import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import ConsultationPage from "./page";
import type { Consultation } from "@/features/consultation/types";
import type { WorkspaceConfig } from "@/features/clinic-config/types";

// Task #2 - the SOAP suggestion fields on the real consultation page.

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "visit-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/features/visits/hooks/use-visit", () => ({
  useVisit: () => ({ data: { id: "visit-1", visitNumber: "VIS-1", patientId: "patient-1", queueNumber: null, timeline: [] }, isLoading: false }),
}));
vi.mock("@/features/patients/hooks/use-patient", () => ({
  usePatient: () => ({
    data: {
      id: "patient-1", firstName: "Juan", lastName: "Dela Cruz", birthDate: "1990-01-01", gender: "Male",
      addressLine: "123 Rizal St", barangay: "Poblacion", city: "Quezon City", province: "Metro Manila", zipCode: "1100",
    },
  }),
}));
vi.mock("@/features/auth/hooks/use-current-user", () => ({ useCurrentUser: () => ({ data: { role: "Doctor" } }) }));

const useOpenConsultation = vi.fn();
vi.mock("@/features/consultation/hooks/use-consultation", () => ({
  useOpenConsultation: (id: string) => useOpenConsultation(id),
  useCompleteConsultation: () => ({ mutate: vi.fn(), isPending: false }),
}));

// A stateful stand-in for the real autosave hook so typing/selecting is reflected in the UI.
vi.mock("@/features/consultation/hooks/use-soap-autosave", () => ({
  useSoapAutosave: () => {
    const [values, setValues] = useState<Record<string, unknown>>({});
    return { values, setValues, initialize: (v: Record<string, unknown>) => setValues(v), saveNow: vi.fn(), isDirty: false, status: "idle" };
  },
}));

const learned: Record<string, string[]> = {};
vi.mock("@/features/consultation/hooks/use-soap-suggestions", () => ({
  useSoapSuggestions: (field: string, enabled: boolean) => ({ data: enabled ? learned[field] ?? [] : undefined }),
}));

vi.mock("@/features/consultation/hooks/use-diagnoses", () => ({ useAddDiagnosis: () => ({ mutate: vi.fn(), isPending: false }) }));
vi.mock("@/features/consultation/hooks/use-attachments", () => ({
  useAttachments: () => ({ data: [] }),
  useUploadAttachment: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/features/clinical-orders/components/ClinicalOrdersTab", () => ({ ClinicalOrdersTab: () => <div /> }));
vi.mock("@/features/clinical-orders/components/PrescriptionTab", () => ({ PrescriptionTab: () => <div /> }));
vi.mock("@/features/clinical-orders/components/MedicalCertificateTab", () => ({ MedicalCertificateTab: () => <div /> }));

function config(): WorkspaceConfig {
  return {
    sections: Object.fromEntries(
      ["vitals", "diagnosis", "prescription", "lab_requests", "certificate", "attachments"].map((id) => [id, { visible: true, required: false }])
    ),
    soap_fields: Object.fromEntries(
      [
        "chief_complaint", "history_of_present_illness", "past_medical_history", "family_history", "social_history",
        "review_of_systems", "subjective_notes", "blood_pressure", "pulse_rate", "respiratory_rate", "temperature",
        "height_cm", "weight_kg", "bmi", "oxygen_saturation", "physical_examination", "clinical_findings",
        "clinical_impression", "differential_diagnosis", "assessment_notes", "treatment_plan", "patient_instructions",
        "followup_recommendation", "referral_notes",
      ].map((id) => [id, true])
    ),
  };
}

function consultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
    id: "cons-1", visitId: "visit-1", branchId: "b1", doctorId: "d1", patientId: "patient-1", status: "InProgress",
    startedAt: "2026-08-01T00:00:00Z", completedAt: null, signedAt: null, doctorName: "Dr. Rizal",
    doctorPrcLicense: "1", doctorPtrNumber: "2", doctorWorkspaceConfig: config(),
    patientName: "Juan Dela Cruz", patientNumber: "P-1", visitNumber: "VIS-1", soapNote: null, diagnoses: [], attachments: [],
    lock: { locked: true, lockedBy: "u1", lockedByName: "Dr. Rizal", lockedAt: "2026-08-01T00:00:00Z", isSelf: true },
    ...overrides,
  };
}

async function openTab(name: string) {
  const user = userEvent.setup();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ConsultationPage />
    </QueryClientProvider>
  );
  await user.click(screen.getByRole("tab", { name }));
  return user;
}

const field = (label: string) => screen.getByLabelText(label) as HTMLTextAreaElement;
const plainField = (label: string) => screen.getByText(label).parentElement!.querySelector("textarea") as HTMLTextAreaElement;

describe("ConsultationPage - SOAP suggestion fields (Task #2)", () => {
  beforeEach(() => {
    for (const k of Object.keys(learned)) delete learned[k];
    useOpenConsultation.mockReturnValue({ data: consultation(), isLoading: false, isError: false });
  });

  it("the 8 approved fields offer suggestions (static starters when nothing is learned)", async () => {
    const user = await openTab("SOAP");
    const expected: Record<string, string> = {
      "Chief complaint": "Fever",
      "Physical examination": "Awake, alert, no acute distress",
      "Clinical findings": "No abnormal findings",
      "Clinical impression": "Acute pharyngitis",
      "Differential diagnosis": "Viral infection",
      "Treatment plan": "Rest and hydration",
      "Patient instructions": "Take medications as prescribed",
      "Follow-up recommendation": "Follow up in 1 week",
    };
    for (const [label, suggestion] of Object.entries(expected)) {
      await user.click(field(label));
      expect(await screen.findByRole("button", { name: suggestion })).toBeInTheDocument();
      await user.click(document.body);
    }
  });

  it("the long narrative fields stay plain textareas with NO suggestions", async () => {
    const user = await openTab("SOAP");
    for (const label of [
      "History of present illness", "Past medical history", "Family history", "Social history",
      "Review of systems", "Additional subjective notes", "Assessment notes", "Referral notes",
    ]) {
      const box = plainField(label);
      expect(box.tagName).toBe("TEXTAREA");
      await user.click(box);
      expect(screen.queryAllByRole("button", { name: /Fever|Rest and hydration|Follow up|Viral/ })).toHaveLength(0);
      await user.type(box, "free text");
      expect(box).toHaveValue("free text");
      await user.click(document.body);
    }
  });

  it("learned clinic suggestions come first; selecting one fills the field and it stays editable", async () => {
    learned.chief_complaint = ["Persistent dry cough"];
    const user = await openTab("SOAP");
    await user.click(field("Chief complaint"));
    const dropdown = screen.getByRole("button", { name: "Persistent dry cough" }).closest("ul") as HTMLElement;
    const labels = within(dropdown).getAllByRole("button").map((b) => b.textContent);
    expect(labels[0]).toBe("Persistent dry cough"); // learned first
    expect(labels).toContain("Fever"); // then the static starters
    await user.click(screen.getByRole("button", { name: "Persistent dry cough" }));
    expect(field("Chief complaint")).toHaveValue("Persistent dry cough");
    await user.type(field("Chief complaint"), ", 3 days");
    expect(field("Chief complaint")).toHaveValue("Persistent dry cough, 3 days");
  });

  it("custom text works without any suggestion", async () => {
    const user = await openTab("SOAP");
    await user.type(field("Treatment plan"), "Bespoke plan for this patient");
    expect(field("Treatment plan")).toHaveValue("Bespoke plan for this patient");
  });

  it("existing (historical) SOAP values render, remain editable, and other fields are untouched", async () => {
    useOpenConsultation.mockReturnValue({
      data: consultation({
        soapNote: {
          id: "s1", consultationId: "cons-1", chiefComplaint: "Old chief complaint", historyOfPresentIllness: "Old HPI",
          treatmentPlan: "Old plan line 1\nOld plan line 2", clinicalImpression: null,
        } as unknown as Consultation["soapNote"],
      }),
      isLoading: false, isError: false,
    });
    const user = await openTab("SOAP");
    expect(field("Chief complaint")).toHaveValue("Old chief complaint");
    expect(plainField("History of present illness")).toHaveValue("Old HPI");
    expect(field("Treatment plan")).toHaveValue("Old plan line 1\nOld plan line 2");
    expect(field("Clinical impression")).toHaveValue(""); // null renders empty, not "null"
    await user.type(field("Chief complaint"), " edited");
    expect(field("Chief complaint")).toHaveValue("Old chief complaint edited");
    expect(plainField("History of present illness")).toHaveValue("Old HPI");
  });

  it("read-only viewers get disabled fields and no suggestions", async () => {
    useOpenConsultation.mockReturnValue({
      data: consultation({ lock: { locked: true, lockedBy: "u9", lockedByName: "Someone", lockedAt: "2026-08-01T00:00:00Z", isSelf: false } }),
      isLoading: false, isError: false,
    });
    const user = await openTab("SOAP");
    expect(field("Chief complaint")).toBeDisabled();
    await user.click(field("Chief complaint"));
    expect(screen.queryByRole("button", { name: "Fever" })).not.toBeInTheDocument();
  });

  it("the Diagnosis tab offers learned ICD-10 code/description suggestions (no static catalog) and free text", async () => {
    learned.icd10_code = ["J06.9"];
    learned.icd10_description = ["Acute upper respiratory infection, unspecified"];
    const user = await openTab("Diagnosis");
    await user.click(screen.getByLabelText("ICD-10 code"));
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toContain("J06.9");
    await user.click(screen.getByRole("button", { name: "J06.9" }));
    expect(screen.getByLabelText("ICD-10 code")).toHaveValue("J06.9");

    await user.click(screen.getByLabelText("ICD-10 description"));
    await user.click(screen.getByRole("button", { name: "Acute upper respiratory infection, unspecified" }));
    expect(screen.getByLabelText("ICD-10 description")).toHaveValue("Acute upper respiratory infection, unspecified");

    await user.clear(screen.getByLabelText("ICD-10 code"));
    await user.type(screen.getByLabelText("ICD-10 code"), "Z00.0");
    expect(screen.getByLabelText("ICD-10 code")).toHaveValue("Z00.0");
  });

  it("keeps the Task #7 patient address on the Overview (after Age/Gender) unchanged", async () => {
    await openTab("Overview");
    const address = screen.getByText("Address");
    expect(address.parentElement).toHaveTextContent("123 Rizal St, Poblacion, Quezon City, Metro Manila, 1100");
    const labels = screen.getAllByText(/^(Age \/ Gender|Address|Blood type)$/).map((n) => n.textContent);
    expect(labels.indexOf("Address")).toBeGreaterThan(labels.indexOf("Age / Gender"));
    expect(within(address.parentElement as HTMLElement).queryByText("null")).not.toBeInTheDocument();
  });
});
