"use client";

import { useQuery } from "@tanstack/react-query";
import { billingApi } from "@/features/billing/api/billing-api";
import { billingKeys } from "@/features/billing/hooks/use-invoice";
import type { InvoiceSearchParams } from "@/features/billing/types";

export function useInvoices(params: InvoiceSearchParams) {
  return useQuery({
    queryKey: billingKeys.list(params as Record<string, unknown>),
    queryFn: () => billingApi.listInvoices(params),
    placeholderData: (prev) => prev,
  });
}

export function useBillingHistory(
  patientId: string | null | undefined,
  params?: { dateFrom?: string; dateTo?: string }
) {
  return useQuery({
    queryKey: patientId
      ? [...billingKeys.history(patientId), params ?? {}]
      : ["billing", "history", "none"],
    queryFn: () => billingApi.getBillingHistory(patientId as string, params),
    enabled: Boolean(patientId),
  });
}
