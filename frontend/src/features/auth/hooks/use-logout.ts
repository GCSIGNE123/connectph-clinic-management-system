"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi } from "@/features/auth/api/auth-api";

/**
 * Mutation hook for logging out. Clears cached query state and redirects
 * to the login screen regardless of whether the backend call succeeds.
 */
export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: () => authApi.logout(),
    onSettled: () => {
      queryClient.clear();
      router.push("/login");
    },
  });
}
