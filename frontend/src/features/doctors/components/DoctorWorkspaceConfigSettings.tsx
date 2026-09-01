"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import type { Doctor, WorkspaceConfig } from "@/features/clinic-config/types";
import { CONSULTATION_SECTIONS, SOAP_FIELD_GROUPS, WORKSPACE_CONFIG_PRESETS } from "@/features/doctors/workspace-config";

const doctorsApi = createCrudApi<Doctor>("/doctors");

/**
 * Per-doctor consultation workspace configuration: which sections
 * (vitals/diagnosis/prescription/lab requests/certificate/attachments) show
 * up for THIS doctor's consultations, and which of the visible ones are
 * required before the doctor can mark a consultation complete - plus, below
 * that, which individual SOAP note fields this doctor wants to see at all.
 * Purely data-driven - `CONSULTATION_SECTIONS`/`SOAP_FIELD_GROUPS` are the
 * only places a section/field is named; nothing here ever special-cases a
 * specific doctor. Disabling a SOAP field only hides it from this doctor's
 * consultation form; it never deletes previously saved data for that field.
 *
 * Reuses the existing `PUT /doctors/{id}` endpoint (via `createCrudApi`)
 * rather than a dedicated one - `workspace_config` is just another Doctor
 * field, same as the rest of the profile form.
 */
export function DoctorWorkspaceConfigSettings({ doctor, onDoctorUpdated }: { doctor: Doctor; onDoctorUpdated: (doctor: Doctor) => void }) {
  const { toast } = useToast();
  const [draft, setDraft] = useState<WorkspaceConfig>(doctor.workspace_config);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(doctor.workspace_config);
  }, [doctor.id, doctor.workspace_config]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(doctor.workspace_config);

  function setSection(sectionId: string, patch: Partial<{ visible: boolean; required: boolean }>) {
    setDraft((prev) => {
      const current = prev.sections[sectionId] ?? { visible: true, required: false };
      const next = { ...current, ...patch };
      if (!next.visible) next.required = false; // required only ever applies to a visible section
      return { sections: { ...prev.sections, [sectionId]: next } };
    });
  }

  function applyPreset(preset: keyof typeof WORKSPACE_CONFIG_PRESETS) {
    // Presets only define section visibility/required - the doctor's own
    // SOAP field checklist (a separate, independently-configured concern)
    // is left exactly as-is rather than reset to all-enabled.
    setDraft((prev) => ({ ...prev, sections: WORKSPACE_CONFIG_PRESETS[preset].sections }));
  }

  function setSoapField(fieldId: string, enabled: boolean) {
    setDraft((prev) => ({
      ...prev,
      soap_fields: { ...prev.soap_fields, [fieldId]: enabled },
    }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await doctorsApi.update(doctor.id, { workspace_config: draft });
      onDoctorUpdated(updated);
      toast({ title: "Workspace configuration saved.", variant: "success", durationMs: 3000 });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save workspace configuration.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium">Presets</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => applyPreset("simple")} disabled={saving}>
            Simple
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => applyPreset("standard")} disabled={saving}>
            Standard
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => applyPreset("comprehensive")} disabled={saving}>
            Comprehensive
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="px-3 py-2">Section</th>
              <th className="px-3 py-2 text-center">Visible</th>
              <th className="px-3 py-2 text-center">Required</th>
            </tr>
          </thead>
          <tbody>
            {CONSULTATION_SECTIONS.map((section) => {
              const config = draft.sections[section.id] ?? { visible: true, required: false };
              return (
                <tr key={section.id} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-2 font-medium">{section.label}</td>
                  <td className="px-3 py-2 text-center">
                    <Checkbox
                      aria-label={`${section.label} visible`}
                      checked={config.visible}
                      disabled={saving}
                      onChange={(e) => setSection(section.id, { visible: e.target.checked })}
                    />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <Checkbox
                      aria-label={`${section.label} required`}
                      checked={config.required}
                      disabled={saving || !config.visible}
                      onChange={(e) => setSection(section.id, { required: e.target.checked })}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="text-sm font-medium">Consultation SOAP Fields</h3>
        <div className="mt-2 space-y-4">
          {SOAP_FIELD_GROUPS.map((group) => (
            <div key={group.id}>
              <h4 className="text-xs font-semibold uppercase text-muted-foreground">{group.label}</h4>
              <div className="mt-1.5 grid gap-y-1.5 gap-x-4 sm:grid-cols-2">
                {group.fields.map((field) => {
                  const enabled = draft.soap_fields?.[field.id] ?? true;
                  return (
                    <label key={field.id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        aria-label={field.label}
                        checked={enabled}
                        disabled={saving}
                        onChange={(e) => setSoapField(field.id, e.target.checked)}
                      />
                      {field.label}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="flex justify-end">
        <Button type="button" onClick={handleSave} disabled={saving || !isDirty} isLoading={saving}>
          Save Configuration
        </Button>
      </div>
    </div>
  );
}
