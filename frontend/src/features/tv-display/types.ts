export type TvTheme = "Light" | "Dark" | "ClinicBranded";
export type TvFontSize = "Small" | "Medium" | "Large" | "ExtraLarge";
export type TvAnimationSpeed = "None" | "Slow" | "Normal" | "Fast";
export type TvAnnouncementType = "Welcome" | "HealthTip" | "Promotion" | "Emergency";
export type TvInfoContentType =
  | "ServicePricing"
  | "DoctorInfo"
  | "HealthTip"
  | "PreventiveReminder"
  | "Announcement"
  | "Promotion"
  | "Motivational";

export interface TvDisplayConfig {
  id: string;
  clinicId: string;
  branchId: string | null;
  departmentId: string | null;
  doctorId: string | null;
  displayName: string;
  isPublic: boolean;
  publicSlug: string | null;
  /** Post-RC1 (short TV display URL): optional admin-chosen short alias
   * for this display's public URL, e.g. "canora" - so a Smart TV remote
   * can type `/tv/canora` instead of the long `publicSlug`. `null` = no
   * short URL configured; the long `publicSlug` URL always keeps working
   * either way. */
  shortCode: string | null;
  theme: TvTheme;
  fontSize: TvFontSize;
  animationSpeed: TvAnimationSpeed;
  queueSize: number;
  refreshIntervalSeconds: number;
  logoUrl: string | null;
  primaryColor: string | null;
  secondaryColor: string | null;
  ttsEnabled: boolean;
  ttsTemplate: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateTvDisplayInput {
  branchId?: string | null;
  departmentId?: string | null;
  doctorId?: string | null;
  displayName: string;
  isPublic: boolean;
  shortCode?: string | null;
  theme?: TvTheme;
  fontSize?: TvFontSize;
  animationSpeed?: TvAnimationSpeed;
  queueSize?: number;
  refreshIntervalSeconds?: number;
  logoUrl?: string | null;
  primaryColor?: string | null;
  secondaryColor?: string | null;
  ttsEnabled?: boolean;
  ttsTemplate?: string | null;
}

export type UpdateTvDisplayInput = Partial<CreateTvDisplayInput> & { isActive?: boolean };

export interface TvAnnouncement {
  id: string;
  tvDisplayConfigId: string | null;
  message: string;
  announcementType: TvAnnouncementType;
  displayOrder: number;
  isActive: boolean;
  startsAt: string | null;
  endsAt: string | null;
  createdAt: string;
}

export interface CreateAnnouncementInput {
  message: string;
  announcementType: TvAnnouncementType;
  displayOrder?: number;
  isActive?: boolean;
  startsAt?: string | null;
  endsAt?: string | null;
}

export interface TvDisplayNowServing {
  queueId: string;
  queueNumber: string;
  patientInitials: string;
  doctorName: string | null;
  departmentId: string | null;
  departmentName: string | null;
  roomName: string | null;
  status: string;
  calledAt: string | null;
}

export interface TvDisplayWaitingEntry {
  queueId: string;
  queueNumber: string;
  patientInitials: string;
  doctorName: string | null;
  departmentId: string | null;
  departmentName: string | null;
  priority: string;
}

export interface TvInfoContentItem {
  id: string;
  title: string;
  body: string;
  contentType: TvInfoContentType;
  durationSeconds: number;
  displayOrder: number;
  isActive: boolean;
  imageUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateTvInfoContentInput {
  title: string;
  body: string;
  contentType?: TvInfoContentType;
  durationSeconds?: number;
  displayOrder?: number;
  isActive?: boolean;
  imageUrl?: string | null;
}

export type UpdateTvInfoContentInput = Partial<CreateTvInfoContentInput>;

export interface TvDisplayData {
  displayName: string;
  clinicName: string;
  branchName: string | null;
  theme: TvTheme;
  fontSize: TvFontSize;
  animationSpeed: TvAnimationSpeed;
  queueSize: number;
  refreshIntervalSeconds: number;
  logoUrl: string | null;
  primaryColor: string | null;
  secondaryColor: string | null;
  nowServing: TvDisplayNowServing[];
  nextWaiting: TvDisplayWaitingEntry[];
  announcements: TvAnnouncement[];
  infoContent: TvInfoContentItem[];
  serverTime: string;
  wsChannelClinicId: string;
  wsAuthSlug: string | null;
}
