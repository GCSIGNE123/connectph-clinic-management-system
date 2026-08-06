import { apiClient } from "@/lib/api-client";
import type { Shift } from "@/features/shifts/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

function toShift(raw: any): Shift {
  return {
    id: raw.id,
    clinicId: raw.clinic_id,
    branchId: raw.branch_id,
    receptionistUserId: raw.receptionist_user_id,
    receptionistName: raw.receptionist_name,
    openingCash: raw.opening_cash,
    openedAt: raw.opened_at,
    closedAt: raw.closed_at,
    actualCashCount: raw.actual_cash_count,
    status: raw.status,
    notes: raw.notes,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    expectedCash: raw.expected_cash,
    cashDifference: raw.cash_difference,
    summary: {
      cashCollections: raw.summary.cash_collections,
      gcashCollections: raw.summary.gcash_collections,
      cardCollections: raw.summary.card_collections,
      otherCollections: raw.summary.other_collections,
      totalCollections: raw.summary.total_collections,
      discountsGiven: raw.summary.discounts_given,
      cashRefunds: raw.summary.cash_refunds,
      nonCashRefunds: raw.summary.non_cash_refunds,
      totalRefunds: raw.summary.total_refunds,
      paymentCount: raw.summary.payment_count,
      discountCount: raw.summary.discount_count,
      refundCount: raw.summary.refund_count,
      expectedCash: raw.summary.expected_cash,
    },
  };
}

export const shiftsApi = {
  start: async (openingCash: number, branchId?: string): Promise<Shift> => {
    const raw = await apiClient.post<any>("/shifts", { opening_cash: openingCash, branch_id: branchId ?? null });
    return toShift(raw);
  },
  getCurrent: async (): Promise<Shift | null> => {
    const raw = await apiClient.get<any>("/shifts/current");
    return raw ? toShift(raw) : null;
  },
  getById: async (shiftId: string): Promise<Shift> => {
    const raw = await apiClient.get<any>(`/shifts/${shiftId}`);
    return toShift(raw);
  },
  close: async (shiftId: string, actualCashCount: number, notes?: string): Promise<Shift> => {
    const raw = await apiClient.post<any>(`/shifts/${shiftId}/close`, {
      actual_cash_count: actualCashCount,
      notes: notes ?? null,
    });
    return toShift(raw);
  },
  reopen: async (shiftId: string): Promise<Shift> => {
    const raw = await apiClient.post<any>(`/shifts/${shiftId}/reopen`, {});
    return toShift(raw);
  },
};
