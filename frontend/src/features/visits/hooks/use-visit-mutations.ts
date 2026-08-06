"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { visitsApi } from "@/features/visits/api/visits-api";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import type { UpdateVisitInput, VisitStatus } from "@/features/visits/types";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function useUpdateVisit(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: (input: UpdateVisitInput) => visitsApi.update(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: visitKeys.all });
      toast({ title: "Visit updated", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not update visit",
        description: errorMessage(error, "Please try again."),
        variant: "error",
      });
    },
  });
}

export function useChangeVisitStatus(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  return useMutation({
    mutationFn: ({ status, note }: { status: VisitStatus; note?: string }) => visitsApi.changeStatus(id, status, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: visitKeys.all });
      toast({ title: "Visit status updated", variant: "success" });
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
