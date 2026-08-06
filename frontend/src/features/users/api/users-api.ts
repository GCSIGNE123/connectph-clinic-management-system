import { apiClient } from "@/lib/api-client";
import type { PaginatedResponse, Role } from "@/types";
import type { ManagedUser, UserListParams } from "@/features/users/types";
import type {
  AdminResetPasswordInput,
  CreateUserInput,
  EditUserInput,
} from "@/features/users/schemas/users-schemas";

/** Raw shape of a user record as returned by `/api/v1/users/*` (snake_case). */
interface RawManagedUser {
  id: string;
  email: string;
  username: string;
  first_name: string;
  middle_name?: string | null;
  last_name: string;
  mobile_number?: string | null;
  clinic_id: string;
  role_id: string;
  role_name: string | null;
  branch_id?: string | null;
  profile_photo?: string | null;
  is_active: boolean;
  is_email_verified: boolean;
  status: string;
  created_at: string;
  updated_at: string;
}

interface RawUserListResponse {
  items: RawManagedUser[];
  total: number;
  limit: number;
  offset: number;
}

function toManagedUser(raw: RawManagedUser): ManagedUser {
  return {
    id: raw.id,
    firstName: raw.first_name,
    middleName: raw.middle_name,
    lastName: raw.last_name,
    email: raw.email,
    mobileNumber: raw.mobile_number ?? "",
    username: raw.username,
    role: (raw.role_name ?? "Viewer") as Role,
    clinicId: raw.clinic_id,
    branchId: raw.branch_id,
    branchName: null,
    status: raw.status as ManagedUser["status"],
    profilePhotoUrl: raw.profile_photo,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toQueryString(params: UserListParams): string {
  const search = new URLSearchParams();
  if (params.search) search.set("q", params.search);
  if (params.page && params.pageSize) search.set("offset", String((params.page - 1) * params.pageSize));
  if (params.pageSize) search.set("limit", String(params.pageSize));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

/** `/api/v1/roles` - read-only list of the fixed platform roles, used to
 * resolve a `role_id` for user create/update forms. */
export const rolesApi = {
  async list(): Promise<{ id: string; name: string; description: string | null }[]> {
    const raw = await apiClient.get<{ items: { id: string; name: string; description: string | null }[] }>(
      "/roles"
    );
    return raw.items;
  },
};

/**
 * `/api/v1/users/*` bindings for admin user management (list/search,
 * create, edit, disable, enable, admin password reset). The backend returns
 * bodies directly (no envelope) and expects `role_id` (not a role name) on
 * writes, so callers must resolve the id via `rolesApi.list()` first.
 */
export const usersApi = {
  async list(params: UserListParams): Promise<PaginatedResponse<ManagedUser>> {
    const raw = await apiClient.get<RawUserListResponse>(`/users${toQueryString(params)}`);
    const pageSize = raw.limit || 1;
    return {
      data: raw.items.map(toManagedUser),
      meta: {
        page: Math.floor(raw.offset / pageSize) + 1,
        pageSize: raw.limit,
        total: raw.total,
        totalPages: Math.max(1, Math.ceil(raw.total / pageSize)),
      },
    };
  },

  async get(id: string): Promise<ManagedUser> {
    const raw = await apiClient.get<RawManagedUser>(`/users/${id}`);
    return toManagedUser(raw);
  },

  async create(input: CreateUserInput & { roleId: string }): Promise<ManagedUser> {
    const raw = await apiClient.post<RawManagedUser>("/users", {
      first_name: input.firstName,
      middle_name: input.middleName || null,
      last_name: input.lastName,
      email: input.email,
      mobile_number: input.mobileNumber,
      username: input.username,
      role_id: input.roleId,
      branch_id: input.branchId || null,
      password: input.password,
    });
    return toManagedUser(raw);
  },

  async update(id: string, input: EditUserInput & { roleId?: string }): Promise<ManagedUser> {
    const raw = await apiClient.patch<RawManagedUser>(`/users/${id}`, {
      first_name: input.firstName,
      middle_name: input.middleName || null,
      last_name: input.lastName,
      mobile_number: input.mobileNumber,
      role_id: input.roleId,
      branch_id: input.branchId || null,
    });
    return toManagedUser(raw);
  },

  async disable(id: string): Promise<void> {
    await apiClient.post<RawManagedUser>(`/users/${id}/disable`);
  },

  async enable(id: string): Promise<void> {
    await apiClient.post<RawManagedUser>(`/users/${id}/enable`);
  },

  async adminResetPassword(id: string, input: AdminResetPasswordInput): Promise<void> {
    await apiClient.post<{ detail: string }>(`/users/${id}/reset-password`, {
      new_password: input.newPassword,
    });
  },
};
