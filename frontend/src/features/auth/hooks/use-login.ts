"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi } from "@/features/auth/api/auth-api";
import type { LoginInput } from "@/features/auth/schemas/auth-schemas";
import { authKeys } from "@/features/auth/hooks/use-current-user";

/**
 * Mutation hook for logging in. On success it seeds the current-user cache
 * and redirects to the dashboard.
 */
export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: (input: LoginInput) => authApi.login(input),
    onSuccess: (session) => {
      queryClient.setQueryData(authKeys.currentUser, session.user);
      router.push("/dashboard");
    },
  });
}
