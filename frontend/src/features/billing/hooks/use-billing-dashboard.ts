"use client";

import { useQuery } from "@tanstack/react-query";
import { billingApi } from "@/features/billing/api/billing-api";
import { billingKeys } from "@/features/billing/hooks/use-invoice";

export function useBillingDashboard() {
  return useQuery({
    queryKey: billingKeys.dashboard(),
    queryFn: () => billingApi.getDashboard(),
    refetchInterval: 30_000,
  });
}
