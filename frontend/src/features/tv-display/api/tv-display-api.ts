import { apiClient, tokenStorage } from "@/lib/api-client";
import type {
  CreateAnnouncementInput,
  CreateTvDisplayInput,
  CreateTvInfoContentInput,
  TvAnnouncement,
  TvDisplayConfig,
  TvDisplayData,
  TvInfoContentItem,
  UpdateTvDisplayInput,
  UpdateTvInfoContentInput,
} from "@/features/tv-display/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000/api/v1";

/** `image_url` on a `TvInfoContentItem` is a backend-relative path (e.g.
 * `/media/tv-info-content/{clinic_id}/{file}`), not an absolute URL - the
 * backend has no public base-URL setting (see `app/main.py`'s static mount).
 * Resolve it against the API origin (stripping the `/api/v1` suffix) so
 * `<img src>` works regardless of which host/port the API is served from. */
export function resolveTvMediaUrl(imageUrl: string | null): string | null {
  if (!imageUrl) return null;
  if (/^https?:\/\//i.test(imageUrl)) return imageUrl;
  const origin = API_URL.replace(/\/api\/v1\/?$/, "");
  return `${origin}${imageUrl}`;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function toConfig(raw: any): TvDisplayConfig {
  return {
    id: raw.id,
    clinicId: raw.clinic_id,
    branchId: raw.branch_id,
    departmentId: raw.department_id,
    doctorId: raw.doctor_id,
    displayName: raw.display_name,
    isPublic: raw.is_public,
    publicSlug: raw.public_slug,
    theme: raw.theme,
    fontSize: raw.font_size,
    animationSpeed: raw.animation_speed,
    queueSize: raw.queue_size,
    refreshIntervalSeconds: raw.refresh_interval_seconds,
    logoUrl: raw.logo_url,
    primaryColor: raw.primary_color,
    secondaryColor: raw.secondary_color,
    ttsEnabled: raw.tts_enabled,
    ttsTemplate: raw.tts_template,
    isActive: raw.is_active,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toAnnouncement(raw: any): TvAnnouncement {
  return {
    id: raw.id,
    tvDisplayConfigId: raw.tv_display_config_id,
    message: raw.message,
    announcementType: raw.announcement_type,
    displayOrder: raw.display_order,
    isActive: raw.is_active,
    startsAt: raw.starts_at,
    endsAt: raw.ends_at,
    createdAt: raw.created_at,
  };
}

function toInfoContent(raw: any): TvInfoContentItem {
  return {
    id: raw.id,
    title: raw.title,
    body: raw.body,
    contentType: raw.content_type,
    durationSeconds: raw.duration_seconds,
    displayOrder: raw.display_order,
    isActive: raw.is_active,
    imageUrl: raw.image_url,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toDisplayData(raw: any): TvDisplayData {
  return {
    displayName: raw.display_name,
    clinicName: raw.clinic_name,
    branchName: raw.branch_name,
    theme: raw.theme,
    fontSize: raw.font_size,
    animationSpeed: raw.animation_speed,
    queueSize: raw.queue_size,
    refreshIntervalSeconds: raw.refresh_interval_seconds,
    logoUrl: raw.logo_url,
    primaryColor: raw.primary_color,
    secondaryColor: raw.secondary_color,
    nowServing: (raw.now_serving ?? []).map((e: any) => ({
      queueId: e.queue_id,
      queueNumber: e.queue_number,
      patientInitials: e.patient_initials,
      doctorName: e.doctor_name,
      departmentId: e.department_id ?? null,
      departmentName: e.department_name ?? null,
      roomName: e.room_name,
      status: e.status,
      calledAt: e.called_at,
    })),
    nextWaiting: (raw.next_waiting ?? []).map((e: any) => ({
      queueId: e.queue_id,
      queueNumber: e.queue_number,
      patientInitials: e.patient_initials,
      doctorName: e.doctor_name,
      departmentId: e.department_id ?? null,
      departmentName: e.department_name ?? null,
      priority: e.priority,
    })),
    announcements: (raw.announcements ?? []).map(toAnnouncement),
    infoContent: (raw.info_content ?? []).map(toInfoContent),
    serverTime: raw.server_time,
    wsChannelClinicId: raw.ws_channel_clinic_id,
    wsAuthSlug: raw.ws_auth_slug,
  };
}

function toCreatePayload(input: CreateTvDisplayInput) {
  return {
    branch_id: input.branchId || null,
    department_id: input.departmentId || null,
    doctor_id: input.doctorId || null,
    display_name: input.displayName,
    is_public: input.isPublic,
    theme: input.theme,
    font_size: input.fontSize,
    animation_speed: input.animationSpeed,
    queue_size: input.queueSize,
    refresh_interval_seconds: input.refreshIntervalSeconds,
    logo_url: input.logoUrl || null,
    primary_color: input.primaryColor || null,
    secondary_color: input.secondaryColor || null,
    tts_enabled: input.ttsEnabled,
    tts_template: input.ttsTemplate || null,
  };
}

function toUpdatePayload(input: UpdateTvDisplayInput) {
  const payload: Record<string, unknown> = {};
  if (input.branchId !== undefined) payload.branch_id = input.branchId || null;
  if (input.departmentId !== undefined) payload.department_id = input.departmentId || null;
  if (input.doctorId !== undefined) payload.doctor_id = input.doctorId || null;
  if (input.displayName !== undefined) payload.display_name = input.displayName;
  if (input.isPublic !== undefined) payload.is_public = input.isPublic;
  if (input.theme !== undefined) payload.theme = input.theme;
  if (input.fontSize !== undefined) payload.font_size = input.fontSize;
  if (input.animationSpeed !== undefined) payload.animation_speed = input.animationSpeed;
  if (input.queueSize !== undefined) payload.queue_size = input.queueSize;
  if (input.refreshIntervalSeconds !== undefined) payload.refresh_interval_seconds = input.refreshIntervalSeconds;
  if (input.logoUrl !== undefined) payload.logo_url = input.logoUrl || null;
  if (input.primaryColor !== undefined) payload.primary_color = input.primaryColor || null;
  if (input.secondaryColor !== undefined) payload.secondary_color = input.secondaryColor || null;
  if (input.ttsEnabled !== undefined) payload.tts_enabled = input.ttsEnabled;
  if (input.ttsTemplate !== undefined) payload.tts_template = input.ttsTemplate || null;
  if (input.isActive !== undefined) payload.is_active = input.isActive;
  return payload;
}

/** `/api/v1/tv-displays/*` (admin, JWT-required) plus the no-auth public
 * snapshot endpoint. See `docs/API.md` for the public-endpoint security
 * model this mirrors. */
export const tvDisplayApi = {
  async list(): Promise<TvDisplayConfig[]> {
    const raw = await apiClient.get<any[]>("/tv-displays");
    return raw.map(toConfig);
  },
  async get(id: string): Promise<TvDisplayConfig> {
    const raw = await apiClient.get<any>(`/tv-displays/${id}`);
    return toConfig(raw);
  },
  async create(input: CreateTvDisplayInput): Promise<TvDisplayConfig> {
    const raw = await apiClient.post<any>("/tv-displays", toCreatePayload(input));
    return toConfig(raw);
  },
  async update(id: string, input: UpdateTvDisplayInput): Promise<TvDisplayConfig> {
    const raw = await apiClient.patch<any>(`/tv-displays/${id}`, toUpdatePayload(input));
    return toConfig(raw);
  },
  async remove(id: string): Promise<void> {
    await apiClient.delete<void>(`/tv-displays/${id}`);
  },
  async preview(id: string): Promise<TvDisplayData> {
    const raw = await apiClient.get<any>(`/tv-displays/${id}/preview`);
    return toDisplayData(raw);
  },
  async listAnnouncements(configId: string): Promise<TvAnnouncement[]> {
    const raw = await apiClient.get<any[]>(`/tv-displays/${configId}/announcements`);
    return raw.map(toAnnouncement);
  },
  async createAnnouncement(configId: string, input: CreateAnnouncementInput): Promise<TvAnnouncement> {
    const raw = await apiClient.post<any>(`/tv-displays/${configId}/announcements`, {
      message: input.message,
      announcement_type: input.announcementType,
      display_order: input.displayOrder ?? 0,
      is_active: input.isActive ?? true,
      starts_at: input.startsAt || null,
      ends_at: input.endsAt || null,
    });
    return toAnnouncement(raw);
  },
  async updateAnnouncement(id: string, input: Partial<CreateAnnouncementInput>): Promise<TvAnnouncement> {
    const payload: Record<string, unknown> = {};
    if (input.message !== undefined) payload.message = input.message;
    if (input.announcementType !== undefined) payload.announcement_type = input.announcementType;
    if (input.displayOrder !== undefined) payload.display_order = input.displayOrder;
    if (input.isActive !== undefined) payload.is_active = input.isActive;
    if (input.startsAt !== undefined) payload.starts_at = input.startsAt || null;
    if (input.endsAt !== undefined) payload.ends_at = input.endsAt || null;
    const raw = await apiClient.patch<any>(`/announcements/${id}`, payload);
    return toAnnouncement(raw);
  },
  async deleteAnnouncement(id: string): Promise<void> {
    await apiClient.delete<void>(`/announcements/${id}`);
  },
  async listInfoContent(): Promise<TvInfoContentItem[]> {
    const raw = await apiClient.get<any[]>("/tv-info-content");
    return raw.map(toInfoContent);
  },
  async createInfoContent(input: CreateTvInfoContentInput): Promise<TvInfoContentItem> {
    const raw = await apiClient.post<any>("/tv-info-content", {
      title: input.title,
      body: input.body,
      content_type: input.contentType ?? "Announcement",
      duration_seconds: input.durationSeconds ?? 10,
      display_order: input.displayOrder ?? 0,
      is_active: input.isActive ?? true,
      image_url: input.imageUrl || null,
    });
    return toInfoContent(raw);
  },
  async updateInfoContent(id: string, input: UpdateTvInfoContentInput): Promise<TvInfoContentItem> {
    const payload: Record<string, unknown> = {};
    if (input.title !== undefined) payload.title = input.title;
    if (input.body !== undefined) payload.body = input.body;
    if (input.contentType !== undefined) payload.content_type = input.contentType;
    if (input.durationSeconds !== undefined) payload.duration_seconds = input.durationSeconds;
    if (input.displayOrder !== undefined) payload.display_order = input.displayOrder;
    if (input.isActive !== undefined) payload.is_active = input.isActive;
    if (input.imageUrl !== undefined) payload.image_url = input.imageUrl || null;
    const raw = await apiClient.patch<any>(`/tv-info-content/${id}`, payload);
    return toInfoContent(raw);
  },
  async deleteInfoContent(id: string): Promise<void> {
    await apiClient.delete<void>(`/tv-info-content/${id}`);
  },
  /** Real multipart upload (not a presigned-URL stub) - see
   * `app/api/v1/tv_display.py`'s module docstring for why this feature is
   * one of the few exceptions to this codebase's stub-upload convention.
   * Mirrors `migration-api.ts::uploadFiles`'s direct-`fetch`-with-`FormData`
   * pattern since `apiClient` always JSON-serializes its body. */
  async uploadInfoContentImage(id: string, file: File): Promise<TvInfoContentItem> {
    const form = new FormData();
    form.append("file", file);
    const token = tokenStorage.getAccessToken();
    const res = await fetch(`${API_URL}/tv-info-content/${id}/image`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      credentials: "include",
      body: form,
    });
    if (!res.ok) {
      let message = `Upload failed (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body.detail === "string") message = body.detail;
      } catch {
        // Non-JSON error body - keep the generic message.
      }
      throw new Error(message);
    }
    return toInfoContent(await res.json());
  },
  async deleteInfoContentImage(id: string): Promise<TvInfoContentItem> {
    const raw = await apiClient.delete<any>(`/tv-info-content/${id}/image`);
    return toInfoContent(raw);
  },
};

/** Public, no-auth-required snapshot fetch - deliberately bypasses
 * `apiClient` (which always attempts to attach a bearer token / refresh on
 * 401) since this must work with zero session state, e.g. in an
 * incognito/kiosk tab that never logged in. */
export async function fetchPublicTvDisplay(publicSlug: string): Promise<TvDisplayData> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:4000/api/v1";
  const res = await fetch(`${apiUrl}/public/tv-display/${encodeURIComponent(publicSlug)}`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(res.status === 404 ? "Display not found" : `Request failed (${res.status})`);
  }
  return toDisplayData(await res.json());
}
