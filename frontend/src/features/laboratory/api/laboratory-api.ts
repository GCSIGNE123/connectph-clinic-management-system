import { apiClient } from "@/lib/api-client";
import type {
  LaboratoryAttachment,
  LaboratoryDashboardStats,
  LaboratoryOrder,
  LaboratoryResult,
  LaboratoryResultInput,
  LaboratoryTemplate,
  LaboratoryTemplateParameter,
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

  enterResults: (id: string, results: LaboratoryResultInput[]) =>
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
        })),
      })
      .then(toOrder),

  releaseResults: (id: string) => apiClient.post<any>(`/laboratory/orders/${id}/release`).then(toOrder),

  cancelOrder: (id: string) => apiClient.post<any>(`/laboratory/orders/${id}/cancel`).then(toOrder),

  addAttachment: (id: string, payload: { attachmentType: string; fileName: string; fileSizeBytes?: number }) =>
    apiClient
      .post<any>(`/laboratory/orders/${id}/attachments`, {
        attachment_type: payload.attachmentType,
        file_name: payload.fileName,
        file_size_bytes: payload.fileSizeBytes ?? null,
      })
      .then(toOrder),

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
};
