"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { consultationKeys } from "@/features/consultation/hooks/use-consultation";
import type { SoapNoteInput } from "@/features/consultation/types";

const AUTOSAVE_INTERVAL_MS = 30_000;

export type AutosaveStatus = "idle" | "saving" | "saved" | "unsaved" | "error";

type SoapValues = Partial<SoapNoteInput>;

/** `undefined`, `null` and "" all mean "empty" - a field that was empty and is empty again is unchanged. */
const normalize = (v: unknown) => (v === undefined || v === "" ? null : v);

/**
 * Task #6: the fields the Doctor actually changed relative to `baseline` (the values loaded
 * from - or last saved to - the server). Only these are ever sent, so an autosave can never
 * overwrite a field somebody else (Reception/Nurse pre-entry) saved in the meantime. A field
 * that was edited and then put back to its baseline value is NOT reported. A value cleared to
 * "" from a non-empty baseline IS reported (and sent as-is, so it clears the field).
 */
export function changedSoapFields(baseline: SoapValues, current: SoapValues): SoapValues {
  const changed: Record<string, unknown> = {};
  for (const key of Object.keys(current) as (keyof SoapNoteInput)[]) {
    if (normalize(baseline[key]) !== normalize(current[key])) changed[key] = current[key];
  }
  return changed as SoapValues;
}

/**
 * Real dirty-tracking autosave: only calls the API when a field differs from the baseline
 * (avoids firing an empty PUT every 30s when the doctor is reading, not typing), and - since
 * Task #6 - sends ONLY the changed fields, never a full snapshot. Also warns on
 * `beforeunload` only while genuinely dirty, not unconditionally.
 */
export function useSoapAutosave(consultationId: string | null, canEdit: boolean) {
  const queryClient = useQueryClient();
  const [values, setValuesState] = useState<SoapValues>({});
  const [status, setStatus] = useState<AutosaveStatus>("idle");
  // Values as loaded from the server / as last successfully saved - the diff base.
  const baselineRef = useRef<SoapValues>({});
  const valuesRef = useRef<SoapValues>({});
  const consultationIdRef = useRef<string | null>(consultationId);
  consultationIdRef.current = consultationId;

  const hasChanges = () => Object.keys(changedSoapFields(baselineRef.current, valuesRef.current)).length > 0;

  const mutation = useMutation({
    mutationFn: ({ payload }: { payload: SoapValues; forConsultation: string | null }) => {
      if (!consultationId) throw new Error("No consultation open");
      return consultationApi.saveSoap(consultationId, payload);
    },
    onMutate: () => setStatus("saving"),
    onSuccess: (consultation, { payload, forConsultation }) => {
      // A save that finishes after the doctor switched consultations must not touch the new baseline.
      if (forConsultation === consultationIdRef.current) {
        baselineRef.current = { ...baselineRef.current, ...payload };
        setStatus(hasChanges() ? "unsaved" : "saved");
      }
      if (consultationId) {
        queryClient.setQueryData(consultationKeys.detail(consultationId), consultation);
        // The consultation page reads from `consultationKeys.forVisit(visitId)`
        // (via useOpenConsultation), not `detail` — without this, autosaved
        // SOAP content wouldn't reflect back into the page's own data source.
        queryClient.setQueryData(consultationKeys.forVisit(consultation.visitId), consultation);
      }
    },
    onError: () => setStatus("error"),
  });

  const setValues = useCallback((next: SoapValues) => {
    valuesRef.current = next;
    setValuesState(next);
    setStatus(Object.keys(changedSoapFields(baselineRef.current, next)).length > 0 ? "unsaved" : "saved");
  }, []);

  /** (Re)load from the server: also resets the baseline, e.g. when the consultation changes. */
  const initialize = useCallback((initial: SoapValues) => {
    valuesRef.current = initial;
    baselineRef.current = { ...initial };
    setValuesState(initial);
    setStatus("idle");
  }, []);

  const isDirty = hasChanges();

  const saveNow = useCallback(() => {
    if (!canEdit || !consultationId) return;
    const payload = changedSoapFields(baselineRef.current, valuesRef.current);
    if (Object.keys(payload).length === 0) return;
    mutation.mutate({ payload, forConsultation: consultationId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canEdit, consultationId]);

  // 30-second autosave interval - only fires the request when dirty.
  useEffect(() => {
    if (!canEdit || !consultationId) return;
    const interval = setInterval(saveNow, AUTOSAVE_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [canEdit, consultationId, saveNow]);

  // Warn on tab close/navigate away only while there are real unsaved edits.
  useEffect(() => {
    if (!canEdit) return;
    const handler = (event: BeforeUnloadEvent) => {
      if (hasChanges()) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [canEdit]);

  return { values, setValues, initialize, status, isDirty, saveNow };
}
