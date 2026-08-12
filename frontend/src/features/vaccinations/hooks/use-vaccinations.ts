"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { vaccinationsApi } from "@/features/vaccinations/api/vaccinations-api";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { VaccinationAdministerInput } from "@/features/vaccinations/types";

export const vaccinationKeys = {
  list: (status?: string) => ["vaccinations", "list", status ?? "all"] as const,
  forPatient: (patientId: string) => ["vaccinations", "patient", patientId] as const,
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export function useVaccinationsWorklist(status?: string) {
  return useQuery({
    queryKey: vaccinationKeys.list(status),
    queryFn: () => vaccinationsApi.list({ status }),
    refetchInterval: 30_000,
  });
}

export function useVaccinationsForPatient(patientId: string | null | undefined) {
  return useQuery({
    queryKey: patientId ? vaccinationKeys.forPatient(patientId) : ["vaccinations", "patient", "none"],
    queryFn: () => vaccinationsApi.list({ patientId: patientId as string }),
    enabled: Boolean(patientId),
  });
}

export function useAdministerVaccination() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: VaccinationAdministerInput }) =>
      vaccinationsApi.administer(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vaccinations"] });
      toast({ title: "Vaccination administered", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not record administration", description: errorMessage(error), variant: "error" }),
  });
}

export function useCancelVaccination() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => vaccinationsApi.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["vaccinations"] });
      toast({ title: "Vaccination order cancelled", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not cancel order", description: errorMessage(error), variant: "error" }),
  });
}
