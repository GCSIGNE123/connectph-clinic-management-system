import { apiClient } from "@/lib/api-client";

export interface AppNotification {
  id: string;
  clinic_id: string;
  type: string;
  title: string;
  body: string;
  entity_type?: string | null;
  entity_id?: string | null;
  created_at: string;
  is_read: boolean;
}

export interface NotificationListResponse {
  items: AppNotification[];
  total: number;
}

export const notificationsApi = {
  async list(params: { limit?: number; offset?: number } = {}): Promise<NotificationListResponse> {
    const search = new URLSearchParams();
    if (params.limit !== undefined) search.set("limit", String(params.limit));
    if (params.offset !== undefined) search.set("offset", String(params.offset));
    const qs = search.toString();
    return apiClient.get<NotificationListResponse>(`/notifications${qs ? `?${qs}` : ""}`);
  },
  async unreadCount(): Promise<number> {
    const res = await apiClient.get<{ unread_count: number }>("/notifications/unread-count");
    return res.unread_count;
  },
  async markRead(id: string): Promise<void> {
    return apiClient.post<void>(`/notifications/${id}/read`);
  },
  async markAllRead(): Promise<{ marked_count: number }> {
    return apiClient.post<{ marked_count: number }>("/notifications/read-all");
  },
};
