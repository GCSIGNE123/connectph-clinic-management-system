"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { medicalCertificateApi } from "@/features/clinical-orders/api/medical-certificate-api";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { MedicalCertificateDraftInput } from "@/features/clinical-orders/types";

/** Same per-(consultation)/per-(visit)/per-(patient) query-key convention as
 * `clinicalOrdersKeys` - every mutation invalidates all three so the
 * Consultation tab, the read-only Visit view, and the Patient history all
 * stay in sync (see that file's docstring for the Phase 8 lesson this
 * avoids repeating). */
export const medicalCertificateKeys = {
  forConsultation: (consultationId: string) => ["medical-certificates", "consultation", consultationId] as const,
  forVisit: (visitId: string) => ["medical-certificates", "visit", visitId] as const,
  forPatient: (patientId: string) => ["medical-certificates", "patient", patientId] as const,
  detail: (certificateId: string) => ["medical-certificates", "detail", certificateId] as const,
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export function useMedicalCertificatesForConsultation(consultationId: string | null | undefined) {
  return useQuery({
    queryKey: consultationId ? medicalCertificateKeys.forConsultation(consultationId) : ["medical-certificates", "none"],
    queryFn: () => medicalCertificateApi.listForConsultation(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

export function useMedicalCertificatesForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? medicalCertificateKeys.forVisit(visitId) : ["medical-certificates", "none"],
    queryFn: () => medicalCertificateApi.listForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

export function useMedicalCertificatesForPatient(patientId: string | null | undefined) {
  return useQuery({
    queryKey: patientId ? medicalCertificateKeys.forPatient(patientId) : ["medical-certificates", "none"],
    queryFn: () => medicalCertificateApi.listForPatient(patientId as string),
    enabled: Boolean(patientId),
  });
}

function useInvalidateAll(consultationId: string, visitId: string, patientId?: string | null) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: medicalCertificateKeys.forConsultation(consultationId) });
    queryClient.invalidateQueries({ queryKey: medicalCertificateKeys.forVisit(visitId) });
    if (patientId) queryClient.invalidateQueries({ queryKey: medicalCertificateKeys.forPatient(patientId) });
    // The Timeline tab reads visit.timeline from a different cache entry
    // (visitKeys.detail) - without this, Issue/Cancel timeline events don't
    // show up until a full reload (same Phase 8 lesson as clinical-orders).
    queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
  };
}

export function useCreateMedicalCertificateDraft(consultationId: string, visitId: string, patientId?: string | null) {
  const { toast } = useToast();
  const invalidate = useInvalidateAll(consultationId, visitId, patientId);
  return useMutation({
    mutationFn: (input: MedicalCertificateDraftInput) => medicalCertificateApi.createDraft(consultationId, input),
    onSuccess: () => {
      toast({ title: "Draft certificate saved", variant: "success" });
      invalidate();
    },
    onError: (error) => toast({ title: "Could not save draft", description: errorMessage(error), variant: "error" }),
  });
}

export function useUpdateMedicalCertificateDraft(consultationId: string, visitId: string, patientId?: string | null) {
  const { toast } = useToast();
  const invalidate = useInvalidateAll(consultationId, visitId, patientId);
  return useMutation({
    mutationFn: ({ certificateId, input }: { certificateId: string; input: Partial<MedicalCertificateDraftInput> }) =>
      medicalCertificateApi.updateDraft(certificateId, input),
    onSuccess: () => {
      toast({ title: "Draft updated", variant: "success" });
      invalidate();
    },
    onError: (error) => toast({ title: "Could not update draft", description: errorMessage(error), variant: "error" }),
  });
}

export function useIssueMedicalCertificate(consultationId: string, visitId: string, patientId?: string | null) {
  const { toast } = useToast();
  const invalidate = useInvalidateAll(consultationId, visitId, patientId);
  return useMutation({
    mutationFn: (certificateId: string) => medicalCertificateApi.issue(certificateId),
    onSuccess: (certificate) => {
      toast({ title: `Certificate ${certificate.certificateNumber} issued`, variant: "success" });
      invalidate();
    },
    onError: (error) => toast({ title: "Could not issue certificate", description: errorMessage(error), variant: "error" }),
  });
}

export function useCancelMedicalCertificate(consultationId: string, visitId: string, patientId?: string | null) {
  const { toast } = useToast();
  const invalidate = useInvalidateAll(consultationId, visitId, patientId);
  return useMutation({
    mutationFn: ({ certificateId, reason }: { certificateId: string; reason: string }) =>
      medicalCertificateApi.cancel(certificateId, reason),
    onSuccess: () => {
      toast({ title: "Certificate cancelled", variant: "success" });
      invalidate();
    },
    onError: (error) => toast({ title: "Could not cancel certificate", description: errorMessage(error), variant: "error" }),
  });
}

export function useReissueMedicalCertificate(consultationId: string, visitId: string, patientId?: string | null) {
  const { toast } = useToast();
  const invalidate = useInvalidateAll(consultationId, visitId, patientId);
  return useMutation({
    mutationFn: ({ certificateId, reason }: { certificateId: string; reason: string }) =>
      medicalCertificateApi.reissue(certificateId, reason),
    onSuccess: (certificate) => {
      toast({ title: `Certificate reissued as ${certificate.certificateNumber}`, variant: "success" });
      invalidate();
    },
    onError: (error) => toast({ title: "Could not reissue certificate", description: errorMessage(error), variant: "error" }),
  });
}

/** Best-effort audit trail of the print action - never blocks the actual
 * `window.print()` call (see `PrintableDocumentDialog`) if this fails. */
export function useRecordMedicalCertificatePrint() {
  return useMutation({
    mutationFn: (certificateId: string) => medicalCertificateApi.recordPrint(certificateId),
  });
}
