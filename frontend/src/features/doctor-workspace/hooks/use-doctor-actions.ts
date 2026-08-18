"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { doctorWorkspaceApi } from "@/features/doctor-workspace/api/doctor-workspace-api";
import { doctorWorkspaceKeys } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { announceQueueNumber } from "@/lib/queue-announcer";

/** Phase 5B (P1, D4): Doctor Workspace actions change a Visit's status,
 * but previously only invalidated `doctorWorkspaceKeys` - the standalone
 * Visit Details page (`visitKeys.detail`) has no WebSocket/poll refresh of
 * its own, so it could show a stale status indefinitely after another
 * staff member completed/called/cancelled the same visit elsewhere. Also
 * invalidating `visitKeys.detail(visitId)` here (the exact query key the
 * Visit Details page reads) is the same targeted-invalidation convention
 * `features/clinical-orders/hooks/use-clinical-orders.ts` already uses
 * correctly for this same page. */
function useInvalidateWorkspace() {
  const queryClient = useQueryClient();
  return (visitId?: string) => {
    queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all });
    if (visitId) queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
  };
}

function useSimpleAction<TResult>(
  fn: (visitId: string) => Promise<TResult>,
  successMessage: string,
  onSuccessExtra?: (data: TResult) => void
) {
  const { toast } = useToast();
  const invalidate = useInvalidateWorkspace();
  return useMutation({
    mutationFn: (visitId: string) => fn(visitId),
    onSuccess: (data, visitId) => {
      toast({ title: successMessage, variant: "success" });
      onSuccessExtra?.(data);
      invalidate(visitId);
    },
    onError: (error) => {
      toast({
        title: "Action failed",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}

export function useCallPatient() {
  // Item 8: real TTS announcement ("Now serving patient number ...") when
  // a Call actually succeeds (not on click - only once the backend
  // confirms the transition and returns the real queue number), replacing
  // Phase 20 item 12's basic `playCallCue` two-tone chime.
  return useSimpleAction(doctorWorkspaceApi.call, "Patient called", (data) => announceQueueNumber(data.queue_number));
}

export function useRecallPatient() {
  // Recall repeats the same announcement pattern for the same queue number.
  return useSimpleAction(doctorWorkspaceApi.recall, "Patient re-called", (data) => announceQueueNumber(data.queue_number));
}

export function useStartConsultation() {
  return useSimpleAction(doctorWorkspaceApi.startConsultation, "Consultation started");
}

export function useCompleteConsultation() {
  return useSimpleAction(doctorWorkspaceApi.completeConsultation, "Consultation completed");
}

export function useMarkNoShow() {
  return useSimpleAction(doctorWorkspaceApi.noShow, "Marked as no-show");
}

export function useCancelVisit() {
  const { toast } = useToast();
  const invalidate = useInvalidateWorkspace();
  return useMutation({
    mutationFn: ({ visitId, reason }: { visitId: string; reason?: string }) => doctorWorkspaceApi.cancel(visitId, reason),
    onSuccess: (_data, { visitId }) => {
      toast({ title: "Visit cancelled", variant: "success" });
      invalidate(visitId);
    },
    onError: (error) => {
      toast({
        title: "Cancel failed",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}

/** Acquire/refresh the visit lock. Intended to be called on visit-viewer
 * mount and then periodically as a heartbeat (see `LOCK_TTL_MINUTES` in
 * `doctor_workspace_service.py`) while the viewer stays open. */
export function useOpenVisit() {
  return useMutation({ mutationFn: (visitId: string) => doctorWorkspaceApi.openVisit(visitId) });
}

export function useReleaseLock() {
  const invalidate = useInvalidateWorkspace();
  return useMutation({
    mutationFn: (visitId: string) => doctorWorkspaceApi.releaseLock(visitId),
    onSuccess: () => invalidate(),
  });
}
