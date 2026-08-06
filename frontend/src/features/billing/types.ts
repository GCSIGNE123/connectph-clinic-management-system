/**
 * Domain types for Billing & Cashier (Phase 9), mirroring
 * `schemas/billing.py`.
 */

export type InvoiceStatus = "Draft" | "PendingPayment" | "PartiallyPaid" | "Paid" | "Cancelled";
export type InvoiceItemType =
  | "ConsultationFee"
  | "FollowUpFee"
  | "MedicalCertificate"
  | "Laboratory"
  | "XRay"
  | "Procedure"
  | "Vaccination"
  | "Custom";
export type DiscountType = "SeniorCitizen" | "PWD" | "Employee" | "Custom";
export type DiscountCalculationType = "Percentage" | "FixedAmount";
export type PaymentMethod = "Cash" | "GCash" | "BankTransfer" | "CreditCard" | "DebitCard";
export type PaymentStatus = "Completed" | "Voided";

export interface InvoiceItem {
  id: string;
  invoiceId: string;
  description: string;
  itemType: InvoiceItemType;
  quantity: number;
  unitPrice: number;
  discountAmount: number;
  taxAmount: number | null;
  lineTotal: number;
  notes: string | null;
}

export interface Discount {
  id: string;
  invoiceId: string;
  discountType: DiscountType;
  calculationType: DiscountCalculationType;
  value: number;
  amount: number;
  reason: string | null;
  approvedBy: string | null;
  createdAt: string;
}

export interface Payment {
  id: string;
  invoiceId: string;
  paymentMethod: PaymentMethod;
  amount: number;
  referenceNumber: string | null;
  status: PaymentStatus;
  receivedBy: string | null;
  paidAt: string;
  voidedAt: string | null;
  voidedBy: string | null;
}

export interface Invoice {
  id: string;
  invoiceNumber: string;
  visitId: string;
  clinicId: string;
  branchId: string;
  patientId: string;
  doctorId: string | null;
  invoiceDate: string;
  status: InvoiceStatus;
  subtotal: number;
  discountTotal: number;
  taxTotal: number | null;
  grandTotal: number;
  amountPaid: number;
  balanceDue: number;
  createdAt: string;
  updatedAt: string;
  patientName: string | null;
  patientNumber: string | null;
  doctorName: string | null;
  visitNumber: string | null;
  branchName: string | null;
  items: InvoiceItem[];
  discounts: Discount[];
  payments: Payment[];
}

export interface InvoiceListItem {
  id: string;
  invoiceNumber: string;
  visitId: string;
  visitNumber: string | null;
  patientId: string;
  patientName: string | null;
  patientNumber: string | null;
  doctorId: string | null;
  doctorName: string | null;
  invoiceDate: string;
  status: InvoiceStatus;
  grandTotal: number;
  amountPaid: number;
  balanceDue: number;
  createdAt: string;
}

export interface InvoiceSearchParams {
  q?: string;
  status?: InvoiceStatus;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
}

export interface ReceiptPayload {
  invoiceId: string;
  invoiceNumber: string;
  receiptNumber: string;
  clinicName: string;
  branchName: string | null;
  patientName: string | null;
  visitNumber: string | null;
  cashierName: string | null;
  printedAt: string;
  items: { description: string; quantity: number; unitPrice: number; lineTotal: number }[];
  discounts: Discount[];
  subtotal: number;
  discountTotal: number;
  grandTotal: number;
  amountPaid: number;
  balanceDue: number;
  payments: Payment[];
}

export interface RecentPayment {
  id: string;
  invoiceNumber: string;
  patientName: string | null;
  amount: number;
  paymentMethod: PaymentMethod;
  paidAt: string;
}

export interface CashierDashboard {
  pendingPayments: number;
  paidToday: number;
  todaysRevenue: number;
  outstandingBalance: number;
  refundsPending: number;
  recentPayments: RecentPayment[];
}

export interface BillingHistoryItem {
  id: string;
  invoiceNumber: string;
  invoiceDate: string;
  grandTotal: number;
  status: InvoiceStatus;
  visitId: string;
  visitNumber: string | null;
}
