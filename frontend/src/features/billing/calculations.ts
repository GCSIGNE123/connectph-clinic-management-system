/**
 * Pure calculation helpers for invoice totals, discount amounts, and
 * split-payment validation - extracted so they're unit-testable without a
 * rendered component (mirrors `bmi.ts` in `features/consultation/`).
 */

import type { DiscountCalculationType, InvoiceItem } from "@/features/billing/types";

export function computeItemLineTotal(quantity: number, unitPrice: number, discountAmount = 0): number {
  return Math.max(quantity * unitPrice - discountAmount, 0);
}

export function computeInvoiceSubtotal(items: Pick<InvoiceItem, "quantity" | "unitPrice">[]): number {
  return items.reduce((sum, i) => sum + i.quantity * i.unitPrice, 0);
}

export function computeDiscountAmount(subtotal: number, calculationType: DiscountCalculationType, value: number): number {
  if (calculationType === "Percentage") {
    return Math.round(((subtotal * value) / 100) * 100) / 100;
  }
  return value;
}

export function computeGrandTotal(subtotal: number, discountTotal: number): number {
  return Math.max(subtotal - discountTotal, 0);
}

export function computeBalanceDue(grandTotal: number, amountPaid: number): number {
  return Math.max(grandTotal - amountPaid, 0);
}

export interface SplitPaymentValidationResult {
  valid: boolean;
  total: number;
  message?: string;
}

/** Validates that a set of split-payment rows sums to no more than the
 * remaining balance, and each row has a positive amount. */
export function validateSplitPayments(
  rows: { amount: number }[],
  balanceDue: number
): SplitPaymentValidationResult {
  if (rows.length === 0) {
    return { valid: false, total: 0, message: "Add at least one payment." };
  }
  if (rows.some((r) => !(r.amount > 0))) {
    return { valid: false, total: 0, message: "Each payment amount must be greater than zero." };
  }
  const total = Math.round(rows.reduce((sum, r) => sum + r.amount, 0) * 100) / 100;
  if (total > balanceDue + 0.001) {
    return { valid: false, total, message: `Payment total (${total.toFixed(2)}) exceeds the remaining balance (${balanceDue.toFixed(2)}).` };
  }
  return { valid: true, total };
}
