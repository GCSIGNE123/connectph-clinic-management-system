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

export const DEFAULT_WORKSPACE_CONFIG: WorkspaceConfig = { sections: allSections(true, false) };

export const WORKSPACE_CONFIG_PRESETS: Record<"simple" | "standard" | "comprehensive", WorkspaceConfig> = {
  simple: {
    sections: {
      ...allSections(false, false),
      vitals: { visible: true, required: false },
      diagnosis: { visible: true, required: false },
      prescription: { visible: true, required: false },
    },
  },
  standard: DEFAULT_WORKSPACE_CONFIG,
  comprehensive: {
    sections: {
      ...allSections(true, false),
      vitals: { visible: true, required: true },
      diagnosis: { visible: true, required: true },
      prescription: { visible: true, required: true },
    },
  },
};

/** Same normalization the backend applies on every read - a section
 * marked required while hidden always resolves to not-required. Used by
 * the consultation page so client-side rendering can never disagree with
 * what the server will actually enforce at completion time. */
export function isSectionVisible(config: WorkspaceConfig | undefined, sectionId: string): boolean {
  return config?.sections?.[sectionId]?.visible ?? true;
}
