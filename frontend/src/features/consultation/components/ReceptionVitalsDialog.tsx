"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { ApiError } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

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

  const [chiefComplaint, setChiefComplaint] = useState("");
  const [bloodPressure, setBloodPressure] = useState("");
  const [pulseRate, setPulseRate] = useState("");
  const [respiratoryRate, setRespiratoryRate] = useState("");
  const [temperature, setTemperature] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [oxygenSaturation, setOxygenSaturation] = useState("");

  const fieldRefs = useRef<Record<string, HTMLInputElement | null>>({});

  useEffect(() => {
    if (!open) {
      setConsultationId(null);
      setError(null);
      setInvalidFields(new Set());
      return;
    }
    setLoading(true);
    consultationApi
      .openForReception(visitId)
      .then(async (consultation) => {
        setConsultationId(consultation.id);
        const note = await consultationApi.getSubjectiveObjective(consultation.id);
        if (note) {
          setChiefComplaint(note.chiefComplaint ?? "");
          setBloodPressure(note.bloodPressure ?? "");
          setPulseRate(note.pulseRate != null ? String(note.pulseRate) : "");
          setRespiratoryRate(note.respiratoryRate != null ? String(note.respiratoryRate) : "");
          setTemperature(note.temperature != null ? String(note.temperature) : "");
          setHeightCm(note.heightCm != null ? String(note.heightCm) : "");
          setWeightKg(note.weightKg != null ? String(note.weightKg) : "");
          setOxygenSaturation(note.oxygenSaturation != null ? String(note.oxygenSaturation) : "");
        }
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

  const REQUIRED_FIELDS: Array<[string, string]> = [
    ["bloodPressure", bloodPressure],
    ["temperature", temperature],
    ["pulseRate", pulseRate],
    ["respiratoryRate", respiratoryRate],
    ["oxygenSaturation", oxygenSaturation],
    ["heightCm", heightCm],
    ["weightKg", weightKg],
  ];

  const handleSaveAndClose = async () => {
    if (!consultationId) return;
    const missing = REQUIRED_FIELDS.filter(([, v]) => !v).map(([key]) => key);
    if (missing.length > 0) {
      setInvalidFields(new Set(missing));
      setError("Please fill in all required vitals before saving.");
      fieldRefs.current[missing[0]]?.focus();
      return;
    }
    setInvalidFields(new Set());
    setSaving(true);
    setError(null);
    try {
      await consultationApi.saveSubjectiveObjective(consultationId, {
        chiefComplaint: chiefComplaint || null,
        bloodPressure: bloodPressure || null,
        pulseRate: pulseRate ? Number(pulseRate) : null,
        respiratoryRate: respiratoryRate ? Number(respiratoryRate) : null,
        temperature: temperature ? Number(temperature) : null,
        heightCm: heightCm ? Number(heightCm) : null,
        weightKg: weightKg ? Number(weightKg) : null,
        oxygenSaturation: oxygenSaturation ? Number(oxygenSaturation) : null,
      });
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" onClose={() => onOpenChange(false)}>
        <div onKeyDown={handleKeyDown}>
          <DialogHeader>
            <DialogTitle>Enter Vitals / Chief Complaint{patientName ? ` — ${patientName}` : ""}</DialogTitle>
          </DialogHeader>

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Chief complaint</label>
                <Textarea rows={2} value={chiefComplaint} onChange={(e) => setChiefComplaint(e.target.value)} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Blood pressure *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.bloodPressure = el; }}
                    value={bloodPressure}
                    onChange={(e) => setBloodPressure(e.target.value)}
                    placeholder="120/80"
                    className={cn(invalidFields.has("bloodPressure") && "border-destructive")}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Pulse rate (bpm) *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.pulseRate = el; }}
                    type="number"
                    value={pulseRate}
                    onChange={(e) => setPulseRate(e.target.value)}
                    className={cn(invalidFields.has("pulseRate") && "border-destructive")}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Respiratory rate *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.respiratoryRate = el; }}
                    type="number"
                    value={respiratoryRate}
                    onChange={(e) => setRespiratoryRate(e.target.value)}
                    className={cn(invalidFields.has("respiratoryRate") && "border-destructive")}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Temperature (°C) *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.temperature = el; }}
                    type="number"
                    step="0.1"
                    value={temperature}
                    onChange={(e) => setTemperature(e.target.value)}
                    className={cn(invalidFields.has("temperature") && "border-destructive")}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Height (cm) *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.heightCm = el; }}
                    type="number"
                    step="0.1"
                    value={heightCm}
                    onChange={(e) => setHeightCm(e.target.value)}
                    className={cn(invalidFields.has("heightCm") && "border-destructive")}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Weight (kg) *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.weightKg = el; }}
                    type="number"
                    step="0.1"
                    value={weightKg}
                    onChange={(e) => setWeightKg(e.target.value)}
                    className={cn(invalidFields.has("weightKg") && "border-destructive")}
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">O2 saturation (%) *</label>
                  <Input
                    ref={(el) => { fieldRefs.current.oxygenSaturation = el; }}
                    type="number"
                    step="0.1"
                    value={oxygenSaturation}
                    onChange={(e) => setOxygenSaturation(e.target.value)}
                    className={cn(invalidFields.has("oxygenSaturation") && "border-destructive")}
                  />
                </div>
              </div>
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
