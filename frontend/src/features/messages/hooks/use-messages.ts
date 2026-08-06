"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { messagesApi } from "@/features/messages/api/messages-api";

export const messagesKeys = {
  conversation: (otherUserId: string) => ["messages", "conversation", otherUserId] as const,
  unreadCount: () => ["messages", "unread-count"] as const,
};

/** Polling-based, matching the "plain polling is fine" scope note - this
 * feature doesn't need the WebSocket infrastructure Queue/TV Display use
 * for a minimal Receptionist<->Doctor message list.
 *
 * Client Acceptance Revisions - Round 3 (item 2): the client's target
 * latency is "2-3 seconds". The Queue/TV Display WebSocket channel
 * (`app/api/v1/ws_queues.py`) is queue-event-specific (ticket
 * created/called/status-changed payloads keyed by queue/visit) - piping
 * unrelated message-notification events through it would require a new
 * event type, a new subscription/broadcast path, and frontend wiring to a
 * channel this feature doesn't otherwise use, for a feature whose own
 * scope note says polling is fine. That's a bigger, messier change than
 * the goal calls for, so the fix here is tightening the interval from 30s
 * to 3s (both the unread badge/dropdown and the open conversation view),
 * which meets the stated target directly. */
export function useConversation(otherUserId: string | undefined) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: messagesKeys.conversation(otherUserId ?? ""),
    queryFn: async () => {
      const data = await messagesApi.getConversation(otherUserId as string);
      // The GET side-effects mark that partner's messages read (server-side,
      // scoped to `other_user_id` only) - refresh the badges that summarize
      // unread state so this conversation's indicator drops immediately
      // without waiting for the next 30s poll, while other conversations'
      // counts are untouched (they weren't part of this query at all).
      queryClient.invalidateQueries({ queryKey: messagesKeys.unreadCount() });
      queryClient.invalidateQueries({ queryKey: ["messages", "unread-by-conversation"] });
      return data;
    },
    enabled: Boolean(otherUserId),
    refetchInterval: 3_000,
  });
}

export function useUnreadMessageCount() {
  return useQuery({
    queryKey: messagesKeys.unreadCount(),
    queryFn: () => messagesApi.getUnreadCount(),
    refetchInterval: 3_000,
  });
}

export function useUnreadByConversation() {
  return useQuery({
    queryKey: ["messages", "unread-by-conversation"] as const,
    queryFn: () => messagesApi.getUnreadByConversation(),
    refetchInterval: 3_000,
  });
}

export function useStaffDirectory() {
  return useQuery({
    queryKey: ["messages", "staff-directory"] as const,
    queryFn: () => messagesApi.getStaffDirectory(),
  });
}

export function useSendMessage(otherUserId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => messagesApi.send(otherUserId as string, body),
    onSuccess: () => {
      if (otherUserId) queryClient.invalidateQueries({ queryKey: messagesKeys.conversation(otherUserId) });
      queryClient.invalidateQueries({ queryKey: messagesKeys.unreadCount() });
    },
  });
}
