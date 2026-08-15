"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { laboratoryApi } from "@/features/laboratory/api/laboratory-api";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import { clinicalOrdersKeys } from "@/features/clinical-orders/hooks/use-clinical-orders";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { LaboratoryAttachmentType, LaboratoryOrder, LaboratoryResultInput, LaboratoryTemplate } from "@/features/laboratory/types";

/**
 * Query-key convention (mirrors `clinicalOrdersKeys`/`billingKeys` - see
 * their doc-comments for the Phase 8/9 cache-key lesson this directly
 * applies): a laboratory order's status/results are read from FIVE
 * different places - the Laboratory Dashboard's worklist, the Consultation
 * page's Orders tab (via `clinicalOrdersKeys`, since the underlying Phase 9
 * Order.status is also synced), the Visit Details page's Laboratory tab,
 * the Visit's Timeline tab (`visitKeys.detail`), and the Patient's
 * Laboratory history tab. Every mutation below invalidates ALL of them,
 * not just the one screen it was triggered from.
 */
export const laboratoryKeys = {
  dashboard: () => ["laboratory", "dashboard"] as const,
  dashboardOrders: () => ["laboratory", "orders", "dashboard"] as const,
  order: (id: string) => ["laboratory", "orders", "detail", id] as const,
  forVisit: (visitId: string) => ["laboratory", "orders", "visit", visitId] as const,
  forPatient: (patientId: string) => ["laboratory", "orders", "patient", patientId] as const,
  templates: (activeOnly: boolean) => ["laboratory", "templates", activeOnly] as const,
  attachments: (orderId: string) => ["laboratory", "orders", "attachments", orderId] as const,
};

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export function useLaboratoryDashboard() {
  return useQuery({
    queryKey: laboratoryKeys.dashboard(),
    queryFn: laboratoryApi.getDashboard,
    refetchInterval: 30_000,
  });
}

export function useLaboratoryWorklist() {
  return useQuery({
    queryKey: laboratoryKeys.dashboardOrders(),
    queryFn: () => laboratoryApi.listOrders(),
    refetchInterval: 30_000,
  });
}

export function useLaboratoryOrder(id: string | null | undefined) {
  return useQuery({
    queryKey: id ? laboratoryKeys.order(id) : ["laboratory", "orders", "detail", "none"],
    queryFn: () => laboratoryApi.getOrder(id as string),
    enabled: Boolean(id),
  });
}

export function useLaboratoryForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? laboratoryKeys.forVisit(visitId) : ["laboratory", "orders", "visit", "none"],
    queryFn: () => laboratoryApi.listForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

export function useLaboratoryForPatient(patientId: string | null | undefined) {
  return useQuery({
    queryKey: patientId ? laboratoryKeys.forPatient(patientId) : ["laboratory", "orders", "patient", "none"],
    queryFn: () => laboratoryApi.listForPatient(patientId as string),
    enabled: Boolean(patientId),
  });
}

function useInvalidateAllLabViews() {
  const queryClient = useQueryClient();
  return (order: LaboratoryOrder) => {
    queryClient.invalidateQueries({ queryKey: laboratoryKeys.dashboard() });
    queryClient.invalidateQueries({ queryKey: laboratoryKeys.dashboardOrders() });
    queryClient.invalidateQueries({ queryKey: laboratoryKeys.order(order.id) });
    queryClient.invalidateQueries({ queryKey: laboratoryKeys.forVisit(order.visitId) });
    queryClient.invalidateQueries({ queryKey: laboratoryKeys.forPatient(order.patientId) });
    queryClient.invalidateQueries({ queryKey: visitKeys.detail(order.visitId) });
    queryClient.invalidateQueries({ queryKey: clinicalOrdersKeys.ordersForVisit(order.visitId) });
  };
}

