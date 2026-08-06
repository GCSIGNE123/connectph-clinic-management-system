"use client";

import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { doctorWorkspaceApi } from "@/features/doctor-workspace/api/doctor-workspace-api";
import { doctorWorkspaceKeys } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";
import type { DoctorWsEvent } from "@/features/doctor-workspace/types";
import { tokenStorage } from "@/lib/api-client";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";

/** Today's visits assigned to the logged-in doctor (or all/filtered for
 * Owner/Administrator via `doctorId`). Polls every 15s as a fallback and
 * refreshes immediately on `ws.queues` realtime events. */
export function useDoctorQueue(doctorId?: string) {
  return useQuery({
    queryKey: doctorWorkspaceKeys.queue(doctorId),
    queryFn: () => doctorWorkspaceApi.getQueue(doctorId),
    placeholderData: (previousData) => previousData,
    refetchInterval: 15_000,
  });
}

function wsUrl(clinicId: string, token: string): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000/api/v1";
  const wsBase = apiUrl.replace(/^http/, "ws").replace(/\/api\/v1$/, "");
  return `${wsBase}/api/v1/ws/queues/${clinicId}?token=${encodeURIComponent(token)}`;
}

/**
 * Subscribes to the same `/ws/queues/{clinicId}` channel the Reception
 * Dashboard uses (see `services/doctor_workspace_service.py` - it
 * broadcasts `visit.called` / `visit.consultation_started` /
 * `visit.consultation_completed` / `visit.status_changed` /
 * `visit.lock_acquired` / `visit.lock_released` on the same connection
 * manager) and invalidates the Doctor Workspace queries on any event so the
 * Doctor Dashboard/queue/lock banner stay live without a hard poll.
 */
export function useDoctorWorkspaceRealtime() {
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
          const parsed = JSON.parse(event.data) as DoctorWsEvent;
          if (parsed.event?.startsWith("visit.")) {
            queryClient.invalidateQueries({ queryKey: doctorWorkspaceKeys.all });
          }
        } catch {
          // Ignore malformed frames - the 15s poll in `useDoctorQueue` is the fallback.
        }
      };
    } catch {
      // WebSocket construction can throw synchronously (e.g. SSR); polling still works.
    }

    return () => {
      cancelled = true;
      socket?.close();
      socketRef.current = null;
    };
  }, [currentUser?.clinicId, queryClient]);
}
