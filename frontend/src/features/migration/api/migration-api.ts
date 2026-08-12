import { apiClient } from "@/lib/api-client";
import { tokenStorage } from "@/lib/api-client";
import { getApiBaseUrl } from "@/lib/api-url";
import type {
  MigrationBatch,
  MigrationEntityType,
  MigrationFieldMapping,
  MigrationLogEntry,
  MigrationMappingSuggestion,
  MigrationPreview,
  MigrationSourceType,
  MigrationStatusResponse,
  MigrationValidationIssue,
  MigrationVerificationReport,
} from "@/features/migration/types";

const API_URL = getApiBaseUrl();

async function uploadFiles(batchId: string, files: File[]): Promise<MigrationBatch> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const token = tokenStorage.getAccessToken();
  const res = await fetch(`${API_URL}/migration/batches/${batchId}/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: "include",
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export const migrationApi = {
  createBatch: (sourceType: MigrationSourceType, sourceDescription?: string) =>
    apiClient.post<MigrationBatch>("/migration/batches", { source_type: sourceType, source_description: sourceDescription }),

  listBatches: () => apiClient.get<MigrationBatch[]>("/migration/batches"),

  uploadFiles,

  analyze: (batchId: string) => apiClient.post<Record<string, string[]>>(`/migration/batches/${batchId}/analyze`),

  suggestMappings: (batchId: string, entityType: MigrationEntityType) =>
    apiClient.get<MigrationMappingSuggestion[]>(`/migration/batches/${batchId}/mappings/suggest?entity_type=${entityType}`),

  getMappings: (batchId: string) => apiClient.get<MigrationFieldMapping[]>(`/migration/batches/${batchId}/mappings`),

  putMappings: (batchId: string, mappings: Partial<MigrationFieldMapping>[]) =>
    apiClient.put<MigrationFieldMapping[]>(`/migration/batches/${batchId}/mappings`, { mappings }),

  validate: (batchId: string, entityType: MigrationEntityType) =>
    apiClient.post<MigrationValidationIssue[]>(`/migration/batches/${batchId}/validate?entity_type=${entityType}`),

  preview: (batchId: string, entityType: MigrationEntityType) =>
    apiClient.post<MigrationPreview>(`/migration/batches/${batchId}/preview?entity_type=${entityType}`),

  resolveIssue: (batchId: string, issueId: string, resolution: string) =>
    apiClient.patch(`/migration/batches/${batchId}/issues/${issueId}/resolve`, { resolution }),

  startImport: (batchId: string) => apiClient.post<MigrationBatch>(`/migration/batches/${batchId}/import`),

  resume: (batchId: string) => apiClient.post<MigrationBatch>(`/migration/batches/${batchId}/resume`),

  cancel: (batchId: string) => apiClient.post<MigrationBatch>(`/migration/batches/${batchId}/cancel`),

  retryEntity: (batchId: string, entityType: MigrationEntityType) =>
    apiClient.post(`/migration/batches/${batchId}/retry-batch?entity_type=${entityType}`),

  getStatus: (batchId: string) => apiClient.get<MigrationStatusResponse>(`/migration/batches/${batchId}/status`),

  verify: (batchId: string) => apiClient.get<MigrationVerificationReport>(`/migration/batches/${batchId}/verify`),

  getLogs: (batchId: string) => apiClient.get<MigrationLogEntry[]>(`/migration/batches/${batchId}/logs`),
};
