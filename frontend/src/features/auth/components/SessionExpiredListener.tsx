"use client";

import { useEffect } from "react";
import { SESSION_EXPIRED_EVENT } from "@/lib/api-client";

/**
 * Mounted once, app-wide (see `lib/query-client.tsx::Providers`). Listens
 * for `SESSION_EXPIRED_EVENT` (dispatched by `apiClient` when the automatic
 * token-refresh dance exhausts itself - see that constant's doc comment)
 * and sends the user back to `/login`.
 *
 * Uses a hard navigation (`window.location.href`), not `router.push` -
 * deliberately, for two reasons: (1) it re-runs the Next.js middleware's
 * session-cookie check on the way to `/login`, and (2) it fully resets
 * client state (open dialogs, in-flight queries against a dead session)
 * rather than leaving stale UI mounted under a route the user can no longer
 * actually use.
 */
export function SessionExpiredListener() {
  useEffect(() => {
    function handleSessionExpired() {
      window.location.href = "/login";
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  return null;
}
