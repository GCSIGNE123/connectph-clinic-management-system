"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clinicalOrdersApi } from "@/features/clinical-orders/api/clinical-orders-api";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type {
  OrderCategory, OrderItemInput, OrderPriority, OrderStatus,
  PrescriptionItemInput,
} from "@/features/clinical-orders/types";

/** Query-key convention mirrors `features/consultation/hooks/use-consultation.ts`
 * (`consultationKeys`) - a distinct key per (consultation) and per (visit),
 * so every mutation below invalidates BOTH the consultation-scoped list the
 * Consultation page's Orders/Prescription tabs read from AND the
 * visit-scoped list the Visit Details page's read-only tabs read from. This
 * directly applies the Phase 8 lesson documented in that file: writing to
 * only one cache key leaves the other screen silently stale. */
export const clinicalOrdersKeys = {
  ordersForConsultation: (consultationId: string) => ["clinical-orders", "orders", "consultation", consultationId] as const,
  ordersForVisit: (visitId: string) => ["clinical-orders", "orders", "visit", visitId] as const,
  proceduresForConsultation: (consultationId: string) => ["clinical-orders", "procedures", "consultation", consultationId] as const,
  proceduresForVisit: (visitId: string) => ["clinical-orders", "procedures", "visit", visitId] as const,
  referralsForConsultation: (consultationId: string) => ["clinical-orders", "referrals", "consultation", consultationId] as const,
  referralsForVisit: (visitId: string) => ["clinical-orders", "referrals", "visit", visitId] as const,
  prescriptionsForConsultation: (consultationId: string) => ["clinical-orders", "prescriptions", "consultation", consultationId] as const,
  prescriptionsForVisit: (visitId: string) => ["clinical-orders", "prescriptions", "visit", visitId] as const,
  prescriptionsForPatient: (patientId: string) => ["clinical-orders", "prescriptions", "patient", patientId] as const,
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

// --- Orders ---

export function useOrdersForConsultation(consultationId: string | null | undefined) {
  return useQuery({
    queryKey: consultationId ? clinicalOrdersKeys.ordersForConsultation(consultationId) : ["clinical-orders", "orders", "none"],
    queryFn: () => clinicalOrdersApi.listOrdersForConsultation(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

export function useOrdersForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? clinicalOrdersKeys.ordersForVisit(visitId) : ["clinical-orders", "orders", "none"],
    queryFn: () => clinicalOrdersApi.listOrdersForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

export function useCreateOrder(consultationId: string, visitId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { orderCategory: OrderCategory; priority: OrderPriority; scheduledDate?: string | null; clinicalNotes?: string | null; items: OrderItemInput[] }) =>
      clinicalOrdersApi.createOrder(consultationId, payload),
    onSuccess: () => {
      toast({ title: "Order created", variant: "success" });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.ordersForConsultation(consultationId) });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.ordersForVisit(visitId) });
      // The Timeline tab reads `visit.timeline` from useVisit() (visitKeys.detail),
      // a completely different cache entry than the ones above - without this,
      // "Order created" timeline events never appeared until a full reload.
      queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
    },
    onError: (error) => toast({ title: "Could not create order", description: errorMessage(error), variant: "error" }),
  });
}

export function useUpdateOrderStatus(consultationId: string, visitId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, status }: { orderId: string; status: OrderStatus }) => clinicalOrdersApi.updateOrderStatus(orderId, status),
    onSuccess: () => {
      toast({ title: "Order status updated", variant: "success" });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.ordersForConsultation(consultationId) });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.ordersForVisit(visitId) });
      queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
    },
    onError: (error) => toast({ title: "Could not update order status", description: errorMessage(error), variant: "error" }),
  });
}

// --- Procedures ---

export function useProceduresForConsultation(consultationId: string | null | undefined) {
  return useQuery({
    queryKey: consultationId ? clinicalOrdersKeys.proceduresForConsultation(consultationId) : ["clinical-orders", "procedures", "none"],
    queryFn: () => clinicalOrdersApi.listProceduresForConsultation(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

export function useProceduresForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? clinicalOrdersKeys.proceduresForVisit(visitId) : ["clinical-orders", "procedures", "none"],
    queryFn: () => clinicalOrdersApi.listProceduresForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

export function useCreateProcedure(consultationId: string, visitId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { procedureName: string; procedureDate?: string | null; notes?: string | null }) =>
      clinicalOrdersApi.createProcedure(consultationId, payload),
    onSuccess: () => {
      toast({ title: "Procedure recorded", variant: "success" });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.proceduresForConsultation(consultationId) });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.proceduresForVisit(visitId) });
      queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
    },
    onError: (error) => toast({ title: "Could not record procedure", description: errorMessage(error), variant: "error" }),
  });
}

// --- Referrals ---

export function useReferralsForConsultation(consultationId: string | null | undefined) {
  return useQuery({
    queryKey: consultationId ? clinicalOrdersKeys.referralsForConsultation(consultationId) : ["clinical-orders", "referrals", "none"],
    queryFn: () => clinicalOrdersApi.listReferralsForConsultation(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

export function useReferralsForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? clinicalOrdersKeys.referralsForVisit(visitId) : ["clinical-orders", "referrals", "none"],
    queryFn: () => clinicalOrdersApi.listReferralsForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

export function useCreateReferral(consultationId: string, visitId: string) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { referredTo: string; reason?: string | null; notes?: string | null }) =>
      clinicalOrdersApi.createReferral(consultationId, payload),
    onSuccess: () => {
      toast({ title: "Referral created", variant: "success" });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.referralsForConsultation(consultationId) });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.referralsForVisit(visitId) });
      queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
    },
    onError: (error) => toast({ title: "Could not create referral", description: errorMessage(error), variant: "error" }),
  });
}

// --- Prescriptions ---

export function usePrescriptionsForConsultation(consultationId: string | null | undefined) {
  return useQuery({
    queryKey: consultationId ? clinicalOrdersKeys.prescriptionsForConsultation(consultationId) : ["clinical-orders", "prescriptions", "none"],
    queryFn: () => clinicalOrdersApi.listPrescriptionsForConsultation(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

export function usePrescriptionsForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? clinicalOrdersKeys.prescriptionsForVisit(visitId) : ["clinical-orders", "prescriptions", "none"],
    queryFn: () => clinicalOrdersApi.listPrescriptionsForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

export function usePrescriptionsForPatient(patientId: string | null | undefined) {
  return useQuery({
    queryKey: patientId ? clinicalOrdersKeys.prescriptionsForPatient(patientId) : ["clinical-orders", "prescriptions", "none"],
    queryFn: () => clinicalOrdersApi.listPrescriptionsForPatient(patientId as string),
    enabled: Boolean(patientId),
  });
}

export function useCreatePrescription(consultationId: string, visitId: string, patientId?: string | null) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (items: PrescriptionItemInput[]) => clinicalOrdersApi.createPrescription(consultationId, items),
    onSuccess: ({ warnings }) => {
      if (warnings.length > 0) {
        toast({ title: "Prescription saved with warnings", description: warnings.join(" "), variant: "default" });
      } else {
        toast({ title: "Prescription saved", variant: "success" });
      }
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.prescriptionsForConsultation(consultationId) });
      queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.prescriptionsForVisit(visitId) });
      if (patientId) queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.prescriptionsForPatient(patientId) });
      queryClient.invalidateQueries({ queryKey: visitKeys.detail(visitId) });
    },
    onError: (error) => toast({ title: "Could not save prescription", description: errorMessage(error), variant: "error" }),
  });
}
