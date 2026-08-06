"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

export const consultationKeys = {
  all: ["consultation"] as const,
  forVisit: (visitId: string) => ["consultation", "visit", visitId] as const,
  detail: (id: string) => ["consultation", "detail", id] as const,
};

export function useOpenConsultation(visitId: string) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: consultationKeys.forVisit(visitId),
    queryFn: () => consultationApi.openForVisit(visitId),
    enabled: Boolean(visitId),
    staleTime: 0,
    refetchOnWindowFocus: false,
    meta: { onSettled: () => queryClient.invalidateQueries({ queryKey: consultationKeys.all }) },
  });
}

export function useConsultationDetail(consultationId: string | null | undefined) {
  return useQuery({
    queryKey: consultationId ? consultationKeys.detail(consultationId) : ["consultation", "detail", "none"],
    queryFn: () => consultationApi.getById(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

export function useCompleteConsultation(consultationId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (consultationFee?: number | null) => consultationApi.completeConsultation(consultationId, consultationFee),
    onSuccess: (consultation) => {
      toast({ title: "Consultation completed", variant: "success" });
      // See use-diagnoses.ts / use-soap-autosave.ts: the page reads from
      // `forVisit`, not `detail` — both must be kept in sync.
      queryClient.setQueryData(consultationKeys.detail(consultationId), consultation);
      queryClient.setQueryData(consultationKeys.forVisit(consultation.visitId), consultation);
    },
    onError: (error) => {
      toast({
        title: "Could not complete consultation",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}

export function useSignConsultation(consultationId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => consultationApi.signConsultation(consultationId),
    onSuccess: (consultation) => {
      toast({ title: "Consultation signed", variant: "success" });
      queryClient.setQueryData(consultationKeys.detail(consultationId), consultation);
      queryClient.setQueryData(consultationKeys.forVisit(consultation.visitId), consultation);
    },
    onError: (error) => {
      toast({
        title: "Could not sign consultation",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}
