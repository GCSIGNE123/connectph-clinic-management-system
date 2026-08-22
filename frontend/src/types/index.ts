/**
 * Core domain types shared across the CONNECT.PH Clinic Platform frontend.
 * These are foundation types only (auth/session/tenancy shell) - business
 * feature types (patients, appointments, billing, etc.) are intentionally
 * out of scope for this iteration.
 */

/** Roles matching the backend authorization model. */
export enum Role {
  Owner = "Owner",
  Administrator = "Administrator",
  Receptionist = "Receptionist",
  Doctor = "Doctor",
  Nurse = "Nurse",
  Cashier = "Cashier",
  Laboratory = "Laboratory",
  Pharmacy = "Pharmacy",
  Viewer = "Viewer",
}

export interface Clinic {
  id: string;
  name: string;
  slug: string;
  logoUrl?: string | null;
  timezone: string;
  createdAt: string;
}

export interface Branch {
  id: string;
  clinicId: string;
  name: string;
}

/** Account status, matching the backend `status` enum for user records. */
export enum UserStatus {
  Active = "active",
  Disabled = "disabled",
  Locked = "locked",
}

export interface User {
  id: string;
  email: string;
  firstName: string;
  middleName?: string | null;
  lastName: string;
  mobileNumber?: string | null;
  role: Role;
  clinicId: string;
  clinic?: Clinic;
  branchId?: string | null;
  branch?: Branch | null;
  avatarUrl?: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  // Round 6 (Laboratory Report Signatories): a Laboratory-role user's own
  // professional license/registration number + whether they have an
  // e-signature configured (fetched via `/auth/me/signature/file`, never
  // exposed as a raw filename here).
  licenseNumber?: string | null;
  hasSignature?: boolean;
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  /** Unix epoch (ms) when the access token expires. */
  expiresAt: number;
}

export interface AuthSession {
  user: User;
  tokens: AuthTokens;
}

/**
 * The backend does NOT wrap successful responses in a `{ data }` envelope -
 * it returns the resource body directly. `ApiResponse<T>` is kept as a
 * type-level identity alias (rather than removed) so existing call sites
 * that reference it keep compiling; it no longer implies an actual `.data`
 * unwrap at runtime. See `lib/api-client.ts` and `features/auth/api/auth-api.ts`.
 */
export type ApiResponse<T> = T;

/** Generic API error envelope returned by the backend. */
export interface ApiErrorResponse {
  message: string;
  errors?: Record<string, string[]>;
  statusCode: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
  };
}

/** Navigation item used by the dashboard sidebar. `icon` is typed loosely
 * (not `ComponentType`) here because this shared type doesn't depend on
 * React; call sites that render icons intersect with a stricter local type
 * (see `components/layout/Sidebar.tsx`). */
export interface NavItem {
  label: string;
  href: string;
  icon?: unknown;
  roles?: Role[];
}
