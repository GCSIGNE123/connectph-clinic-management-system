import { apiClient } from "@/lib/api-client";
import type { VaccinationAdministration, VaccinationAdministerInput } from "@/features/vaccinations/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shape */

function toVaccination(raw: any): VaccinationAdministration {
  return {
    id: raw.id,
    orderId: raw.order_id,
    visitId: raw.visit_id,
    patientId: raw.patient_id,
    patientName: raw.patient_name ?? null,
    doctorId: raw.doctor_id ?? null,
    vaccineName: raw.vaccine_name,
    status: raw.status,
    dose: raw.dose ?? null,
    lotNumber: raw.lot_number ?? null,
    site: raw.site ?? null,
    route: raw.route ?? null,
    notes: raw.notes ?? null,
    administeredAt: raw.administered_at ?? null,
    administeredBy: raw.administered_by ?? null,
    administeredByName: raw.administered_by_name ?? null,
    createdAt: raw.created_at,
  };
}

export const vaccinationsApi = {
  list: (params?: { status?: string; patientId?: string; dateFrom?: string; dateTo?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status_filter", params.status);
    if (params?.patientId) qs.set("patient_id", params.patientId);
    if (params?.dateFrom) qs.set("date_from", params.dateFrom);
    if (params?.dateTo) qs.set("date_to", params.dateTo);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiClient.get<any[]>(`/vaccinations${suffix}`).then((rows) => rows.map(toVaccination));
  },

  administer: (id: string, payload: VaccinationAdministerInput) =>
    apiClient
      .post<any>(`/vaccinations/${id}/administer`, {
        vaccine_name: payload.vaccineName || undefined,
        dose: payload.dose || undefined,
        lot_number: payload.lotNumber || undefined,
        site: payload.site || undefined,
        route: payload.route || undefined,
        notes: payload.notes || undefined,
      })
      .then(toVaccination),

  cancel: (id: string) => apiClient.post<any>(`/vaccinations/${id}/cancel`).then(toVaccination),
};
