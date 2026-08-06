import type { Role, UserStatus } from "@/types";

/**
 * Shape of a user record as managed via `/api/v1/users/*` (admin user CRUD).
 * Distinct from the auth `User` type (which represents "me") because the
 * backend's user-management payload exposes the full set of profile fields
 * (middle name, mobile number, username, branch, status) that the
 * lightweight `/auth/me` response does not need to carry.
 */
export interface ManagedUser {
  id: string;
  firstName: string;
  middleName?: string | null;
  lastName: string;
  email: string;
  mobileNumber: string;
  username: string;
  role: Role;
  clinicId: string;
  branchId?: string | null;
  branchName?: string | null;
  status: UserStatus;
  profilePhotoUrl?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface UserListParams {
  search?: string;
  page?: number;
  pageSize?: number;
  role?: Role;
  status?: UserStatus;
}
