import { platformApiFetch } from "./client";

export interface TenantUser {
  id: string;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  role: string | null;
  status: string;
  is_active: boolean;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
}

export async function listTenantUsers(clinicId: string): Promise<TenantUser[]> {
  return platformApiFetch<TenantUser[]>(`/platform-admin/tenants/${clinicId}/users`);
}

export async function listRoles(): Promise<Role[]> {
  const resp = await platformApiFetch<{ items: Role[] }>("/platform-admin/roles");
  return resp.items;
}

export interface CreateTenantUserInput {
  email: string;
  username: string;
  password: string;
  firstName: string;
  lastName: string;
  roleId: string;
}

export async function createTenantUser(clinicId: string, input: CreateTenantUserInput): Promise<TenantUser> {
  return platformApiFetch<TenantUser>(`/platform-admin/tenants/${clinicId}/users`, {
    method: "POST",
    body: {
      email: input.email,
      username: input.username,
      password: input.password,
      first_name: input.firstName,
      last_name: input.lastName,
      role_id: input.roleId,
    },
  });
}

export interface UpdateTenantUserInput {
  email?: string;
  username?: string;
  firstName?: string;
  lastName?: string;
  roleId?: string;
}

export async function updateTenantUser(
  clinicId: string,
  userId: string,
  input: UpdateTenantUserInput
): Promise<TenantUser> {
  return platformApiFetch<TenantUser>(`/platform-admin/tenants/${clinicId}/users/${userId}`, {
    method: "PATCH",
    body: {
      email: input.email,
      username: input.username,
      first_name: input.firstName,
      last_name: input.lastName,
      role_id: input.roleId,
    },
  });
}

export async function deleteTenantUser(clinicId: string, userId: string): Promise<void> {
  await platformApiFetch<void>(`/platform-admin/tenants/${clinicId}/users/${userId}`, { method: "DELETE" });
}

export async function resetTenantUserPassword(clinicId: string, userId: string, newPassword: string): Promise<void> {
  await platformApiFetch<void>(`/platform-admin/tenants/${clinicId}/users/${userId}/reset-password`, {
    method: "POST",
    body: { new_password: newPassword },
  });
}

export async function lockTenantUser(clinicId: string, userId: string): Promise<TenantUser> {
  return platformApiFetch<TenantUser>(`/platform-admin/tenants/${clinicId}/users/${userId}/lock`, { method: "POST" });
}

export async function unlockTenantUser(clinicId: string, userId: string): Promise<TenantUser> {
  return platformApiFetch<TenantUser>(`/platform-admin/tenants/${clinicId}/users/${userId}/unlock`, { method: "POST" });
}

export async function forceLogoutTenantUser(clinicId: string, userId: string): Promise<void> {
  await platformApiFetch<void>(`/platform-admin/tenants/${clinicId}/users/${userId}/force-logout`, { method: "POST" });
}
