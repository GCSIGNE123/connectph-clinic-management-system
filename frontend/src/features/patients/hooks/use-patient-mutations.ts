"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { patientsApi } from "@/features/patients/api/patients-api";
import { patientsKeys } from "@/features/patients/hooks/use-patients";
import type { CreatePatientInput, EditPatientInput } from "@/features/patients/schemas/patients-schemas";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/**
 * Create a patient. Resolves with `{ patient: null, duplicates: [...] }`
 * when the backend detects likely duplicates and `override` was not passed -
 * callers should show a confirmation dialog and re-call with
 * `{ override: true }` (gated to Administrator/Owner roles) if the user
 * confirms.
 */
export function useCreatePatient() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ input, override }: { input: CreatePatientInput; override?: boolean }) =>
      patientsApi.create(input, { override }),
    onSuccess: (result) => {
      if (result.patient) {
        queryClient.invalidateQueries({ queryKey: patientsKeys.all });
        toast({ title: "Patient added", variant: "success" });
      }
    },
    onError: (error) => {
      toast({
        title: "Could not add patient",
        description: errorMessage(error, "Please check the form and try again."),
        variant: "error",
      });
    },
  });
}

export function useUpdatePatient(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ input, override }: { input: EditPatientInput; override?: boolean }) =>
      patientsApi.update(id, input, { override }),
    onSuccess: (result) => {
      if (result.patient) {
        queryClient.invalidateQueries({ queryKey: patientsKeys.all });
        toast({ title: "Patient updated", variant: "success" });
      }
    },
    onError: (error) => {
      toast({
        title: "Could not update patient",
        description: errorMessage(error, "Please check the form and try again."),
        variant: "error",
      });
    },
  });
}

export function useArchivePatient() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (id: string) => patientsApi.archive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: patientsKeys.all });
      toast({ title: "Patient archived", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not archive patient",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useRestorePatient() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (id: string) => patientsApi.restore(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: patientsKeys.all });
      toast({ title: "Patient restored", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not restore patient",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useUploadPatientPhoto(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (file: File) => patientsApi.uploadPhoto(id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: patientsKeys.detail(id) });
      toast({ title: "Photo updated", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not upload photo",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}
