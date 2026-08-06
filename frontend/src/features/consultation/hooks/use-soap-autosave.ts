"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { consultationKeys } from "@/features/consultation/hooks/use-consultation";
import type { SoapNoteInput } from "@/features/consultation/types";

const AUTOSAVE_INTERVAL_MS = 30_000;

export type AutosaveStatus = "idle" | "saving" | "saved" | "unsaved" | "error";

/**
 * Real dirty-tracking autosave: only calls the API when the current form
 * values differ from the last-saved snapshot (avoids firing an empty PUT
 * every 30s when the doctor is reading, not typing). Also warns on
 * `beforeunload` only while genuinely dirty, not unconditionally.
 */
export function useSoapAutosave(consultationId: string | null, canEdit: boolean) {
  const queryClient = useQueryClient();
  const [values, setValuesState] = useState<Partial<SoapNoteInput>>({});
  const [status, setStatus] = useState<AutosaveStatus>("idle");
  const lastSavedRef = useRef<string>("{}");
  const valuesRef = useRef<Partial<SoapNoteInput>>({});

  const mutation = useMutation({
    mutationFn: (payload: Partial<SoapNoteInput>) => {
      if (!consultationId) throw new Error("No consultation open");
      return consultationApi.saveSoap(consultationId, payload);
    },
    onMutate: () => setStatus("saving"),
    onSuccess: (consultation) => {
      lastSavedRef.current = JSON.stringify(valuesRef.current);
      setStatus("saved");
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

  const setValues = useCallback((next: Partial<SoapNoteInput>) => {
    valuesRef.current = next;
    setValuesState(next);
    setStatus(JSON.stringify(next) === lastSavedRef.current ? "saved" : "unsaved");
  }, []);

  const initialize = useCallback((initial: Partial<SoapNoteInput>) => {
    valuesRef.current = initial;
    lastSavedRef.current = JSON.stringify(initial);
    setValuesState(initial);
    setStatus("idle");
  }, []);

  const isDirty = JSON.stringify(valuesRef.current) !== lastSavedRef.current;

  const saveNow = useCallback(() => {
    if (!canEdit || !consultationId) return;
    if (JSON.stringify(valuesRef.current) === lastSavedRef.current) return;
    mutation.mutate(valuesRef.current);
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
      if (JSON.stringify(valuesRef.current) !== lastSavedRef.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [canEdit]);

  return { values, setValues, initialize, status, isDirty, saveNow };
}
