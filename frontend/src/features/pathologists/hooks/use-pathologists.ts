"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@/components/ui/toast";
import { pathologistsApi } from "@/features/pathologists/api/pathologists-api";
import { ApiError } from "@/lib/api-client";

const pathologistsKey = (activeOnly = false) => ["pathologists", { activeOnly }] as const;

export function usePathologists(activeOnly = false, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: pathologistsKey(activeOnly),
    queryFn: () => pathologistsApi.list(activeOnly),
    enabled: options.enabled ?? true,
  });
}

export function usePathologist(id: string | null) {
  return useQuery({
    queryKey: ["pathologist", id],
    queryFn: () => pathologistsApi.get(id as string),
    enabled: Boolean(id),
  });
}

export function useCreatePathologist() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: pathologistsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pathologists"] });
      toast({ title: "Pathologist added", variant: "success" });
    },
    onError: (err) => toast({ title: "Could not add pathologist", description: (err as ApiError).message, variant: "error" }),
  });
}

export function useUpdatePathologist() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof pathologistsApi.update>[1] }) =>
      pathologistsApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pathologists"] });
      queryClient.invalidateQueries({ queryKey: ["pathologist"] });
      toast({ title: "Pathologist updated", variant: "success" });
    },
    onError: (err) => toast({ title: "Update failed", description: (err as ApiError).message, variant: "error" }),
  });
}

export function useDeletePathologist() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: pathologistsApi.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pathologists"] });
      toast({ title: "Pathologist removed", variant: "success" });
    },
    onError: (err) => toast({ title: "Could not remove pathologist", description: (err as ApiError).message, variant: "error" }),
  });
}
