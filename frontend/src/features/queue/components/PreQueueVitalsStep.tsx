"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import {
  EMPTY_INTAKE,
  IntakeSubjectiveFields,
  IntakeVitalInput,
  changedIntakePayload,
  intakeFromNote,
  type IntakeKey,
  type IntakeValues,
} from "@/features/consultation/components/intake-fields";
import { ApiError } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";

/**
 * Phase 21 (Vitals-before-Queue): the "Enter Vitals" step embedded inside
 * `NewQueueDialog`, for a draft Visit created via `POST /visits/pre-queue`
 * (status `DraftVitals`, no Queue ticket yet). Reuses the exact same
 * backend endpoints as `ReceptionVitalsDialog` (Item 4-5's after-queueing
 * vitals-edit flow) - `open-for-reception` + `soap/subjective-objective` -
 * since those endpoints only ever look at `visit_id`/`visit.doctor_id` and
 * don't care whether a Queue ticket exists yet. This is a separate
 * component (rather than reusing `ReceptionVitalsDialog` directly) because
 * it renders inline as a dialog *step*, not its own `<Dialog>`, and adds
 * live BMI and the required-vitals gate that dialog doesn't have.
 *
 * Task #6: offers the same approved Subjective + vitals fields as
 * `ReceptionVitalsDialog` (shared via `intake-fields`), and - like it - sends
 * only the fields changed since the step loaded. Doctor-only fields are never
 * offered. The queue lifecycle (this step happens BEFORE the ticket exists) is unchanged.
 */
export function PreQueueVitalsStep({
  visitId,
  onSaved,
  onBack,
}: {
  visitId: string;
  onSaved: () => void;
  onBack: () => void;
}) {
  const { toast } = useToast();
  const [consultationId, setConsultationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalidFields, setInvalidFields] = useState<Set<string>>(new Set());
  const fieldRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const [values, setValues] = useState<IntakeValues>(EMPTY_INTAKE);
  const baselineRef = useRef<IntakeValues>(EMPTY_INTAKE);
  const setField = (key: IntakeKey, value: string) => setValues((v) => ({ ...v, [key]: value }));

  useEffect(() => {
    setLoading(true);
    setError(null);
    consultationApi
      .openForReception(visitId)
      .then(async (consultation) => {
        setConsultationId(consultation.id);
        const note = await consultationApi.getSubjectiveObjective(consultation.id);
        const loaded = intakeFromNote(note);
        baselineRef.current = loaded;
        setValues(loaded);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not open this visit's consultation.");
      })
      .finally(() => setLoading(false));
  }, [visitId]);

  // Live BMI preview - display-only; the backend independently recomputes
  // and stores this from height_cm/weight_kg on save (see
  // `ConsultationService._compute_bmi`), this is purely so the receptionist
  // sees it update as they type, without waiting on a round trip.
  const bmiPreview = useMemo(() => {
    const h = Number(values.heightCm);
    const w = Number(values.weightKg);
    if (!h || !w || h <= 0) return null;
    const meters = h / 100;
    return Math.round((w / (meters * meters)) * 100) / 100;
  }, [values.heightCm, values.weightKg]);

  const REQUIRED_FIELDS: Array<[IntakeKey, string]> = [
    ["bloodPressure", "Blood Pressure"],
    ["temperature", "Temperature"],
    ["pulseRate", "Pulse Rate"],
    ["respiratoryRate", "Respiratory Rate"],
    ["oxygenSaturation", "SpO2"],
    ["heightCm", "Height"],
    ["weightKg", "Weight"],
  ];
  const missingRequired = REQUIRED_FIELDS.filter(([key]) => !values[key]).map(([, label]) => label);

  const handleSaveAndClose = async () => {
    if (!consultationId) return;
    const missingKeys = REQUIRED_FIELDS.filter(([key]) => !values[key]).map(([key]) => key);
    if (missingKeys.length > 0) {
      setInvalidFields(new Set(missingKeys));
      setError("Please fill in all required vitals before saving.");
      fieldRefs.current[missingKeys[0]]?.focus();
      return;
    }
    setInvalidFields(new Set());
    setSaving(true);
    setError(null);
    try {
      await consultationApi.saveSubjectiveObjective(consultationId, changedIntakePayload(baselineRef.current, values));
      toast({ title: "Vitals saved successfully.", variant: "success", durationMs: 3000 });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save vitals. The consultation may already be signed.");
    } finally {
      setSaving(false);
    }
  };

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      onBack();
      return;
    }
    if (e.key === "Enter") {
      const target = e.target as HTMLElement;
      if (target.tagName === "TEXTAREA") return;
      e.preventDefault();
      void handleSaveAndClose();
    }
  }

  const vital = (key: IntakeKey) => ({
    value: values[key],
    onChange: (v: string) => setField(key, v),
    invalid: invalidFields.has(key),
    inputRef: (el: HTMLInputElement | null) => {
      fieldRefs.current[key] = el;
    },
  });

  return (
    <div className="space-y-3" onKeyDown={handleKeyDown}>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <>
          <section aria-label="Subjective / patient history" className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Subjective / patient history</h3>
            <IntakeSubjectiveFields values={values} onChange={setField} />
          </section>
          <section aria-label="Vitals" className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Vitals</h3>
            <div className="grid grid-cols-2 gap-3">
              <IntakeVitalInput label="Blood pressure *" placeholder="120/80" type="text" {...vital("bloodPressure")} />
              <IntakeVitalInput label="Pulse rate (bpm) *" {...vital("pulseRate")} />
              <IntakeVitalInput label="Respiratory rate *" {...vital("respiratoryRate")} />
              <IntakeVitalInput label="Temperature (°C) *" step="0.1" {...vital("temperature")} />
              <IntakeVitalInput label="Height (cm) *" step="0.1" {...vital("heightCm")} />
              <IntakeVitalInput label="Weight (kg) *" step="0.1" {...vital("weightKg")} />
              <IntakeVitalInput label="SpO2 (%) *" step="0.1" {...vital("oxygenSaturation")} />
              <div>
                <label className="text-xs font-medium text-muted-foreground">BMI (auto-computed)</label>
                <Input value={bmiPreview != null ? String(bmiPreview) : ""} readOnly disabled placeholder="—" />
              </div>
              <IntakeVitalInput label="Pain score (0-10, optional)" min={0} max={10} {...vital("painScore")} />
              <IntakeVitalInput label="Head circumference (cm, optional)" step="0.1" {...vital("headCircumferenceCm")} />
            </div>
          </section>
          {missingRequired.length > 0 ? (
            <p className="text-xs text-muted-foreground">Still needed: {missingRequired.join(", ")}</p>
          ) : (
            <p className="text-xs text-green-600">All required vitals entered.</p>
          )}
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
        </>
      )}
      <div className="flex justify-between pt-2">
        <Button type="button" variant="outline" onClick={onBack} disabled={saving}>
          Close
        </Button>
        <Button type="button" onClick={handleSaveAndClose} disabled={loading || saving || !consultationId}>
          {saving ? "Saving..." : "Save and Close"}
        </Button>
      </div>
    </div>
  );
}
