"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { doctorWorkspaceApi } from "@/features/doctor-workspace/api/doctor-workspace-api";
import { doctorWorkspaceKeys } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { announceQueueNumber } from "@/lib/queue-announcer";

function useInvalidateWorkspace() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all });
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
    onSuccess: (data) => {
      toast({ title: successMessage, variant: "success" });
      onSuccessExtra?.(data);
      invalidate();
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
    onSuccess: () => {
      toast({ title: "Visit cancelled", variant: "success" });
      invalidate();
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
