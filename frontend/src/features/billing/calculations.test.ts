import { describe, expect, it } from "vitest";
import {
  computeBalanceDue,
  computeDiscountAmount,
  computeGrandTotal,
  computeInvoiceSubtotal,
  computeItemLineTotal,
  validateSplitPayments,
} from "@/features/billing/calculations";

describe("invoice totals", () => {
  it("computes a line total from quantity/price minus a line discount", () => {
    expect(computeItemLineTotal(2, 100, 20)).toBe(180);
    expect(computeItemLineTotal(1, 50)).toBe(50);
  });

  it("never goes negative even if discount exceeds the line amount", () => {
    expect(computeItemLineTotal(1, 10, 50)).toBe(0);
  });

  it("sums item quantity*price across the invoice for the subtotal", () => {
    const subtotal = computeInvoiceSubtotal([
      { quantity: 1, unitPrice: 500 },
      { quantity: 2, unitPrice: 200 },
    ]);
    expect(subtotal).toBe(900);
  });

  it("computes grand total as subtotal minus discount total, floored at 0", () => {
    expect(computeGrandTotal(900, 100)).toBe(800);
    expect(computeGrandTotal(100, 500)).toBe(0);
  });

  it("computes balance due as grand total minus amount paid, floored at 0", () => {
    expect(computeBalanceDue(800, 300)).toBe(500);
    expect(computeBalanceDue(800, 800)).toBe(0);
    expect(computeBalanceDue(800, 1000)).toBe(0);
  });
});

describe("discount calculation", () => {
  it("computes a percentage discount off the subtotal", () => {
    expect(computeDiscountAmount(1000, "Percentage", 20)).toBe(200);
  });

  it("computes a fixed-amount discount as the raw value", () => {
    expect(computeDiscountAmount(1000, "FixedAmount", 150)).toBe(150);
  });
});

describe("split-payment validation", () => {
  it("accepts payment rows summing to exactly the balance due", () => {
    const result = validateSplitPayments([{ amount: 200 }, { amount: 300 }], 500);
    expect(result.valid).toBe(true);
    expect(result.total).toBe(500);
  });

  it("accepts payment rows summing to less than the balance due (partial payment)", () => {
    const result = validateSplitPayments([{ amount: 200 }], 500);
    expect(result.valid).toBe(true);
    expect(result.total).toBe(200);
  });

  it("rejects payment rows summing to more than the balance due", () => {
    const result = validateSplitPayments([{ amount: 400 }, { amount: 200 }], 500);
    expect(result.valid).toBe(false);
    expect(result.message).toMatch(/exceeds/);
  });

  it("rejects an empty set of payment rows", () => {
    expect(validateSplitPayments([], 500).valid).toBe(false);
  });

  it("rejects a non-positive payment amount", () => {
    expect(validateSplitPayments([{ amount: 0 }], 500).valid).toBe(false);
    expect(validateSplitPayments([{ amount: -10 }], 500).valid).toBe(false);
  });
});
