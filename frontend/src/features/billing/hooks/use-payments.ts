"use client";

import { useMutation } from "@tanstack/react-query";
import { billingApi } from "@/features/billing/api/billing-api";
import { useSyncInvoiceCache } from "@/features/billing/hooks/use-invoice";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { PaymentMethod } from "@/features/billing/types";

/**
 * `onShiftRequired` (item 7, Shift Enforcement): optional hook for the
 * caller (`PaymentDialog`) to intercept the "Receptionist has no open
 * shift" 400 via the shared `useShiftRequiredError` hook and show the
 * shared `<ShiftRequiredDialog>` instead of the generic error toast. If it
 * returns `true` (handled), the toast below is skipped.
 */
export function useRecordPayment(invoiceId: string, onShiftRequired?: (error: unknown) => boolean) {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (payments: { paymentMethod: PaymentMethod; amount: number; referenceNumber?: string | null }[]) =>
      billingApi.recordPayment(invoiceId, payments),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({
        title: invoice.status === "Paid" ? "Payment recorded — invoice paid in full" : "Payment recorded",
        variant: "success",
      });
    },
    onError: (error) => {
      if (onShiftRequired?.(error)) return;
      toast({
        title: "Could not record payment",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}

export function useVoidPayment() {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (paymentId: string) => billingApi.voidPayment(paymentId),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({ title: "Payment voided", variant: "success" });
    },
    onError: (error) => {
      toast({
        title: "Could not void payment",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}
