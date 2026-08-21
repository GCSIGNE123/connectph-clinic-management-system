"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notificationsApi } from "@/features/notifications/api/notifications-api";

export const notificationKeys = {
  list: () => ["notifications", "list"] as const,
  unreadCount: () => ["notifications", "unread-count"] as const,
};

// Same 3s-polling convention as the Messages bell (`use-messages.ts`) -
// this is a lightweight badge/dropdown, not something that needs the
// Queue/TV Display WebSocket channel.
const POLL_INTERVAL_MS = 3_000;

/** `enabled` defaults to true; pass `false` for roles the backend's
 * `INVENTORY_NOTIFICATION_ROLES` gate would 403 (e.g. Cashier) so the UI
 * never fires a request it knows will fail. */
export function useUnreadNotificationCount(enabled = true) {
  return useQuery({
    queryKey: notificationKeys.unreadCount(),
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: POLL_INTERVAL_MS,
    enabled,
  });
}

export function useNotificationList(enabled = true) {
  return useQuery({
    queryKey: notificationKeys.list(),
    queryFn: () => notificationsApi.list({ limit: 20 }),
    refetchInterval: POLL_INTERVAL_MS,
    enabled,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.list() });
      queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount() });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.list() });
      queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount() });
    },
  });
}
