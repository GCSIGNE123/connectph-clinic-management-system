import { apiClient } from "@/lib/api-client";
import type {
  CreateAnnouncementInput,
  CreateTvDisplayInput,
  TvAnnouncement,
  TvDisplayConfig,
  TvDisplayData,
  UpdateTvDisplayInput,
} from "@/features/tv-display/types";

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
      roomName: e.room_name,
      status: e.status,
      calledAt: e.called_at,
    })),
    nextWaiting: (raw.next_waiting ?? []).map((e: any) => ({
      queueId: e.queue_id,
      queueNumber: e.queue_number,
      patientInitials: e.patient_initials,
      doctorName: e.doctor_name,
      priority: e.priority,
    })),
    announcements: (raw.announcements ?? []).map(toAnnouncement),
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
