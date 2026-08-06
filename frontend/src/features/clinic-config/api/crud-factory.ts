import { apiClient } from "@/lib/api-client";
import type { Paginated } from "@/features/clinic-config/types";

/**
 * Generic CRUD API factory for the Phase 4 master-data resources. Every
 * resource follows the same REST shape the backend routers expose:
 * GET (list, paginated) / GET :id / POST / PUT :id / DELETE :id / POST
 * :id/restore. See `types.ts` for the design shortcut this enables.
 */
export function createCrudApi<T extends { id: string }>(resourcePath: string) {
  return {
    async list(query: Record<string, string | number | boolean | undefined> = {}): Promise<Paginated<T>> {
      const search = new URLSearchParams();
      Object.entries(query).forEach(([key, value]) => {
        if (value !== undefined && value !== "") search.set(key, String(value));
      });
      const qs = search.toString();
      return apiClient.get<Paginated<T>>(`${resourcePath}${qs ? `?${qs}` : ""}`);
    },
    async get(id: string): Promise<T> {
      return apiClient.get<T>(`${resourcePath}/${id}`);
    },
    async create(payload: Partial<T>): Promise<T> {
      return apiClient.post<T>(resourcePath, payload);
    },
    async update(id: string, payload: Partial<T>): Promise<T> {
      return apiClient.put<T>(`${resourcePath}/${id}`, payload);
    },
    async remove(id: string): Promise<void> {
      return apiClient.delete<void>(`${resourcePath}/${id}`);
    },
    async restore(id: string): Promise<T> {
      return apiClient.post<T>(`${resourcePath}/${id}/restore`);
    },
  };
}
