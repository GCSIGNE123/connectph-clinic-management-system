import type { WorkspaceConfig, WorkspaceSectionConfig } from "@/features/clinic-config/types";

/**
 * Mirrors `CONSULTATION_SECTIONS`/`WORKSPACE_CONFIG_PRESETS` in
 * `backend/app/models/doctor.py` - same convention this codebase already
 * uses for other backend-enum-shaped constants (e.g. `LaboratoryResultType`).
 * The backend is the source of truth for storage/validation/enforcement;
 * this file only drives rendering (checkbox list + preset buttons), so it
 * never needs to be authoritative on its own.
 */
export const CONSULTATION_SECTIONS: { id: string; label: string }[] = [
  { id: "vitals", label: "Vitals" },
  { id: "diagnosis", label: "Diagnosis" },
  { id: "prescription", label: "Prescription" },
  { id: "lab_requests", label: "Lab Requests" },
  { id: "certificate", label: "Medical Certificate" },
  { id: "attachments", label: "Attachments" },
];

function allSections(visible: boolean, required: boolean): Record<string, WorkspaceSectionConfig> {
  return Object.fromEntries(CONSULTATION_SECTIONS.map((s) => [s.id, { visible, required }]));
}

/**
 * Mirrors `SOAP_FIELD_GROUPS`/`SOAP_FIELD_IDS` in `backend/app/models/doctor.py`
 * - same convention as `CONSULTATION_SECTIONS` above. Grouped by SOAP
 * section purely for rendering the checklist; the backend stores/validates
 * a flat {field_id: enabled} map (`soap_fields`), not a grouped one.
 */
export const SOAP_FIELD_GROUPS: { id: string; label: string; fields: { id: string; label: string }[] }[] = [
  {
    id: "subjective",
    label: "Subjective",
    fields: [
      { id: "chief_complaint", label: "Chief complaint" },
      { id: "history_of_present_illness", label: "History of present illness" },
      { id: "past_medical_history", label: "Past medical history" },
      { id: "family_history", label: "Family history" },
      { id: "social_history", label: "Social history" },
      { id: "review_of_systems", label: "Review of systems" },
      { id: "subjective_notes", label: "Additional subjective notes" },
    ],
  },
  {
    id: "objective",
    label: "Objective / Vitals",
    fields: [
      { id: "blood_pressure", label: "Blood pressure" },
      { id: "pulse_rate", label: "Pulse (bpm)" },
      { id: "respiratory_rate", label: "Respiratory rate" },
      { id: "temperature", label: "Temperature (°C)" },
      { id: "height_cm", label: "Height (cm)" },
      { id: "weight_kg", label: "Weight (kg)" },
      { id: "bmi", label: "BMI" },
      { id: "oxygen_saturation", label: "O₂ saturation (%)" },
      { id: "physical_examination", label: "Physical examination" },
      { id: "clinical_findings", label: "Clinical findings" },
    ],
  },
  {
    id: "assessment",
    label: "Assessment",
    fields: [
      { id: "clinical_impression", label: "Clinical impression" },
      { id: "differential_diagnosis", label: "Differential diagnosis" },
      { id: "assessment_notes", label: "Assessment notes" },
    ],
  },
  {
    id: "plan",
    label: "Plan",
    fields: [
      { id: "treatment_plan", label: "Treatment plan" },
      { id: "patient_instructions", label: "Patient instructions" },
      { id: "followup_recommendation", label: "Follow-up recommendation" },
      { id: "referral_notes", label: "Referral notes" },
    ],
  },
];

function allSoapFieldsEnabled(): Record<string, boolean> {
  return Object.fromEntries(SOAP_FIELD_GROUPS.flatMap((g) => g.fields).map((f) => [f.id, true]));
}

export const DEFAULT_WORKSPACE_CONFIG: WorkspaceConfig = {
  sections: allSections(true, false),
  soap_fields: allSoapFieldsEnabled(),
};

export const WORKSPACE_CONFIG_PRESETS: Record<"simple" | "standard" | "comprehensive", WorkspaceConfig> = {
  simple: {
    sections: {
      ...allSections(false, false),
      vitals: { visible: true, required: false },
      diagnosis: { visible: true, required: false },
      prescription: { visible: true, required: false },
    },
    soap_fields: allSoapFieldsEnabled(),
  },
  standard: DEFAULT_WORKSPACE_CONFIG,
  comprehensive: {
    sections: {
      ...allSections(true, false),
      vitals: { visible: true, required: true },
      diagnosis: { visible: true, required: true },
      prescription: { visible: true, required: true },
    },
    soap_fields: allSoapFieldsEnabled(),
  },
};

/** Same normalization the backend applies on every read - a section
 * marked required while hidden always resolves to not-required. Used by
 * the consultation page so client-side rendering can never disagree with
 * what the server will actually enforce at completion time. */
export function isSectionVisible(config: WorkspaceConfig | undefined, sectionId: string): boolean {
  return config?.sections?.[sectionId]?.visible ?? true;
}

/** Same "missing = enabled" fallback the backend's `resolve_workspace_config`
 * applies - a doctor with no custom SOAP field configuration (or one saved
 * before this feature existed) sees every SOAP field, unchanged from
 * pre-feature behavior. */
export function isSoapFieldVisible(config: WorkspaceConfig | undefined, fieldId: string): boolean {
  return config?.soap_fields?.[fieldId] ?? true;
}
