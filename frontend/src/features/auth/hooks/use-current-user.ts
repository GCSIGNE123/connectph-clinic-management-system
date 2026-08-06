"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { authApi } from "@/features/auth/api/auth-api";
import { tokenStorage } from "@/lib/api-client";

export const authKeys = {
  currentUser: ["auth", "current-user"] as const,
};

/**
 * Fetches the currently authenticated user. Disabled entirely when there is
 * no access token in storage, so it won't fire a doomed request on public
 * pages.
 *
 * `enabled` only flips on after mount (never reads `window`/storage during
 * the render that produces hydration output) so the client's hydration pass
 * matches the server-rendered markup exactly, then the query kicks in on the
 * next tick. Checking `typeof window` directly here would make the very
 * first client render diverge from the server render and trigger a React
 * hydration-mismatch error.
 */
export function useCurrentUser() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return useQuery({
    queryKey: authKeys.currentUser,
    queryFn: () => authApi.me(),
    enabled: mounted && Boolean(tokenStorage.getAccessToken()),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}
