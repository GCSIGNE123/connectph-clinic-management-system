import { apiClient, apiFetchBlob, apiUploadFile } from "@/lib/api-client";
import type {
  LaboratoryAttachment,
  LaboratoryAttachmentType,
  LaboratoryDashboardStats,
  LaboratoryOrder,
  LaboratoryResult,
  LaboratoryResultInput,
  LaboratoryTemplate,
  LaboratoryTemplateDiff,
  LaboratoryTemplateImportIssue,
  LaboratoryTemplateImportPreview,
  LaboratoryTemplateImportResult,
  LaboratoryTemplateParameter,
  LaboratoryTemplateParameterDiff,
} from "@/features/laboratory/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

function toResult(raw: any): LaboratoryResult {
  return {
    id: raw.id,
    parameterName: raw.parameter_name,
    resultType: raw.result_type,
    numericValue: raw.numeric_value === null || raw.numeric_value === undefined ? null : Number(raw.numeric_value),
    textValue: raw.text_value ?? null,
    normalRange: raw.normal_range ?? null,
    units: raw.units ?? null,
    interpretation: raw.interpretation ?? null,
    remarks: raw.remarks ?? null,
    rangeLow: raw.range_low === null || raw.range_low === undefined ? null : Number(raw.range_low),
    rangeHigh: raw.range_high === null || raw.range_high === undefined ? null : Number(raw.range_high),
    enteredBy: raw.entered_by ?? null,
    enteredAt: raw.entered_at ?? null,
    structuredValue: raw.structured_value ?? null,
    site: raw.site ?? null,
  };
}

function toAttachment(raw: any): LaboratoryAttachment {
  return {
    id: raw.id,
    attachmentType: raw.attachment_type,
    fileName: raw.file_name,
    fileUrl: raw.file_url,
    fileSizeBytes: raw.file_size_bytes ?? null,
    uploadedBy: raw.uploaded_by ?? null,
    createdAt: raw.created_at,
  };
}

function toOrder(raw: any): LaboratoryOrder {
  return {
    id: raw.id,
    orderId: raw.order_id,
    orderNumber: raw.order_number ?? null,
    visitId: raw.visit_id,
    visitNumber: raw.visit_number ?? null,
    queueNumber: raw.queue_number ?? null,
    patientId: raw.patient_id,
    patientName: raw.patient_name ?? null,
    doctorId: raw.doctor_id ?? null,
    doctorName: raw.doctor_name ?? null,
    templateId: raw.template_id ?? null,
    template: raw.template ? toTemplate(raw.template) : null,
    testType: raw.test_type,
    priority: raw.priority ?? null,
    status: raw.status,
    scheduledDate: raw.scheduled_date ?? null,
    collectedAt: raw.collected_at ?? null,
    collectedBy: raw.collected_by ?? null,
    processingStartedAt: raw.processing_started_at ?? null,
    completedAt: raw.completed_at ?? null,
    releasedAt: raw.released_at ?? null,
    releasedBy: raw.released_by ?? null,
    invoiceItemId: raw.invoice_item_id ?? null,
    createdAt: raw.created_at,
    results: (raw.results ?? []).map(toResult),
    attachments: (raw.attachments ?? []).map(toAttachment),
    clinicName: raw.clinic_name ?? null,
    clinicAddress: raw.clinic_address ?? null,
    clinicPhone: raw.clinic_phone ?? null,
    clinicEmail: raw.clinic_email ?? null,
    clinicLogoUrl: raw.clinic_logo_url ?? null,
    pathologistId: raw.pathologist_id ?? null,
    medTechNameSnapshot: raw.med_tech_name_snapshot ?? null,
    medTechLicenseSnapshot: raw.med_tech_license_snapshot ?? null,
    medTechSignatureSnapshotUrl: raw.med_tech_signature_snapshot_url ?? null,
    pathologistNameSnapshot: raw.pathologist_name_snapshot ?? null,
    pathologistLicenseSnapshot: raw.pathologist_license_snapshot ?? null,
    pathologistSignatureSnapshotUrl: raw.pathologist_signature_snapshot_url ?? null,
    updatedAt: raw.updated_at,
  };
}

