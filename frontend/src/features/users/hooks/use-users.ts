"use client";

import { useQuery } from "@tanstack/react-query";
import { usersApi } from "@/features/users/api/users-api";
import type { UserListParams } from "@/features/users/types";

export const usersKeys = {
  all: ["users"] as const,
  list: (params: UserListParams) => ["users", "list", params] as const,
  detail: (id: string) => ["users", "detail", id] as const,
};

/** Paginated, searchable user list. */
export function useUsers(params: UserListParams) {
  return useQuery({
    queryKey: usersKeys.list(params),
    queryFn: () => usersApi.list(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useUser(id: string | undefined) {
  return useQuery({
    queryKey: usersKeys.detail(id ?? ""),
    queryFn: () => usersApi.get(id as string),
    enabled: Boolean(id),
  });
}
