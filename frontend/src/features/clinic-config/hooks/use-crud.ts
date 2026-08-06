"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";

/** Generic query-key + query/mutation hook factory for a master-data resource. */
export function createCrudHooks<T extends { id: string }>(resourceKey: string, resourcePath: string) {
  const api = createCrudApi<T>(resourcePath);
  const keys = {
    all: [resourceKey] as const,
    list: (query: Record<string, unknown>) => [resourceKey, "list", query] as const,
  };

  function useList(query: Record<string, string | number | boolean | undefined> = {}) {
    return useQuery({
      queryKey: keys.list(query),
      queryFn: () => api.list(query),
      placeholderData: (prev) => prev,
    });
  }

  function useMutations() {
    const queryClient = useQueryClient();
    const invalidate = () => queryClient.invalidateQueries({ queryKey: keys.all });

    const create = useMutation({ mutationFn: (payload: Partial<T>) => api.create(payload), onSuccess: invalidate });
    const update = useMutation({
      mutationFn: ({ id, payload }: { id: string; payload: Partial<T> }) => api.update(id, payload),
      onSuccess: invalidate,
    });
    const remove = useMutation({ mutationFn: (id: string) => api.remove(id), onSuccess: invalidate });
    const restore = useMutation({ mutationFn: (id: string) => api.restore(id), onSuccess: invalidate });

    return { create, update, remove, restore };
  }

  return { api, keys, useList, useMutations };
}