function toTemplateParameter(raw: any): LaboratoryTemplateParameter {
  return {
    id: raw.id,
    parameterName: raw.parameter_name,
    unit: raw.unit ?? null,
    normalRange: raw.normal_range ?? null,
    resultType: raw.result_type,
    displayOrder: raw.display_order ?? 0,
    rangeLow: raw.range_low === null || raw.range_low === undefined ? null : Number(raw.range_low),
    rangeHigh: raw.range_high === null || raw.range_high === undefined ? null : Number(raw.range_high),
    expectedNormalText: raw.expected_normal_text ?? null,
    options: raw.options ?? null,
    section: raw.section ?? null,
    requiresSite: raw.requires_site ?? false,
  };
}

function toTemplate(raw: any): LaboratoryTemplate {
  return {
    id: raw.id,
    testName: raw.test_name,
    testCategory: raw.test_category ?? null,
    specimenType: raw.specimen_type ?? null,
    defaultPrice: Number(raw.default_price ?? 0),
    turnaroundTimeHours: raw.turnaround_time_hours ?? null,
    isActive: raw.is_active,
    parameters: (raw.parameters ?? []).map(toTemplateParameter),
    createdAt: raw.created_at,
  };
}

function toDashboard(raw: any): LaboratoryDashboardStats {
  return {
    pending: raw.pending ?? 0,
    collected: raw.collected ?? 0,
    processing: raw.processing ?? 0,
    completedToday: raw.completed_today ?? 0,
    statOrders: raw.stat_orders ?? 0,
    cancelled: raw.cancelled ?? 0,
  };
}

function toImportIssue(raw: any): LaboratoryTemplateImportIssue {
  return {
    severity: raw.severity, sheet: raw.sheet, row: raw.row,
    template: raw.template ?? null, parameter: raw.parameter ?? null, reason: raw.reason,
  };
}

function toParameterDiff(raw: any): LaboratoryTemplateParameterDiff {
  return { added: raw.added ?? [], changed: raw.changed ?? [], removed: raw.removed ?? [], unchanged: raw.unchanged ?? [] };
}

function toTemplateDiff(raw: any): LaboratoryTemplateDiff {
  return { templateId: raw.template_id ?? null, testName: raw.test_name, action: raw.action, parameters: toParameterDiff(raw.parameters) };
}

function toImportPreview(raw: any): LaboratoryTemplateImportPreview {
  return {
    templateCount: raw.template_count,
    parameterCount: raw.parameter_count,
    newTemplateCount: raw.new_template_count,
    updatedTemplateCount: raw.updated_template_count,
    errors: (raw.errors ?? []).map(toImportIssue),
    warnings: (raw.warnings ?? []).map(toImportIssue),
    diffs: (raw.diffs ?? []).map(toTemplateDiff),
    canCommit: raw.can_commit,
  };
}

function toImportResult(raw: any): LaboratoryTemplateImportResult {
  return {
    createdTemplateCount: raw.created_template_count,
    updatedTemplateCount: raw.updated_template_count,
    parameterCount: raw.parameter_count,
    templateNames: raw.template_names ?? [],
  };
}

/** Triggers a browser download of a `Blob` under the given filename - the
 * same `createObjectURL` + hidden-anchor-click pattern `downloadCsv`
 * already uses in `lib/csv.ts`, just for an arbitrary Blob (the workbook
 * bytes here, rather than CSV text) since the file itself is fetched as
 * an authenticated Blob (`apiFetchBlob`), not a public URL. */
