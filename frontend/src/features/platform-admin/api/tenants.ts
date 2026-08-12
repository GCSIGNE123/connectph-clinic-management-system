import { platformApiFetch } from "./client";

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  email: string | null;
  status: string;
  suspended_at: string | null;
  suspended_reason: string | null;
  archived_at: string | null;
  created_at: string;
}

export interface TenantListResponse {
  items: Tenant[];
  total: number;
  page: number;
  page_size: number;
}

export interface SystemHealth {
  total_clinics: number;
  active_clinics: number;
  suspended_clinics: number;
  trial_subscriptions: number;
  expired_subscriptions: number;
  online_users: number;
  database_size_bytes: number;
  background_jobs_total: number;
  background_jobs_failed: number;
  api_requests_today: number | null;
}

export async function listTenants(params: { search?: string; status?: string } = {}): Promise<TenantListResponse> {
  const qs = new URLSearchParams();
  if (params.search) qs.set("search", params.search);
  if (params.status) qs.set("status", params.status);
  qs.set("page_size", "100");
  return platformApiFetch<TenantListResponse>(`/platform-admin/tenants?${qs.toString()}`);
}

export interface CreateTenantInput {
  name: string;
  slug: string;
  email?: string;
  ownerEmail: string;
  ownerUsername: string;
  ownerPassword: string;
  ownerFirstName: string;
  ownerLastName: string;
}

export async function createTenant(input: CreateTenantInput): Promise<Tenant> {
  return platformApiFetch<Tenant>("/platform-admin/tenants", {
    method: "POST",
    body: {
      name: input.name,
      slug: input.slug,
      email: input.email || null,
      owner_email: input.ownerEmail,
      owner_username: input.ownerUsername,
      owner_password: input.ownerPassword,
      owner_first_name: input.ownerFirstName,
      owner_last_name: input.ownerLastName,
    },
  });
}

export interface UpdateTenantInput {
  name?: string;
  slug?: string;
  email?: string;
}

export async function updateTenant(clinicId: string, input: UpdateTenantInput): Promise<Tenant> {
  return platformApiFetch<Tenant>(`/platform-admin/tenants/${clinicId}`, {
    method: "PATCH",
    body: { name: input.name, slug: input.slug, email: input.email },
  });
}

export async function deleteTenant(clinicId: string): Promise<void> {
  await platformApiFetch<void>(`/platform-admin/tenants/${clinicId}`, { method: "DELETE" });
}

export async function suspendTenant(clinicId: string, reason: string): Promise<Tenant> {
  return platformApiFetch<Tenant>(`/platform-admin/tenants/${clinicId}/suspend`, {
    method: "POST",
    body: { reason },
  });
}

export async function reactivateTenant(clinicId: string): Promise<Tenant> {
  return platformApiFetch<Tenant>(`/platform-admin/tenants/${clinicId}/reactivate`, { method: "POST" });
}

export async function archiveTenant(clinicId: string): Promise<Tenant> {
  return platformApiFetch<Tenant>(`/platform-admin/tenants/${clinicId}/archive`, { method: "POST" });
}

export async function getSystemHealth(): Promise<SystemHealth> {
  return platformApiFetch<SystemHealth>("/platform-admin/dashboard/health");
}

export interface FeatureFlag {
  feature_key: string;
  is_enabled: boolean;
}

export async function listFeatureFlags(clinicId: string): Promise<FeatureFlag[]> {
  return platformApiFetch<FeatureFlag[]>(`/platform-admin/tenants/${clinicId}/feature-flags`);
}

export async function setFeatureFlag(clinicId: string, featureKey: string, isEnabled: boolean): Promise<FeatureFlag> {
  return platformApiFetch<FeatureFlag>(`/platform-admin/tenants/${clinicId}/feature-flags`, {
    method: "PUT",
    body: { feature_key: featureKey, is_enabled: isEnabled },
  });
}

/** Pure, unit-testable client-side tenant search/filter helper (used by the
 * Tenant Management page's local filtering in addition to the server-side
 * `search`/`status` query params). */
export function filterTenants(tenants: Tenant[], query: string): Tenant[] {
  const q = query.trim().toLowerCase();
  if (!q) return tenants;
  return tenants.filter(
    (t) =>
      t.name.toLowerCase().includes(q) ||
      t.slug.toLowerCase().includes(q) ||
      (t.email ?? "").toLowerCase().includes(q)
  );
}

/** Pure toggle-state helper for the Feature Flags grid. */
export function toggleFlag(flags: FeatureFlag[], featureKey: string): FeatureFlag[] {
  return flags.map((f) => (f.feature_key === featureKey ? { ...f, is_enabled: !f.is_enabled } : f));
}
