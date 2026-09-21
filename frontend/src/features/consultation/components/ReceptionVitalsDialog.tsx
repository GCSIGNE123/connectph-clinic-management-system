"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import {
  EMPTY_INTAKE,
  IntakeSubjectiveFields,
  IntakeVitalInput,
  changedIntakePayload,
  hasAnyIntakeValue,
  intakeFromNote,
  type IntakeKey,
  type IntakeValues,
} from "@/features/consultation/components/intake-fields";
import { ApiError } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";

/**
 * Phase 20 (items 3-5): lets a Receptionist (performing Nurse-type duties)
 * enter ONLY the Subjective/Objective/vitals portion of a visit's SOAP note
 * directly from the Queue screen - a deliberate, narrow reversal of the
 * Phase 8 "Reception cannot view/edit SOAP notes" rule, scoped by the
 * backend to these fields only (see `require_soap_subjective_objective_role`
 * in `core/dependencies.py` and the `/soap/subjective-objective` endpoints
 * in `api/v1/consultations.py`). Assessment/Plan and completing/signing the
 * consultation remain reachable only from the Doctor Workspace consultation
 * page (Doctor/Owner/Administrator only).
 *
 * Task #6: the form now covers the full approved pre-entry scope - the seven
 * Subjective fields (Chief complaint reuses the Task #2 suggestions) plus all
 * vitals incl. pain score and head circumference - via the fields shared with
 * `PreQueueVitalsStep`. Physical examination / clinical findings and all
 * Assessment/Plan fields are Doctor-only and not offered. A save sends ONLY
 * the fields this user changed since the form loaded, so it cannot overwrite
 * something the Doctor entered in the meantime.
 *
 * Phase 22: "Save" replaced with "Save and Close" - see
 * `PreQueueVitalsStep` for the sibling pre-queue flow, which mirrors this
 * same required-field/toast/keyboard behavior.
 *
 * "Save and Print": on success, `onSaved` fires before the dialog closes -
 * the caller (`queue/page.tsx`) uses this to open the queue slip print
 * flow immediately, so one button does all three (save vitals, print the
 * ticket, close this dialog).
 */
export function ReceptionVitalsDialog({
  open,
  onOpenChange,
  visitId,
  patientName,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  visitId: string;
  patientName?: string | null;
  /** Called right after a successful save, before the dialog closes -
   * lets the caller trigger the queue slip print flow ("Save and Print"). */
  onSaved?: () => void;
}) {
  const { toast } = useToast();
  const [consultationId, setConsultationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalidFields, setInvalidFields] = useState<Set<string>>(new Set());

  const [values, setValues] = useState<IntakeValues>(EMPTY_INTAKE);
  // What the server had when the form loaded - the diff base for the save payload.
  const baselineRef = useRef<IntakeValues>(EMPTY_INTAKE);
  const setField = (key: IntakeKey, value: string) => setValues((v) => ({ ...v, [key]: value }));

  const fieldRefs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    if (!open) {
      setConsultationId(null);
      setError(null);
      setInvalidFields(new Set());
      setValues(EMPTY_INTAKE);
      baselineRef.current = EMPTY_INTAKE;
      return;
    }
    setLoading(true);
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
        // BUG-024: this used to swallow the real backend error (e.g. "Visit
        // has no assigned doctor.") behind one generic, misleading message
        // that fired for every failure alike. Surface the actual detail
        // when we have one so Reception knows exactly why the consultation
        // couldn't be opened (unassigned doctor being the common real
        // case, since `New Queue Ticket` allows "Any / unassigned").
        const detail = err instanceof ApiError ? err.message : null;
        setError(detail || "Could not open this visit's consultation.");
      })
      .finally(() => setLoading(false));
  }, [open, visitId]);

  const handleSaveAndClose = async () => {
    if (!consultationId) return;
    // Every field is optional - a receptionist/nurse may legitimately only have
    // one reading or note at hand (e.g. just a temperature). Only reject the save
    // if EVERY field is empty, since an empty note is not a meaningful save.
    if (!hasAnyIntakeValue(values)) {
      setError("Enter at least one vital sign or chief complaint before saving.");
      return;
    }
    setInvalidFields(new Set());
    setSaving(true);
    setError(null);
    try {
      await consultationApi.saveSubjectiveObjective(consultationId, changedIntakePayload(baselineRef.current, values));
      toast({ title: "Vitals saved successfully.", variant: "success", durationMs: 3000 });
      onSaved?.();
      onOpenChange(false);
    } catch {
      setError("Could not save. The consultation may already be signed.");
    } finally {
      setSaving(false);
    }
  };

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      onOpenChange(false);
      return;
    }
    if (e.key === "Enter") {
      const target = e.target as HTMLElement;
      // Don't let Enter inside a multi-line textarea (Notes/Chief complaint)
      // submit - it's expected to insert a newline there.
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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" onClose={() => onOpenChange(false)}>
        <div onKeyDown={handleKeyDown}>
          <DialogHeader>
            <DialogTitle>Enter Vitals / Chief Complaint{patientName ? ` — ${patientName}` : ""}</DialogTitle>
          </DialogHeader>

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-4">
              <section aria-label="Subjective / patient history" className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">Subjective / patient history</h3>
                <IntakeSubjectiveFields values={values} onChange={setField} />
              </section>
              <section aria-label="Vitals" className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">Vitals</h3>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <IntakeVitalInput label="Blood pressure" placeholder="120/80" type="text" {...vital("bloodPressure")} />
                  <IntakeVitalInput label="Pulse rate (bpm)" {...vital("pulseRate")} />
                  <IntakeVitalInput label="Respiratory rate" {...vital("respiratoryRate")} />
                  <IntakeVitalInput label="Temperature (°C)" step="0.1" {...vital("temperature")} />
                  <IntakeVitalInput label="Height (cm)" step="0.1" {...vital("heightCm")} />
                  <IntakeVitalInput label="Weight (kg)" step="0.1" {...vital("weightKg")} />
                  <IntakeVitalInput label="O2 saturation (%)" step="0.1" {...vital("oxygenSaturation")} />
                  <IntakeVitalInput label="Pain score (0-10)" min={0} max={10} {...vital("painScore")} />
                  <IntakeVitalInput label="Head circumference (cm)" step="0.1" {...vital("headCircumferenceCm")} />
                </div>
              </section>
              {error ? <p className="text-xs text-destructive">{error}</p> : null}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            <Button type="button" onClick={handleSaveAndClose} disabled={loading || saving || !consultationId}>
              {saving ? "Saving…" : "Save and Print"}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
