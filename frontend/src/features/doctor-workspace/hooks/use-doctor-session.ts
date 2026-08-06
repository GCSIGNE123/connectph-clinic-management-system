"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { doctorWorkspaceApi } from "@/features/doctor-workspace/api/doctor-workspace-api";
import { doctorWorkspaceKeys } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";

/** Client Acceptance Revisions Round 3, item 14: Doctor Session Control -
 * whether this doctor has pressed "Start Receiving Patients" today, and the
 * "Next Patient" auto-advance action. Reuses the same query-key
 * invalidation the rest of the Doctor Workspace hooks use, so the existing
 * `useDoctorWorkspaceRealtime()` WebSocket subscription (which invalidates
 * `doctorWorkspaceKeys.all` on every `visit.*`/other event) keeps this in
 * sync too - no new realtime plumbing needed. */

const sessionKey = (doctorId?: string) => [...doctorWorkspaceKeys.all, "session", doctorId ?? "self"] as const;

export function useDoctorSession(doctorId?: string, enabled: boolean = true) {
  return useQuery({
    queryKey: sessionKey(doctorId),
    queryFn: () => doctorWorkspaceApi.getSessionStatus(doctorId),
    refetchInterval: 15_000,
    enabled,
  });
}

export function useStartDoctorSession(doctorId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => doctorWorkspaceApi.startSession(doctorId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all }),
  });
}

export function useEndDoctorSession(doctorId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => doctorWorkspaceApi.endSession(doctorId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all }),
  });
}

export function useNextPatient(doctorId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => doctorWorkspaceApi.nextPatient(doctorId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all }),
  });
}
