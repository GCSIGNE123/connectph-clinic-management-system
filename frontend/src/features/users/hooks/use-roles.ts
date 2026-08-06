"use client";

import { useQuery } from "@tanstack/react-query";
import { rolesApi } from "@/features/users/api/users-api";

export const rolesKeys = {
  all: ["roles"] as const,
};

/** The fixed set of platform roles (`GET /api/v1/roles`), used to resolve a
 * `role_id` from the role name selected in the user create/edit form. */
export function useRoles() {
  return useQuery({
    queryKey: rolesKeys.all,
    queryFn: () => rolesApi.list(),
    staleTime: 10 * 60 * 1000,
  });
}
