export type TvTheme = "Light" | "Dark" | "ClinicBranded";
export type TvFontSize = "Small" | "Medium" | "Large" | "ExtraLarge";
export type TvAnimationSpeed = "None" | "Slow" | "Normal" | "Fast";
export type TvAnnouncementType = "Welcome" | "HealthTip" | "Promotion" | "Emergency";

export interface TvDisplayConfig {
  id: string;
  clinicId: string;
  branchId: string | null;
  departmentId: string | null;
  doctorId: string | null;
  displayName: string;
  isPublic: boolean;
  publicSlug: string | null;
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
  roomName: string | null;
  status: string;
  calledAt: string | null;
}

export interface TvDisplayWaitingEntry {
  queueId: string;
  queueNumber: string;
  patientInitials: string;
  doctorName: string | null;
  priority: string;
}

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
  serverTime: string;
  wsChannelClinicId: string;
  wsAuthSlug: string | null;
}
