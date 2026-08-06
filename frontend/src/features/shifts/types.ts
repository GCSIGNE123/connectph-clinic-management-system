export interface ShiftSummary {
  cashCollections: string;
  gcashCollections: string;
  cardCollections: string;
  otherCollections: string;
  totalCollections: string;
  discountsGiven: string;
  cashRefunds: string;
  nonCashRefunds: string;
  totalRefunds: string;
  paymentCount: number;
  discountCount: number;
  refundCount: number;
  expectedCash: string;
}

export type ShiftStatus = "Open" | "Closed";

export interface Shift {
  id: string;
  clinicId: string;
  branchId: string | null;
  receptionistUserId: string;
  receptionistName: string | null;
  openingCash: string;
  openedAt: string;
  closedAt: string | null;
  actualCashCount: string | null;
  status: ShiftStatus;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
  summary: ShiftSummary;
  expectedCash: string | null;
  cashDifference: string | null;
}
