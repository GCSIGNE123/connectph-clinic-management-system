import { apiClient, apiFetchBlob, apiUploadFile } from "@/lib/api-client";
import type { Pathologist } from "@/features/pathologists/types";

/** Round 6: Pathologist master-data CRUD + e-signature. Plain CRUD reuses
 * the generic `createCrudApi` shape by hand here (rather than importing
 * `features/clinic-config`'s factory) since the list response has no
 * `limit`/`offset` and the active-only filter is bespoke - not worth
 * forcing into that factory's `Paginated<T>` contract for one resource. */
export const pathologistsApi = {
  list: async (activeOnly = false): Promise<Pathologist[]> => {
    const qs = activeOnly ? "?activeOnly=true" : "";
    const res = await apiClient.get<{ items: Pathologist[]; total: number }>(`/pathologists${qs}`);
    return res.items;
  },
  get: (id: string): Promise<Pathologist> => apiClient.get<Pathologist>(`/pathologists/${id}`),
  create: (payload: { name: string; license_number?: string | null; is_active?: boolean }): Promise<Pathologist> =>
    apiClient.post<Pathologist>("/pathologists", payload),
  update: (
    id: string,
    payload: Partial<{ name: string; license_number: string | null; is_active: boolean }>
  ): Promise<Pathologist> => apiClient.put<Pathologist>(`/pathologists/${id}`, payload),
  remove: (id: string): Promise<void> => apiClient.delete<void>(`/pathologists/${id}`),

  uploadSignature: async (id: string, file: File): Promise<Pathologist> => {
    const formData = new FormData();
    formData.append("file", file);
    return apiUploadFile<Pathologist>(`/pathologists/${id}/signature`, formData);
  },
  removeSignature: (id: string): Promise<Pathologist> => apiClient.delete<Pathologist>(`/pathologists/${id}/signature`),
  getSignatureBlob: (id: string): Promise<Blob> => apiFetchBlob(`/pathologists/${id}/signature/file`),
};
