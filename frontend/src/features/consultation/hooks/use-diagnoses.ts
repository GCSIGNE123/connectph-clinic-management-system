"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { consultationKeys } from "@/features/consultation/hooks/use-consultation";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { DiagnosisStatus, DiagnosisType } from "@/features/consultation/types";

export function useAddDiagnosis(consultationId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      diagnosisType: DiagnosisType;
      status: DiagnosisStatus;
      notes?: string | null;
      icd10Code?: string | null;
      icd10Description?: string | null;
    }) => consultationApi.addDiagnosis(consultationId, payload),
    onSuccess: (consultation) => {
      toast({ title: "Diagnosis added", variant: "success" });
      // The consultation page reads from `consultationKeys.forVisit(visitId)`
      // (via useOpenConsultation), a different cache entry than
      // `consultationKeys.detail(id)` — updating only the latter left the
      // visible page stale even though the diagnosis was saved server-side.
      queryClient.setQueryData(consultationKeys.detail(consultationId), consultation);
      queryClient.setQueryData(consultationKeys.forVisit(consultation.visitId), consultation);
    },
    onError: (error) => {
      toast({
        title: "Could not add diagnosis",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}
