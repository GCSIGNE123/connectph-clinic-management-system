import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider } from "@/components/ui/toast";
import { DoctorWorkspaceConfigSettings } from "./DoctorWorkspaceConfigSettings";
import type { Doctor, WorkspaceConfig } from "@/features/clinic-config/types";

const mockUpdate = vi.fn();

vi.mock("@/features/clinic-config/api/crud-factory", () => ({
  createCrudApi: () => ({
    get: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: (...args: unknown[]) => mockUpdate(...args),
    remove: vi.fn(),
    restore: vi.fn(),
  }),
}));

const SOAP_FIELD_IDS = [
  "chief_complaint", "history_of_present_illness", "past_medical_history", "family_history",
  "social_history", "review_of_systems", "subjective_notes",
  "blood_pressure", "pulse_rate", "respiratory_rate", "temperature", "height_cm", "weight_kg",
  "bmi", "oxygen_saturation", "physical_examination", "clinical_findings",
  "clinical_impression", "differential_diagnosis", "assessment_notes",
  "treatment_plan", "patient_instructions", "followup_recommendation", "referral_notes",
];

function allSoapFieldsEnabled(): Record<string, boolean> {
  return Object.fromEntries(SOAP_FIELD_IDS.map((id) => [id, true]));
}

function allSections(visible: boolean, required: boolean): WorkspaceConfig {
  return {
    sections: Object.fromEntries(
      ["vitals", "diagnosis", "prescription", "lab_requests", "certificate", "attachments"].map((id) => [id, { visible, required }])
    ),
    soap_fields: allSoapFieldsEnabled(),
  };
}

function buildDoctor(overrides: Partial<Doctor> = {}): Doctor {
  return {
    id: "doc-1", clinic_id: "clinic-1", doctor_code: "DOC-001",
    first_name: "Jose", last_name: "Rizal", status: "Active",
    created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z",
    workspace_config: allSections(true, false),
    ...overrides,
  };
}

function renderSettings(doctor: Doctor, onDoctorUpdated = vi.fn()) {
  return render(
    <ToastProvider>
      <DoctorWorkspaceConfigSettings doctor={doctor} onDoctorUpdated={onDoctorUpdated} />
    </ToastProvider>
  );
}

describe("DoctorWorkspaceConfigSettings", () => {
  it("renders a row with visible/required checkboxes for every consultation section", () => {
    renderSettings(buildDoctor());
    expect(screen.getByText("Vitals")).toBeInTheDocument();
    expect(screen.getByText("Diagnosis")).toBeInTheDocument();
    expect(screen.getByText("Prescription")).toBeInTheDocument();
    expect(screen.getByText("Lab Requests")).toBeInTheDocument();
    expect(screen.getByText("Medical Certificate")).toBeInTheDocument();
    expect(screen.getByText("Attachments")).toBeInTheDocument();
    expect(screen.getByLabelText("Vitals visible")).toBeChecked();
    expect(screen.getByLabelText("Vitals required")).not.toBeChecked();
  });

  it("unchecking Visible for a section also disables and unchecks Required", async () => {
    const user = userEvent.setup();
    renderSettings(buildDoctor({ workspace_config: allSections(true, true) }));

    expect(screen.getByLabelText("Diagnosis required")).toBeChecked();
    await user.click(screen.getByLabelText("Diagnosis visible"));

    expect(screen.getByLabelText("Diagnosis visible")).not.toBeChecked();
    expect(screen.getByLabelText("Diagnosis required")).not.toBeChecked();
    expect(screen.getByLabelText("Diagnosis required")).toBeDisabled();
  });

  it("applying the Simple preset updates the checkboxes", async () => {
    const user = userEvent.setup();
    renderSettings(buildDoctor());

    await user.click(screen.getByRole("button", { name: "Simple" }));

    expect(screen.getByLabelText("Vitals visible")).toBeChecked();
    expect(screen.getByLabelText("Lab Requests visible")).not.toBeChecked();
    expect(screen.getByLabelText("Medical Certificate visible")).not.toBeChecked();
  });

  it("Save Configuration is disabled until something changes, then calls the update API", async () => {
    mockUpdate.mockReset().mockResolvedValue(buildDoctor({ workspace_config: allSections(true, true) }));
    const onDoctorUpdated = vi.fn();
    const user = userEvent.setup();
    renderSettings(buildDoctor(), onDoctorUpdated);

    expect(screen.getByRole("button", { name: "Save Configuration" })).toBeDisabled();

    await user.click(screen.getByLabelText("Diagnosis required"));
    expect(screen.getByRole("button", { name: "Save Configuration" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Save Configuration" }));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith("doc-1", expect.objectContaining({ workspace_config: expect.any(Object) })));
    await waitFor(() => expect(onDoctorUpdated).toHaveBeenCalled());
  });
});

describe("DoctorWorkspaceConfigSettings - Consultation SOAP Fields", () => {
  it("renders every SOAP field, grouped by Subjective/Objective/Assessment/Plan, all checked by default", () => {
    renderSettings(buildDoctor());

    expect(screen.getByText("Consultation SOAP Fields")).toBeInTheDocument();
    expect(screen.getByText("Subjective")).toBeInTheDocument();
    expect(screen.getByText("Assessment")).toBeInTheDocument();
    expect(screen.getByText("Plan")).toBeInTheDocument();

    for (const label of [
      "Chief complaint", "History of present illness", "Past medical history", "Family history",
      "Social history", "Review of systems", "Additional subjective notes",
      "Blood pressure", "Pulse (bpm)", "Respiratory rate", "Temperature (°C)", "Height (cm)",
      "Weight (kg)", "BMI", "O₂ saturation (%)", "Physical examination", "Clinical findings",
      "Clinical impression", "Differential diagnosis", "Assessment notes",
      "Treatment plan", "Patient instructions", "Follow-up recommendation", "Referral notes",
    ]) {
      expect(screen.getByLabelText(label)).toBeChecked();
    }
  });

  it("unchecking a SOAP field and saving persists the change", async () => {
    mockUpdate.mockReset().mockResolvedValue(
      buildDoctor({ workspace_config: { ...allSections(true, false), soap_fields: { ...allSoapFieldsEnabled(), family_history: false } } })
    );
    const onDoctorUpdated = vi.fn();
    const user = userEvent.setup();
    renderSettings(buildDoctor(), onDoctorUpdated);

    expect(screen.getByRole("button", { name: "Save Configuration" })).toBeDisabled();

    await user.click(screen.getByLabelText("Family history"));
    expect(screen.getByLabelText("Family history")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Save Configuration" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Save Configuration" }));

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(
        "doc-1",
        expect.objectContaining({ workspace_config: expect.objectContaining({ soap_fields: expect.objectContaining({ family_history: false }) }) })
      )
    );
    await waitFor(() => expect(onDoctorUpdated).toHaveBeenCalled());
  });

  it("applying a section preset does not reset the doctor's SOAP field selections", async () => {
    const user = userEvent.setup();
    renderSettings(
      buildDoctor({ workspace_config: { ...allSections(true, false), soap_fields: { ...allSoapFieldsEnabled(), referral_notes: false } } })
    );

    expect(screen.getByLabelText("Referral notes")).not.toBeChecked();
    expect(screen.getByLabelText("Vitals required")).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Comprehensive" }));

    // Sections changed (preset applied)...
    expect(screen.getByLabelText("Vitals required")).toBeChecked();
    // ...but the SOAP field checklist is untouched.
    expect(screen.getByLabelText("Referral notes")).not.toBeChecked();
  });
});
