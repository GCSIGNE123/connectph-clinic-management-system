/**
 * Shared types for the Phase 4 "Clinic Configuration & Master Data" feature
 * modules (branches, departments, doctors, consultation rooms, services,
 * queue settings, operating hours, holidays, clinic settings/branding).
 *
 * Design shortcut: unlike `features/patients` (which has a full
 * camelCase-domain-type + snake_case-wire-type mapping layer), these
 * lighter master-data modules use the backend's field names (snake_case)
 * directly end-to-end to keep 8 modules maintainable in one pass. TODO: if
 * these modules grow substantially, adopt the patients-style mapping layer.
 */

export interface Paginated<T> {
  items: T[];
  total: number;
  limit?: number;
  offset?: number;
}

export interface Branch {
  id: string;
  clinic_id: string;
  name: string;
  code?: string | null;
  address?: string | null;
  phone?: string | null;
  contact_number?: string | null;
  email?: string | null;
  manager_id?: string | null;
  status: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  clinic_id: string;
  department_code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Doctor {
  id: string;
  clinic_id: string;
  doctor_code: string;
  first_name: string;
  middle_name?: string | null;
  last_name: string;
  suffix?: string | null;
  prc_license?: string | null;
  ptr_number?: string | null;
  specialization?: string | null;
  department_id?: string | null;
  branch_id?: string | null;
  photo_url?: string | null;
  signature_url?: string | null;
  contact_number?: string | null;
  email?: string | null;
  consultation_fee?: string | null;
  status: "Active" | "Inactive" | "On Leave";
  created_at: string;
  updated_at: string;
}

export interface DoctorSchedule {
  id: string;
  clinic_id: string;
  doctor_id: string;
  branch_id?: string | null;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface ConsultationRoom {
  id: string;
  clinic_id: string;
  room_name: string;
  room_number?: string | null;
  department_id?: string | null;
  branch_id?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ClinicServiceItem {
  id: string;
  clinic_id: string;
  service_code: string;
  service_name: string;
  description?: string | null;
  default_price: string;
  duration_minutes?: number | null;
  department_id?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface QueueSettingItem {
  id: string;
  clinic_id: string;
  branch_id?: string | null;
  // Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): additive
  // scope columns, mirroring branch_id above - both null means the
  // clinic/branch-wide default row.
  department_id?: string | null;
  doctor_id?: string | null;
  department_name?: string | null;
  doctor_name?: string | null;
  queue_prefix: string;
  max_daily_queue: number;
  reset_time: string;
  allow_walkins: boolean;
  allow_priority_lane: boolean;
}

export interface PriorityType {
  id: string;
  clinic_id: string;
  code: string;
  label: string;
  enabled: boolean;
}

export interface OperatingHoursEntry {
  id: string;
  clinic_id: string;
  branch_id: string;
  day_of_week: number;
  opening_time?: string | null;
  closing_time?: string | null;
  lunch_break_start?: string | null;
  lunch_break_end?: string | null;
  is_closed: boolean;
}

export interface Holiday {
  id: string;
  clinic_id: string;
  holiday_name: string;
  date: string;
  is_recurring: boolean;
  is_closed: boolean;
  is_half_day: boolean;
  branch_id?: string | null;
}

export interface ClinicSettings {
  id: string;
  name: string;
  short_name?: string | null;
  address?: string | null;
  province?: string | null;
  city?: string | null;
  barangay?: string | null;
  zip_code?: string | null;
  telephone?: string | null;
  mobile?: string | null;
  email?: string | null;
  website?: string | null;
  tin?: string | null;
  license_number?: string | null;
  logo_url?: string | null;
  timezone: string;
  language: string;
  currency: string;
  date_format: string;
  time_format: string;
  status: string;
  favicon_url?: string | null;
  login_background_url?: string | null;
  primary_color?: string | null;
  secondary_color?: string | null;
  theme: string;
}

export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
