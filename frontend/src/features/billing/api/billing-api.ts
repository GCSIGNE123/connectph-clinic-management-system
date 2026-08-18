import { apiClient } from "@/lib/api-client";
import type {
  BillingHistoryItem,
  CashierDashboard,
  Discount,
  DiscountCalculationType,
  DiscountType,
  Invoice,
  InvoiceItemType,
  InvoiceListItem,
  InvoiceSearchParams,
  Payment,
  PaymentMethod,
  ReceiptPayload,
} from "@/features/billing/types";

/* eslint-disable @typescript-eslint/no-explicit-any -- raw snake_case wire shapes */

function toDiscount(raw: any): Discount {
  return {
    id: raw.id,
    invoiceId: raw.invoice_id,
    discountType: raw.discount_type,
    calculationType: raw.calculation_type,
    value: Number(raw.value),
    amount: Number(raw.amount),
    reason: raw.reason,
    approvedBy: raw.approved_by,
    createdAt: raw.created_at,
  };
}

function toPayment(raw: any): Payment {
  return {
    id: raw.id,
    invoiceId: raw.invoice_id,
    paymentMethod: raw.payment_method,
    amount: Number(raw.amount),
    referenceNumber: raw.reference_number,
    status: raw.status,
    receivedBy: raw.received_by,
    paidAt: raw.paid_at,
    voidedAt: raw.voided_at,
    voidedBy: raw.voided_by,
  };
}

function toInvoice(raw: any): Invoice {
  return {
    id: raw.id,
    invoiceNumber: raw.invoice_number,
    visitId: raw.visit_id,
    clinicId: raw.clinic_id,
    branchId: raw.branch_id,
    patientId: raw.patient_id,
    doctorId: raw.doctor_id,
    invoiceDate: raw.invoice_date,
    status: raw.status,
    subtotal: Number(raw.subtotal),
    discountTotal: Number(raw.discount_total),
    taxTotal: raw.tax_total !== null && raw.tax_total !== undefined ? Number(raw.tax_total) : null,
    grandTotal: Number(raw.grand_total),
    amountPaid: Number(raw.amount_paid),
    balanceDue: Number(raw.balance_due),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    patientName: raw.patient_name ?? null,
    patientNumber: raw.patient_number ?? null,
    doctorName: raw.doctor_name ?? null,
    visitNumber: raw.visit_number ?? null,
    branchName: raw.branch_name ?? null,
    items: (raw.items ?? []).map((i: any) => ({
      id: i.id,
      invoiceId: i.invoice_id,
      description: i.description,
      itemType: i.item_type,
      quantity: Number(i.quantity),
      unitPrice: Number(i.unit_price),
      discountAmount: Number(i.discount_amount),
      taxAmount: i.tax_amount !== null && i.tax_amount !== undefined ? Number(i.tax_amount) : null,
      lineTotal: Number(i.line_total),
      notes: i.notes ?? null,
    })),
    discounts: (raw.discounts ?? []).map(toDiscount),
    payments: (raw.payments ?? []).map(toPayment),
  };
}

function toListItem(raw: any): InvoiceListItem {
  return {
    id: raw.id,
    invoiceNumber: raw.invoice_number,
    visitId: raw.visit_id,
    visitNumber: raw.visit_number ?? null,
    patientId: raw.patient_id,
    patientName: raw.patient_name ?? null,
    patientNumber: raw.patient_number ?? null,
    doctorId: raw.doctor_id,
    doctorName: raw.doctor_name ?? null,
    invoiceDate: raw.invoice_date,
    status: raw.status,
    grandTotal: Number(raw.grand_total),
    amountPaid: Number(raw.amount_paid),
    balanceDue: Number(raw.balance_due),
    createdAt: raw.created_at,
  };
}

function toDashboard(raw: any): CashierDashboard {
  return {
    pendingPayments: raw.pending_payments,
    paidToday: raw.paid_today,
    todaysRevenue: Number(raw.todays_revenue),
    outstandingBalance: Number(raw.outstanding_balance),
    refundsPending: raw.refunds_pending,
    recentPayments: (raw.recent_payments ?? []).map((p: any) => ({
      id: p.id,
      invoiceNumber: p.invoice_number,
      patientName: p.patient_name,
      amount: Number(p.amount),
      paymentMethod: p.payment_method,
      paidAt: p.paid_at,
    })),
  };
}

function toReceipt(raw: any): ReceiptPayload {
  return {
    invoiceId: raw.invoice_id,
    invoiceNumber: raw.invoice_number,
    receiptNumber: raw.receipt_number,
    clinicName: raw.clinic_name,
    branchName: raw.branch_name,
    patientName: raw.patient_name,
    visitNumber: raw.visit_number,
    cashierName: raw.cashier_name,
    printedAt: raw.printed_at,
    items: (raw.items ?? []).map((i: any) => ({
      description: i.description,
      quantity: Number(i.quantity),
      unitPrice: Number(i.unit_price),
      lineTotal: Number(i.line_total),
    })),
    discounts: (raw.discounts ?? []).map(toDiscount),
    subtotal: Number(raw.subtotal),
    discountTotal: Number(raw.discount_total),
    grandTotal: Number(raw.grand_total),
    amountPaid: Number(raw.amount_paid),
    balanceDue: Number(raw.balance_due),
    payments: (raw.payments ?? []).map(toPayment),
  };
}

