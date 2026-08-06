"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { ApiError } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

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
 * live BMI/Pain Score/Head Circumference fields that dialog doesn't have.
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

  const [chiefComplaint, setChiefComplaint] = useState("");
  const [bloodPressure, setBloodPressure] = useState("");
  const [pulseRate, setPulseRate] = useState("");
  const [respiratoryRate, setRespiratoryRate] = useState("");
  const [temperature, setTemperature] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [oxygenSaturation, setOxygenSaturation] = useState("");
  const [painScore, setPainScore] = useState("");
  const [headCircumferenceCm, setHeadCircumferenceCm] = useState("");

  useEffect(() => {
    setLoading(true);
    setError(null);
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
          setPainScore(note.painScore != null ? String(note.painScore) : "");
          setHeadCircumferenceCm(note.headCircumferenceCm != null ? String(note.headCircumferenceCm) : "");
        }
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
    const h = Number(heightCm);
    const w = Number(weightKg);
    if (!h || !w || h <= 0) return null;
    const meters = h / 100;
    return Math.round((w / (meters * meters)) * 100) / 100;
  }, [heightCm, weightKg]);

  const REQUIRED_FIELDS: Array<[string, string, string]> = [
    ["bloodPressure", "Blood Pressure", bloodPressure],
    ["temperature", "Temperature", temperature],
    ["pulseRate", "Pulse Rate", pulseRate],
    ["respiratoryRate", "Respiratory Rate", respiratoryRate],
    ["oxygenSaturation", "SpO2", oxygenSaturation],
    ["heightCm", "Height", heightCm],
    ["weightKg", "Weight", weightKg],
  ];
  const missingRequired = REQUIRED_FIELDS.filter(([, , v]) => !v).map(([, label]) => label);

  const handleSaveAndClose = async () => {
    if (!consultationId) return;
    const missingKeys = REQUIRED_FIELDS.filter(([, , v]) => !v).map(([key]) => key);
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
      await consultationApi.saveSubjectiveObjective(consultationId, {
        chiefComplaint: chiefComplaint || null,
        bloodPressure: bloodPressure || null,
        pulseRate: pulseRate ? Number(pulseRate) : null,
        respiratoryRate: respiratoryRate ? Number(respiratoryRate) : null,
        temperature: temperature ? Number(temperature) : null,
        heightCm: heightCm ? Number(heightCm) : null,
        weightKg: weightKg ? Number(weightKg) : null,
        oxygenSaturation: oxygenSaturation ? Number(oxygenSaturation) : null,
        painScore: painScore ? Number(painScore) : null,
        headCircumferenceCm: headCircumferenceCm ? Number(headCircumferenceCm) : null,
      });
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

  return (
    <div className="space-y-3" onKeyDown={handleKeyDown}>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <>
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
              <label className="text-xs font-medium text-muted-foreground">SpO2 (%) *</label>
              <Input
                ref={(el) => { fieldRefs.current.oxygenSaturation = el; }}
                type="number"
                step="0.1"
                value={oxygenSaturation}
                onChange={(e) => setOxygenSaturation(e.target.value)}
                className={cn(invalidFields.has("oxygenSaturation") && "border-destructive")}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">BMI (auto-computed)</label>
              <Input value={bmiPreview != null ? String(bmiPreview) : ""} readOnly disabled placeholder="—" />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Pain score (0-10, optional)</label>
              <Input type="number" min={0} max={10} value={painScore} onChange={(e) => setPainScore(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Head circumference (cm, optional)</label>
              <Input type="number" step="0.1" value={headCircumferenceCm} onChange={(e) => setHeadCircumferenceCm(e.target.value)} />
            </div>
          </div>
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
