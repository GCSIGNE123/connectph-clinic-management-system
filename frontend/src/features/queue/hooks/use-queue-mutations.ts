"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queueApi } from "@/features/queue/api/queue-api";
import { queueKeys } from "@/features/queue/hooks/use-queues";
import { QueueStatus } from "@/features/queue/types";
import type { CreateQueueInput, UpdateQueueInput } from "@/features/queue/types";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { announceQueueNumber } from "@/lib/queue-announcer";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** `onShiftRequired` (item 7): see `features/billing/hooks/use-payments.ts`
 * doc - same pattern, since queueing is now gated behind "Receptionist has
 * an open shift". */
export function useCreateQueue(onShiftRequired?: (error: unknown) => boolean) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (input: CreateQueueInput) => queueApi.create(input),
    onSuccess: (queue) => {
      queryClient.invalidateQueries({ queryKey: queueKeys.all });
      toast({ title: `Queue ${queue.queueNumber} created`, variant: "success" });
    },
    onError: (error) => {
      if (onShiftRequired?.(error)) return;
      toast({
        title: "Could not create queue ticket",
        description: errorMessage(error, "Please check the form and try again."),
        variant: "error",
      });
    },
  });
}

export function useUpdateQueue(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (input: UpdateQueueInput) => queueApi.update(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queueKeys.all });
      toast({ title: "Queue ticket updated", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not update queue ticket",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useChangeQueueStatus() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ id, status, note }: { id: string; status: QueueStatus; note?: string }) =>
      queueApi.changeStatus(id, status, note),
    onSuccess: (queue, variables) => {
      queryClient.invalidateQueries({ queryKey: queueKeys.all });
      // Item 8: the Reception Queue view's "Call" action is this same
      // Waiting -> Called status transition (there's no separate
      // call/recall endpoint here like Doctor Workspace has) - announce it
      // with the same shared TTS utility so both surfaces sound identical.
      if (variables.status === QueueStatus.Called) {
        announceQueueNumber(queue.queueNumber);
      }
    },
    onError: (error) => {
      toast({
        title: "Could not update status",
        description: errorMessage(error, "That transition isn't allowed from the current status."),
        variant: "error",
      });
    },
  });
}

export function useCancelQueue() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (id: string) => queueApi.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queueKeys.all });
      toast({ title: "Queue ticket cancelled", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not cancel queue ticket",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}
