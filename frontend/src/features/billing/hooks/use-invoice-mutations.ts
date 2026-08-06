"use client";

import { useMutation } from "@tanstack/react-query";
import { billingApi } from "@/features/billing/api/billing-api";
import { useSyncInvoiceCache } from "@/features/billing/hooks/use-invoice";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { DiscountCalculationType, DiscountType, InvoiceItemType } from "@/features/billing/types";

function useErrorToast() {
  const { toast } = useToast();
  return (title: string) => (error: unknown) =>
    toast({ title, description: error instanceof ApiError ? error.message : "Something went wrong.", variant: "error" });
}

export function useAddInvoiceItem(invoiceId: string) {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  const onErr = useErrorToast();
  return useMutation({
    mutationFn: (payload: { description: string; itemType: InvoiceItemType; quantity: number; unitPrice: number; discountAmount?: number; notes?: string | null }) =>
      billingApi.addItem(invoiceId, payload),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({ title: "Item added", variant: "success" });
    },
    onError: onErr("Could not add item"),
  });
}

export function useUpdateInvoiceItem(invoiceId: string) {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  const onErr = useErrorToast();
  return useMutation({
    mutationFn: ({ itemId, ...payload }: { itemId: string; description?: string; quantity?: number; unitPrice?: number; discountAmount?: number }) =>
      billingApi.updateItem(invoiceId, itemId, payload),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({ title: "Item updated", variant: "success" });
    },
    onError: onErr("Could not update item"),
  });
}

export function useRemoveInvoiceItem(invoiceId: string) {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  const onErr = useErrorToast();
  return useMutation({
    mutationFn: (itemId: string) => billingApi.removeItem(invoiceId, itemId),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({ title: "Item removed", variant: "success" });
    },
    onError: onErr("Could not remove item"),
  });
}

export function useApplyDiscount(invoiceId: string) {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  const onErr = useErrorToast();
  return useMutation({
    mutationFn: (payload: { discountType: DiscountType; calculationType: DiscountCalculationType; value: number; reason?: string | null }) =>
      billingApi.applyDiscount(invoiceId, payload),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({ title: "Discount applied", variant: "success" });
    },
    onError: onErr("Could not apply discount"),
  });
}

export function useRemoveDiscount(invoiceId: string) {
  const sync = useSyncInvoiceCache();
  const { toast } = useToast();
  const onErr = useErrorToast();
  return useMutation({
    mutationFn: (discountId: string) => billingApi.removeDiscount(invoiceId, discountId),
    onSuccess: (invoice) => {
      sync(invoice);
      toast({ title: "Discount removed", variant: "success" });
    },
    onError: onErr("Could not remove discount"),
  });
}
