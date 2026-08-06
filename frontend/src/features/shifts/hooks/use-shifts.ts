"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { shiftsApi } from "@/features/shifts/api/shifts-api";

export const shiftsKeys = {
  current: () => ["shifts", "current"] as const,
  detail: (id: string) => ["shifts", "detail", id] as const,
};

/** Live summary, so poll while the shift is open - same "plain polling is
 * fine" scope as Messages, no WebSocket infra needed for this feature. */
export function useCurrentShift() {
  return useQuery({
    queryKey: shiftsKeys.current(),
    queryFn: () => shiftsApi.getCurrent(),
    refetchInterval: 15_000,
  });
}

export function useShift(shiftId: string | undefined) {
  return useQuery({
    queryKey: shiftsKeys.detail(shiftId ?? ""),
    queryFn: () => shiftsApi.getById(shiftId as string),
    enabled: Boolean(shiftId),
  });
}

export function useStartShift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ openingCash, branchId }: { openingCash: number; branchId?: string }) =>
      shiftsApi.start(openingCash, branchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: shiftsKeys.current() });
    },
  });
}

export function useCloseShift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ shiftId, actualCashCount, notes }: { shiftId: string; actualCashCount: number; notes?: string }) =>
      shiftsApi.close(shiftId, actualCashCount, notes),
    onSuccess: (shift) => {
      queryClient.invalidateQueries({ queryKey: shiftsKeys.current() });
      queryClient.invalidateQueries({ queryKey: shiftsKeys.detail(shift.id) });
    },
  });
}

export function useReopenShift() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (shiftId: string) => shiftsApi.reopen(shiftId),
    onSuccess: (shift) => {
      queryClient.invalidateQueries({ queryKey: shiftsKeys.current() });
      queryClient.invalidateQueries({ queryKey: shiftsKeys.detail(shift.id) });
    },
  });
}
