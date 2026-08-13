"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { doctorWorkspaceApi } from "@/features/doctor-workspace/api/doctor-workspace-api";
import { doctorWorkspaceKeys } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

/** Client Acceptance Revisions Round 3, item 14: Doctor Session Control -
 * whether this doctor has pressed "Start Receiving Patients" today, and the
 * "Next Patient" auto-advance action. Reuses the same query-key
 * invalidation the rest of the Doctor Workspace hooks use, so the existing
 * `useDoctorWorkspaceRealtime()` WebSocket subscription (which invalidates
 * `doctorWorkspaceKeys.all` on every `visit.*`/other event) keeps this in
 * sync too - no new realtime plumbing needed. */

const sessionKey = (doctorId?: string) => [...doctorWorkspaceKeys.all, "session", doctorId ?? "self"] as const;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function useDoctorSession(doctorId?: string, enabled: boolean = true) {
  return useQuery({
    queryKey: sessionKey(doctorId),
    queryFn: () => doctorWorkspaceApi.getSessionStatus(doctorId),
    refetchInterval: 15_000,
    enabled,
  });
}

/** Real bug found live: this account's `startSession()` call was rejected
 * (400, "This account is not linked to a Doctor record.") but nothing
 * surfaced it - the button just silently did nothing on click, which read
 * as "unclickable" rather than "rejected for a real, fixable reason". Every
 * mutation below now shows the actual backend message on failure. */
export function useStartDoctorSession(doctorId?: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => doctorWorkspaceApi.startSession(doctorId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all }),
    onError: (error) => {
      toast({
        title: "Could not start receiving patients",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useEndDoctorSession(doctorId?: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => doctorWorkspaceApi.endSession(doctorId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all }),
    onError: (error) => {
      toast({
        title: "Could not end session",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useNextPatient(doctorId?: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: () => doctorWorkspaceApi.nextPatient(doctorId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all }),
    onError: (error) => {
      toast({
        title: "Could not advance to next patient",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}
