"use client";

import type { Ref } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { SoapSuggestionInput } from "@/features/consultation/components/SoapSuggestionInput";
import type { SoapNoteInput } from "@/features/consultation/types";
import { cn } from "@/lib/utils";

/**
 * Task #6: the Receptionist/Nurse SOAP pre-entry fields, shared by `ReceptionVitalsDialog` (after
 * queueing) and `PreQueueVitalsStep` (before queueing) so both offer exactly the same approved scope:
 * the seven Subjective fields plus the vitals. Physical examination, clinical findings and every
 * Assessment/Plan field are Doctor-only and deliberately absent (the backend rejects them with a 422).
 */

export const SUBJECTIVE_INTAKE_FIELDS = [
  { key: "chiefComplaint", label: "Chief complaint", rows: 2, suggest: true },
  { key: "historyOfPresentIllness", label: "History of present illness", rows: 2 },
  { key: "pastMedicalHistory", label: "Past medical history", rows: 2 },
  { key: "familyHistory", label: "Family history", rows: 2 },
  { key: "socialHistory", label: "Social history", rows: 2 },
  { key: "reviewOfSystems", label: "Review of systems", rows: 2 },
  { key: "subjectiveNotes", label: "Subjective notes", rows: 2 },
] as const;

export const VITAL_INTAKE_KEYS = [
  "bloodPressure", "pulseRate", "respiratoryRate", "temperature", "heightCm", "weightKg", "oxygenSaturation",
  "painScore", "headCircumferenceCm",
] as const;

export type SubjectiveIntakeKey = (typeof SUBJECTIVE_INTAKE_FIELDS)[number]["key"];
export type VitalIntakeKey = (typeof VITAL_INTAKE_KEYS)[number];
export type IntakeKey = SubjectiveIntakeKey | VitalIntakeKey;
export type IntakeValues = Record<IntakeKey, string>;

const NUMERIC_KEYS = new Set<IntakeKey>([
  "pulseRate", "respiratoryRate", "temperature", "heightCm", "weightKg", "oxygenSaturation", "painScore", "headCircumferenceCm",
]);

export const ALL_INTAKE_KEYS: IntakeKey[] = [...SUBJECTIVE_INTAKE_FIELDS.map((f) => f.key), ...VITAL_INTAKE_KEYS];

export const EMPTY_INTAKE: IntakeValues = Object.fromEntries(ALL_INTAKE_KEYS.map((k) => [k, ""])) as IntakeValues;

/** Form strings from a stored note (null / missing -> ""). */
export function intakeFromNote(note: Partial<SoapNoteInput> | null | undefined): IntakeValues {
  const out = { ...EMPTY_INTAKE };
  if (!note) return out;
  for (const key of ALL_INTAKE_KEYS) {
    const v = note[key];
    out[key] = v === null || v === undefined ? "" : String(v);
  }
  return out;
}

/**
 * Only the fields whose value differs from what was loaded (`baseline`) - so a save can never
 * overwrite something the Doctor (or anyone else) changed on a field this user did not touch.
 * A field emptied by the user is sent as `null` (clear it); numeric fields are sent as numbers.
 */
export function changedIntakePayload(baseline: IntakeValues, current: IntakeValues): Partial<SoapNoteInput> {
  const payload: Record<string, unknown> = {};
  for (const key of ALL_INTAKE_KEYS) {
    if (current[key] === baseline[key]) continue;
    const text = current[key].trim();
    payload[key] = text === "" ? null : NUMERIC_KEYS.has(key) ? Number(text) : current[key];
  }
  return payload as Partial<SoapNoteInput>;
}

export function hasAnyIntakeValue(values: IntakeValues): boolean {
  return ALL_INTAKE_KEYS.some((k) => values[k].trim() !== "");
}

/** The Subjective / patient-history block. Chief complaint reuses the Task #2 suggestion control. */
export function IntakeSubjectiveFields({
  values,
  onChange,
}: {
  values: IntakeValues;
  onChange: (key: SubjectiveIntakeKey, value: string) => void;
}) {
  return (
    <div className="space-y-3">
      {SUBJECTIVE_INTAKE_FIELDS.map((field) => (
        <div key={field.key}>
          <label className="text-xs font-medium text-muted-foreground">{field.label}</label>
          {"suggest" in field && field.suggest ? (
            <SoapSuggestionInput
              field="chief_complaint"
              value={values[field.key]}
              onChange={(v) => onChange(field.key, v)}
              rows={field.rows}
              aria-label={field.label}
            />
          ) : (
            <Textarea
              rows={field.rows}
              value={values[field.key]}
              onChange={(e) => onChange(field.key, e.target.value)}
              aria-label={field.label}
              className="mt-1"
            />
          )}
        </div>
      ))}
    </div>
  );
}

/** One labelled vitals input (keeps the existing label text and invalid-outline behaviour). */
export function IntakeVitalInput({
  label,
  value,
  onChange,
  invalid,
  inputRef,
  type = "number",
  step,
  placeholder,
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  type?: string;
  step?: string;
  placeholder?: string;
  min?: number;
  max?: number;
}) {
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <Input
        ref={inputRef}
        type={type}
        step={step}
        min={min}
        max={max}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={cn(invalid && "border-destructive")}
      />
    </div>
  );
}
