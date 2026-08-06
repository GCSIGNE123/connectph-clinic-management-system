import { apiClient } from "@/lib/api-client";
import type { ConversationResponse, ConversationUnread, InternalMessage, StaffDirectoryEntry } from "@/features/messages/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

function toMessage(raw: any): InternalMessage {
  return {
    id: raw.id,
    senderId: raw.sender_id,
    senderName: raw.sender_name,
    recipientId: raw.recipient_id,
    recipientName: raw.recipient_name,
    body: raw.body,
    readAt: raw.read_at,
    createdAt: raw.created_at,
  };
}

export const messagesApi = {
  send: async (recipientId: string, body: string): Promise<InternalMessage> => {
    const raw = await apiClient.post<any>("/messages", { recipient_id: recipientId, body });
    return toMessage(raw);
  },
  getConversation: async (otherUserId: string): Promise<ConversationResponse> => {
    const raw = await apiClient.get<any>(`/messages/conversation/${otherUserId}`);
    return { items: (raw.items ?? []).map(toMessage), total: raw.total, unreadCount: raw.unread_count };
  },
  getUnreadCount: async (): Promise<number> => {
    const raw = await apiClient.get<{ unread_count: number }>("/messages/unread-count");
    return raw.unread_count;
  },
  getStaffDirectory: async (): Promise<StaffDirectoryEntry[]> => {
    const raw = await apiClient.get<any[]>("/messages/staff-directory");
    return raw.map((r) => ({ id: r.id, fullName: r.full_name, role: r.role }));
  },
  getUnreadByConversation: async (): Promise<ConversationUnread[]> => {
    const raw = await apiClient.get<any[]>("/messages/unread-by-conversation");
    return raw.map((r) => ({
      otherUserId: r.other_user_id,
      otherUserName: r.other_user_name,
      unreadCount: r.unread_count,
      lastMessageAt: r.last_message_at,
    }));
  },
};