export function useCollectSpecimen() {
  const { toast } = useToast();
  const invalidateAll = useInvalidateAllLabViews();
  return useMutation({
    mutationFn: (id: string) => laboratoryApi.collectSpecimen(id),
    onSuccess: (order) => {
      invalidateAll(order);
      toast({ title: "Specimen collected", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not collect specimen", description: errorMessage(error), variant: "error" }),
  });
}

export function useStartProcessing() {
  const { toast } = useToast();
  const invalidateAll = useInvalidateAllLabViews();
  return useMutation({
    mutationFn: (id: string) => laboratoryApi.startProcessing(id),
    onSuccess: (order) => {
      invalidateAll(order);
      toast({ title: "Processing started", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not start processing", description: errorMessage(error), variant: "error" }),
  });
}

export function useEnterResults() {
  const { toast } = useToast();
  const invalidateAll = useInvalidateAllLabViews();
  return useMutation({
    mutationFn: ({ id, results }: { id: string; results: LaboratoryResultInput[] }) => laboratoryApi.enterResults(id, results),
    onSuccess: (order) => {
      invalidateAll(order);
      toast({ title: "Results saved", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not save results", description: errorMessage(error), variant: "error" }),
  });
}

export function useReleaseResults() {
  const { toast } = useToast();
  const invalidateAll = useInvalidateAllLabViews();
  return useMutation({
    mutationFn: (id: string) => laboratoryApi.releaseResults(id),
    onSuccess: (order) => {
      invalidateAll(order);
      toast({ title: "Results released", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not release results", description: errorMessage(error), variant: "error" }),
  });
}

export function useCancelLaboratoryOrder() {
  const { toast } = useToast();
  const invalidateAll = useInvalidateAllLabViews();
  return useMutation({
    mutationFn: (id: string) => laboratoryApi.cancelOrder(id),
    onSuccess: (order) => {
      invalidateAll(order);
      toast({ title: "Laboratory order cancelled", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not cancel order", description: errorMessage(error), variant: "error" }),
  });
}

// --- Templates ---

export function useLaboratoryTemplates(activeOnly = false) {
  return useQuery({
    queryKey: laboratoryKeys.templates(activeOnly),
    queryFn: () => laboratoryApi.listTemplates(activeOnly),
  });
}

export function useCreateLaboratoryTemplate() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Omit<LaboratoryTemplate, "id" | "createdAt">) => laboratoryApi.createTemplate(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["laboratory", "templates"] });
      toast({ title: "Test template created", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not create template", description: errorMessage(error), variant: "error" }),
  });
}

export function useUpdateLaboratoryTemplate() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<LaboratoryTemplate, "id" | "createdAt">> }) =>
      laboratoryApi.updateTemplate(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["laboratory", "templates"] });
      toast({ title: "Test template updated", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not update template", description: errorMessage(error), variant: "error" }),
  });
}

// --- Feature 4: Attachments ---
// Dedicated query, independent of whatever (possibly stale, 30s-refetch)
// `LaboratoryOrder` object the caller was handed as a prop - the Result
// Entry dialog reads attachments from this query directly, so "refresh the
// attachment list immediately after upload" only depends on invalidating
// this one key, not on the parent worklist's own refetch timing.

export function useLaboratoryAttachments(laboratoryOrderId: string | null | undefined) {
  return useQuery({
    queryKey: laboratoryOrderId ? laboratoryKeys.attachments(laboratoryOrderId) : ["laboratory", "orders", "attachments", "none"],
    queryFn: () => laboratoryApi.listAttachments(laboratoryOrderId as string),
    enabled: Boolean(laboratoryOrderId),
  });
}

export function useUploadLaboratoryAttachment(laboratoryOrderId: string | null | undefined) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { file: File; attachmentType?: LaboratoryAttachmentType }) => {
      if (!laboratoryOrderId) throw new Error("No laboratory order selected");
      return laboratoryApi.uploadAttachment(laboratoryOrderId, payload);
    },
    onSuccess: () => {
      toast({ title: "Image uploaded", variant: "success" });
      if (laboratoryOrderId) {
        queryClient.invalidateQueries({ queryKey: laboratoryKeys.attachments(laboratoryOrderId) });
        queryClient.invalidateQueries({ queryKey: laboratoryKeys.order(laboratoryOrderId) });
      }
    },
    onError: (error) => toast({ title: "Upload failed", description: errorMessage(error), variant: "error" }),
  });
}