function toBillingHistoryItem(raw: any): BillingHistoryItem {
  return {
    id: raw.id,
    invoiceNumber: raw.invoice_number,
    invoiceDate: raw.invoice_date,
    grandTotal: Number(raw.grand_total),
    status: raw.status,
    visitId: raw.visit_id,
    visitNumber: raw.visit_number ?? null,
  };
}

export const billingApi = {
  listInvoices: async (params: InvoiceSearchParams): Promise<{ items: InvoiceListItem[]; total: number }> => {
    const query = new URLSearchParams();
    if (params.q) query.set("q", params.q);
    if (params.status) query.set("status", params.status);
    if (params.dateFrom) query.set("date_from", params.dateFrom);
    if (params.dateTo) query.set("date_to", params.dateTo);
    query.set("limit", String(params.limit ?? 20));
    query.set("offset", String(params.offset ?? 0));
    const raw = await apiClient.get<any>(`/invoices?${query.toString()}`);
    return { items: (raw.items ?? []).map(toListItem), total: raw.total };
  },
  getInvoice: async (invoiceId: string): Promise<Invoice> => {
    const raw = await apiClient.get<any>(`/invoices/${invoiceId}`);
    return toInvoice(raw);
  },
  getInvoiceForVisit: async (visitId: string): Promise<Invoice | null> => {
    const raw = await apiClient.get<any>(`/visits/${visitId}/invoice`);
    return raw ? toInvoice(raw) : null;
  },
  /** Laboratory pay-first workflow: creates (or returns the existing,
   * idempotent) invoice for a draft Laboratory Visit created via
   * `visitsApi.createPreQueue` - see
   * `InvoiceService.create_draft_invoice_for_laboratory_visit` on the
   * backend. A zero-priced Laboratory service comes back already `Paid`. */
  createLaboratoryInvoiceForVisit: async (visitId: string): Promise<Invoice> => {
    const raw = await apiClient.post<any>(`/visits/${visitId}/laboratory-invoice`);
    return toInvoice(raw);
  },
  getBillingHistory: async (patientId: string): Promise<BillingHistoryItem[]> => {
    const raw = await apiClient.get<any>(`/patients/${patientId}/billing-history`);
    return (raw.items ?? []).map(toBillingHistoryItem);
  },
  addItem: async (
    invoiceId: string,
    payload: { description: string; itemType: InvoiceItemType; quantity: number; unitPrice: number; discountAmount?: number; notes?: string | null }
  ): Promise<Invoice> => {
    const raw = await apiClient.post<any>(`/invoices/${invoiceId}/items`, {
      description: payload.description,
      item_type: payload.itemType,
      quantity: payload.quantity,
      unit_price: payload.unitPrice,
      discount_amount: payload.discountAmount ?? 0,
      notes: payload.notes ?? null,
    });
    return toInvoice(raw);
  },
  updateItem: async (invoiceId: string, itemId: string, payload: Partial<{ description: string; quantity: number; unitPrice: number; discountAmount: number }>): Promise<Invoice> => {
    const raw = await apiClient.patch<any>(`/invoices/${invoiceId}/items/${itemId}`, {
      description: payload.description,
      quantity: payload.quantity,
      unit_price: payload.unitPrice,
      discount_amount: payload.discountAmount,
    });
    return toInvoice(raw);
  },
  removeItem: async (invoiceId: string, itemId: string): Promise<Invoice> => {
    const raw = await apiClient.delete<any>(`/invoices/${invoiceId}/items/${itemId}`);
    return toInvoice(raw);
  },
  applyDiscount: async (
    invoiceId: string,
    payload: { discountType: DiscountType; calculationType: DiscountCalculationType; value: number; reason?: string | null }
  ): Promise<Invoice> => {
    const raw = await apiClient.post<any>(`/invoices/${invoiceId}/discounts`, {
      discount_type: payload.discountType,
      calculation_type: payload.calculationType,
      value: payload.value,
      reason: payload.reason ?? null,
    });
    return toInvoice(raw);
  },
  removeDiscount: async (invoiceId: string, discountId: string): Promise<Invoice> => {
    const raw = await apiClient.delete<any>(`/invoices/${invoiceId}/discounts/${discountId}`);
    return toInvoice(raw);
  },
  recordPayment: async (
    invoiceId: string,
    payments: { paymentMethod: PaymentMethod; amount: number; referenceNumber?: string | null }[]
  ): Promise<Invoice> => {
    const raw = await apiClient.post<any>(`/invoices/${invoiceId}/payments`, {
      payments: payments.map((p) => ({
        payment_method: p.paymentMethod,
        amount: p.amount,
        reference_number: p.referenceNumber ?? null,
      })),
    });
    return toInvoice(raw);
  },
  voidPayment: async (paymentId: string): Promise<Invoice> => {
    const raw = await apiClient.post<any>(`/payments/${paymentId}/void`);
    return toInvoice(raw);
  },
  getReceipt: async (invoiceId: string): Promise<ReceiptPayload> => {
    const raw = await apiClient.get<any>(`/invoices/${invoiceId}/receipt`);
    return toReceipt(raw);
  },
  printReceipt: async (invoiceId: string): Promise<ReceiptPayload> => {
    const raw = await apiClient.post<any>(`/invoices/${invoiceId}/receipt/print`);
    return toReceipt(raw);
  },
  getDashboard: async (): Promise<CashierDashboard> => {
    const raw = await apiClient.get<any>(`/billing/dashboard`);
    return toDashboard(raw);
  },
};
