"use client";

import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queueApi } from "@/features/queue/api/queue-api";
import type { QueueListParams, QueueWsEvent } from "@/features/queue/types";
import { tokenStorage } from "@/lib/api-client";
import { getApiBaseUrl } from "@/lib/api-url";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";

export const queueKeys = {
  all: ["queue"] as const,
  list: (params: QueueListParams) => ["queue", "list", params] as const,
  detail: (id: string) => ["queue", "detail", id] as const,
  slip: (id: string) => ["queue", "slip", id] as const,
};

/** Today's live queue list: search/filter/paginate + realtime updates. */
export function useQueues(params: QueueListParams) {
  return useQuery({
    queryKey: queueKeys.list(params),
    queryFn: () => queueApi.list(params),
    placeholderData: (previousData) => previousData,
    refetchInterval: 30_000, // belt-and-suspenders poll in case the WS drops
  });
}

export function useQueueDetail(id: string | null) {
  return useQuery({
    queryKey: queueKeys.detail(id ?? ""),
    queryFn: () => queueApi.get(id as string),
    enabled: Boolean(id),
  });
}

function wsUrl(clinicId: string, token: string): string {
  const apiUrl = getApiBaseUrl();
  const wsBase = apiUrl.replace(/^http/, "ws").replace(/\/api\/v1$/, "");
  return `${wsBase}/api/v1/ws/queues/${clinicId}?token=${encodeURIComponent(token)}`;
}

/**
 * Subscribes to `/ws/queues/{clinicId}` and invalidates the queue list /
 * detail caches on `queue.created` / `queue.updated` / `queue.status_changed`
 * so the Reception Dashboard stays live without polling every second.
 * Falls back gracefully (via `useQueues`'s `refetchInterval`) if the socket
 * cannot connect - see `ws_manager.py` for the documented Redis pub/sub TODO
 * needed before this endpoint can broadcast across multiple API processes.
 */
export function useQueueRealtime() {
  const { data: currentUser } = useCurrentUser();
  const queryClient = useQueryClient();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!currentUser?.clinicId) return;
    const token = tokenStorage.getAccessToken();
    if (!token) return;

    let cancelled = false;
    let socket: WebSocket | null = null;

    try {
      socket = new WebSocket(wsUrl(currentUser.clinicId, token));
      socketRef.current = socket;

      socket.onmessage = (event) => {
        if (cancelled) return;
        try {
          JSON.parse(event.data) as QueueWsEvent;
          // Any create/update/status-change event invalidates the list +
          // this ticket's detail cache; React Query refetches whatever is
          // currently mounted/observed.
          queryClient.invalidateQueries({ queryKey: queueKeys.all });
        } catch {
          // Ignore malformed frames - the 30s poll in `useQueues` is the fallback.
        }
      };
    } catch {
      // WebSocket construction can throw synchronously in some environments
      // (e.g. SSR); the list still works via polling.
    }

    return () => {
      cancelled = true;
      socket?.close();
      socketRef.current = null;
    };
  }, [currentUser?.clinicId, queryClient]);
}
