import { apiClient } from "@/lib/api-client";
import type {
  Order, OrderCategory, OrderItemInput, OrderPriority, OrderStatus,
  Prescription, PrescriptionItemInput,
  Procedure, Referral,
} from "@/features/clinical-orders/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

function toOrderItem(raw: any) {
  return {
    id: raw.id, itemName: raw.item_name, itemCategory: raw.item_category,
    examType: raw.exam_type, bodyPart: raw.body_part, clinicalIndication: raw.clinical_indication,
  };
}

function toOrder(raw: any): Order {
  return {
    id: raw.id, consultationId: raw.consultation_id, visitId: raw.visit_id, patientId: raw.patient_id,
    doctorId: raw.doctor_id, orderNumber: raw.order_number, orderCategory: raw.order_category,
    priority: raw.priority, scheduledDate: raw.scheduled_date, clinicalNotes: raw.clinical_notes,
    status: raw.status, createdAt: raw.created_at, items: (raw.items ?? []).map(toOrderItem),
  };
}

function toProcedure(raw: any): Procedure {
  return {
    id: raw.id, consultationId: raw.consultation_id, visitId: raw.visit_id, doctorId: raw.doctor_id,
    procedureName: raw.procedure_name, procedureDate: raw.procedure_date, notes: raw.notes,
    status: raw.status, createdAt: raw.created_at,
  };
}

function toReferral(raw: any): Referral {
  return {
    id: raw.id, consultationId: raw.consultation_id, visitId: raw.visit_id, doctorId: raw.doctor_id,
    referredTo: raw.referred_to, reason: raw.reason, notes: raw.notes,
    status: raw.status, createdAt: raw.created_at,
  };
}

function toPrescriptionItem(raw: any) {
  return {
    id: raw.id, medicine: raw.medicine, genericName: raw.generic_name, brandName: raw.brand_name,
    strength: raw.strength, dosage: raw.dosage, frequency: raw.frequency, duration: raw.duration,
    quantity: raw.quantity, route: raw.route, instructions: raw.instructions,
    substitutionAllowed: raw.substitution_allowed,
  };
}

function toPrescription(raw: any): Prescription {
  return {
    id: raw.id, consultationId: raw.consultation_id, visitId: raw.visit_id, patientId: raw.patient_id,
    doctorId: raw.doctor_id, prescriptionNumber: raw.prescription_number, status: raw.status,
    createdAt: raw.created_at, items: (raw.items ?? []).map(toPrescriptionItem),
  };
}

function fromOrderItemInput(item: OrderItemInput) {
  return {
    item_name: item.itemName, item_category: item.itemCategory ?? null,
    exam_type: item.examType ?? null, body_part: item.bodyPart ?? null,
    clinical_indication: item.clinicalIndication ?? null,
  };
}

function fromPrescriptionItemInput(item: PrescriptionItemInput) {
  return {
    medicine: item.medicine, generic_name: item.genericName ?? null, brand_name: item.brandName ?? null,
    strength: item.strength ?? null, dosage: item.dosage ?? null, frequency: item.frequency ?? null,
    duration: item.duration ?? null, quantity: item.quantity ?? null, route: item.route ?? null,
    instructions: item.instructions ?? null, substitution_allowed: item.substitutionAllowed,
  };
}

export const clinicalOrdersApi = {
  createOrder: async (
    consultationId: string,
    payload: { orderCategory: OrderCategory; priority: OrderPriority; scheduledDate?: string | null; clinicalNotes?: string | null; items: OrderItemInput[] }
  ): Promise<Order> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/orders`, {
      order_category: payload.orderCategory, priority: payload.priority,
      scheduled_date: payload.scheduledDate ?? null, clinical_notes: payload.clinicalNotes ?? null,
      items: payload.items.map(fromOrderItemInput),
    });
    return toOrder(raw);
  },
  listOrdersForConsultation: async (consultationId: string): Promise<Order[]> => {
    const raw = await apiClient.get<any[]>(`/consultations/${consultationId}/orders`);
    return raw.map(toOrder);
  },
  listOrdersForVisit: async (visitId: string): Promise<Order[]> => {
    const raw = await apiClient.get<any[]>(`/visits/${visitId}/orders`);
    return raw.map(toOrder);
  },
  updateOrderStatus: async (orderId: string, status: OrderStatus): Promise<Order> => {
    const raw = await apiClient.patch<any>(`/orders/${orderId}/status`, { status });
    return toOrder(raw);
  },

  createProcedure: async (consultationId: string, payload: { procedureName: string; procedureDate?: string | null; notes?: string | null }): Promise<Procedure> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/procedures`, {
      procedure_name: payload.procedureName, procedure_date: payload.procedureDate ?? null, notes: payload.notes ?? null,
    });
    return toProcedure(raw);
  },
  listProceduresForConsultation: async (consultationId: string): Promise<Procedure[]> => {
    const raw = await apiClient.get<any[]>(`/consultations/${consultationId}/procedures`);
    return raw.map(toProcedure);
  },
  listProceduresForVisit: async (visitId: string): Promise<Procedure[]> => {
    const raw = await apiClient.get<any[]>(`/visits/${visitId}/procedures`);
    return raw.map(toProcedure);
  },

  createReferral: async (consultationId: string, payload: { referredTo: string; reason?: string | null; notes?: string | null }): Promise<Referral> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/referrals`, {
      referred_to: payload.referredTo, reason: payload.reason ?? null, notes: payload.notes ?? null,
    });
    return toReferral(raw);
  },
  listReferralsForConsultation: async (consultationId: string): Promise<Referral[]> => {
    const raw = await apiClient.get<any[]>(`/consultations/${consultationId}/referrals`);
    return raw.map(toReferral);
  },
  listReferralsForVisit: async (visitId: string): Promise<Referral[]> => {
    const raw = await apiClient.get<any[]>(`/visits/${visitId}/referrals`);
    return raw.map(toReferral);
  },

  createPrescription: async (consultationId: string, items: PrescriptionItemInput[]): Promise<{ prescription: Prescription; warnings: string[] }> => {
    const raw = await apiClient.post<any>(`/consultations/${consultationId}/prescriptions`, {
      items: items.map(fromPrescriptionItemInput),
    });
    return { prescription: toPrescription(raw.prescription), warnings: raw.warnings ?? [] };
  },
  listPrescriptionsForConsultation: async (consultationId: string): Promise<Prescription[]> => {
    const raw = await apiClient.get<any[]>(`/consultations/${consultationId}/prescriptions`);
    return raw.map(toPrescription);
  },
  listPrescriptionsForVisit: async (visitId: string): Promise<Prescription[]> => {
    const raw = await apiClient.get<any[]>(`/visits/${visitId}/prescriptions`);
    return raw.map(toPrescription);
  },
  listPrescriptionsForPatient: async (patientId: string): Promise<Prescription[]> => {
    const raw = await apiClient.get<any[]>(`/patients/${patientId}/prescriptions`);
    return raw.map(toPrescription);
  },
};
