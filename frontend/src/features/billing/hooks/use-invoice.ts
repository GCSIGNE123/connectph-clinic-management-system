"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { billingApi } from "@/features/billing/api/billing-api";
import type { Invoice } from "@/features/billing/types";

/**
 * Query keys: every mutation hook in this feature (`use-invoice-mutations.ts`,
 * `use-payments.ts`) writes its result back to BOTH `detail(id)` and
 * `forVisit(visitId)` - the two places an Invoice can be read from (Invoice
 * Details page reads `detail`, Visit Details "Billing" tab reads
 * `forVisit`). This mirrors the exact cache-key mistake documented in
 * `docs/TESTING.md`'s Phase 8 section (mutations only wrote to one of two
 * keys the UI actually read from) - deliberately avoided here.
 */
export const billingKeys = {
  all: ["billing"] as const,
  detail: (invoiceId: string) => ["billing", "invoice", "detail", invoiceId] as const,
  forVisit: (visitId: string) => ["billing", "invoice", "visit", visitId] as const,
  list: (params: Record<string, unknown>) => ["billing", "invoices", params] as const,
  dashboard: () => ["billing", "dashboard"] as const,
  history: (patientId: string) => ["billing", "history", patientId] as const,
};

export function useInvoice(invoiceId: string | null | undefined) {
  return useQuery({
    queryKey: invoiceId ? billingKeys.detail(invoiceId) : ["billing", "invoice", "detail", "none"],
    queryFn: () => billingApi.getInvoice(invoiceId as string),
    enabled: Boolean(invoiceId),
  });
}

export function useInvoiceForVisit(visitId: string | null | undefined) {
  return useQuery({
    queryKey: visitId ? billingKeys.forVisit(visitId) : ["billing", "invoice", "visit", "none"],
    queryFn: () => billingApi.getInvoiceForVisit(visitId as string),
    enabled: Boolean(visitId),
  });
}

/** Writes an updated Invoice into both cache entries it could be read from. */
export function useSyncInvoiceCache() {
  const queryClient = useQueryClient();
  return (invoice: Invoice) => {
    queryClient.setQueryData(billingKeys.detail(invoice.id), invoice);
    queryClient.setQueryData(billingKeys.forVisit(invoice.visitId), invoice);
    queryClient.invalidateQueries({ queryKey: billingKeys.dashboard() });
    queryClient.invalidateQueries({ queryKey: ["billing", "invoices"] });
    queryClient.invalidateQueries({ queryKey: billingKeys.history(invoice.patientId) });
  };
}