function downloadBlob(filename: string, blob: Blob): void {
  if (typeof window === "undefined") return;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function fromTemplateParameterInput(p: LaboratoryTemplateParameter) {
  return {
    parameter_name: p.parameterName,
    unit: p.unit ?? null,
    normal_range: p.normalRange ?? null,
    result_type: p.resultType,
    display_order: p.displayOrder ?? 0,
    range_low: p.rangeLow ?? null,
    range_high: p.rangeHigh ?? null,
    expected_normal_text: p.expectedNormalText ?? null,
    options: p.options ?? null,
    section: p.section ?? null,
    requires_site: p.requiresSite ?? false,
  };
}

export const laboratoryApi = {
  getDashboard: () => apiClient.get<any>("/laboratory/dashboard").then(toDashboard),

  listOrders: (visitId?: string) =>
    apiClient
      .get<any[]>(visitId ? `/laboratory/orders?visit_id=${visitId}` : "/laboratory/orders")
      .then((rows) => rows.map(toOrder)),

  getOrder: (id: string) => apiClient.get<any>(`/laboratory/orders/${id}`).then(toOrder),

  listForVisit: (visitId: string) => apiClient.get<any[]>(`/visits/${visitId}/laboratory`).then((rows) => rows.map(toOrder)),

  listForPatient: (patientId: string) => apiClient.get<any[]>(`/patients/${patientId}/laboratory`).then((rows) => rows.map(toOrder)),

  collectSpecimen: (id: string) => apiClient.post<any>(`/laboratory/orders/${id}/collect`).then(toOrder),

  startProcessing: (id: string) => apiClient.post<any>(`/laboratory/orders/${id}/start-processing`).then(toOrder),

  enterResults: (id: string, results: LaboratoryResultInput[], expectedUpdatedAt?: string | null) =>
    apiClient
      .post<any>(`/laboratory/orders/${id}/results`, {
        results: results.map((r) => ({
          parameter_name: r.parameterName,
          result_type: r.resultType,
          numeric_value: r.numericValue ?? null,
          text_value: r.textValue ?? null,
          normal_range: r.normalRange ?? null,
          units: r.units ?? null,
          interpretation: r.interpretation ?? null,
          remarks: r.remarks ?? null,
          range_low: r.rangeLow ?? null,
          range_high: r.rangeHigh ?? null,
          expected_normal_text: r.expectedNormalText ?? null,
          structured_value: r.structuredValue ?? null,
          site: r.site ?? null,
        })),
        // Phase 4I: optimistic-concurrency token - see LaboratoryOrder.updatedAt.
        expected_updated_at: expectedUpdatedAt ?? null,
      })
      .then(toOrder),

  // Round 6: Pathologist selection happens HERE, at release time - never
  // at print time. Omitting `pathologistId` preserves the pre-existing
  // release behavior (no pathologist concept at all).
  releaseResults: (id: string, pathologistId?: string | null) =>
    apiClient.post<any>(`/laboratory/orders/${id}/release`, pathologistId ? { pathologist_id: pathologistId } : {}).then(toOrder),

  getMedTechSignatureBlob: (id: string): Promise<Blob> => apiFetchBlob(`/laboratory/orders/${id}/med-tech-signature/file`),
  getPathologistSignatureBlob: (id: string): Promise<Blob> => apiFetchBlob(`/laboratory/orders/${id}/pathologist-signature/file`),

  cancelOrder: (id: string) => apiClient.post<any>(`/laboratory/orders/${id}/cancel`).then(toOrder),

  /** Feature 4: real upload - sends the actual file bytes as
   * `multipart/form-data`, so the attachment is immediately viewable
   * afterward via its returned `fileUrl`. Defaults to "Image" (the
   * primary ask: attaching the clinic's actual laboratory result image). */
  uploadAttachment: async (
    laboratoryOrderId: string,
    payload: { file: File; attachmentType?: LaboratoryAttachmentType }
  ): Promise<LaboratoryAttachment> => {
    const formData = new FormData();
    formData.append("attachment_type", payload.attachmentType ?? "Image");
    formData.append("file", payload.file);
    const raw = await apiUploadFile<any>(`/laboratory/orders/${laboratoryOrderId}/attachments`, formData);
    return toAttachment(raw);
  },

  listAttachments: async (laboratoryOrderId: string): Promise<LaboratoryAttachment[]> => {
    const raw = await apiClient.get<any[]>(`/laboratory/orders/${laboratoryOrderId}/attachments`);
    return raw.map(toAttachment);
  },

  /** Fetches an attachment's real file bytes as a Blob, for display
   * (`URL.createObjectURL`) or download - the file is served by an
   * authenticated endpoint (`fileUrl` on the attachment itself), not a
   * public URL, so a plain `<img src>` can't reach it directly. */
  getAttachmentFileBlob: (fileUrl: string): Promise<Blob> => apiFetchBlob(fileUrl),

  listTemplates: (activeOnly = false) =>
    apiClient.get<any[]>(`/laboratory/templates${activeOnly ? "?active_only=true" : ""}`).then((rows) => rows.map(toTemplate)),

  createTemplate: (payload: Omit<LaboratoryTemplate, "id" | "createdAt">) =>
    apiClient
      .post<any>("/laboratory/templates", {
        test_name: payload.testName,
        test_category: payload.testCategory,
        specimen_type: payload.specimenType,
        default_price: payload.defaultPrice,
        turnaround_time_hours: payload.turnaroundTimeHours,
        is_active: payload.isActive,
        parameters: payload.parameters.map(fromTemplateParameterInput),
      })
      .then(toTemplate),

  updateTemplate: (id: string, payload: Partial<Omit<LaboratoryTemplate, "id" | "createdAt">>) =>
    apiClient
      .patch<any>(`/laboratory/templates/${id}`, {
        ...(payload.testName !== undefined && { test_name: payload.testName }),
        ...(payload.testCategory !== undefined && { test_category: payload.testCategory }),
        ...(payload.specimenType !== undefined && { specimen_type: payload.specimenType }),
        ...(payload.defaultPrice !== undefined && { default_price: payload.defaultPrice }),
        ...(payload.turnaroundTimeHours !== undefined && { turnaround_time_hours: payload.turnaroundTimeHours }),
        ...(payload.isActive !== undefined && { is_active: payload.isActive }),
        ...(payload.parameters !== undefined && { parameters: payload.parameters.map(fromTemplateParameterInput) }),
      })
      .then(toTemplate),

  /** Downloads the current clinic's templates as an `.xlsx` workbook and
   * saves it via the browser - the backend (`GET /laboratory/templates/
   * export`) is clinic-scoped server-side, so this can never return
   * another clinic's data. */
  exportTemplates: async (): Promise<void> => {
    const blob = await apiFetchBlob("/laboratory/templates/export");
    downloadBlob(`laboratory-templates-${new Date().toISOString().slice(0, 10)}.xlsx`, blob);
  },

  downloadBlankImportTemplate: async (): Promise<void> => {
    const blob = await apiFetchBlob("/laboratory/templates/import/blank");
    downloadBlob("laboratory-templates-import-template.xlsx", blob);
  },

  /** Read-only: uploads the chosen workbook for validation and returns a
   * preview (counts, per-template +/~/- parameter diffs, errors,
   * warnings) - never writes to the database. */
  previewTemplateImport: async (file: File): Promise<LaboratoryTemplateImportPreview> => {
    const formData = new FormData();
    formData.append("file", file);
    const raw = await apiUploadFile<any>("/laboratory/templates/import/preview", formData);
    return toImportPreview(raw);
  },

  /** Re-uploads the SAME file to actually commit the import, only called
   * after the user has confirmed the preview - the backend independently
   * re-parses/re-validates rather than trusting the earlier preview. */
  commitTemplateImport: async (file: File): Promise<LaboratoryTemplateImportResult> => {
    const formData = new FormData();
    formData.append("file", file);
    const raw = await apiUploadFile<any>("/laboratory/templates/import/commit", formData);
    return toImportResult(raw);
  },
};
