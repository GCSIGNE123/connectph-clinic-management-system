import type { InvoiceStatus } from "@/features/billing/types";

export type YakapReportPeriod = "weekly" | "monthly" | "yearly" | "custom";

export const YAKAP_REPORT_PERIOD_LABELS: Record<YakapReportPeriod, string> = {
  weekly: "Weekly",
  monthly: "Monthly",
  yearly: "Yearly",
  custom: "Custom Date Range",
};

export interface YakapReportParams {
  period: YakapReportPeriod;
  /** Only used when `period === "custom"`. ISO dates (YYYY-MM-DD, invoice date). */
  start?: string;
  end?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}

export interface YakapReportSummary {
  totalYakapPatients: number;
  totalInvoices: number;
  totalConsultations: number;
  totalLaboratoryServices: number;
  totalBilled: number;
  totalPaid: number;
  totalOutstanding: number;
}

export interface YakapReportRow {
  invoiceId: string;
  invoiceNumber: string;
  invoiceDate: string;
  patientId: string;
  patientNumber: string;
  patientName: string;
  visitId: string | null;
  visitNumber: string | null;
  consultationCount: number;
  laboratoryCount: number;
  services: string[];
  totalBilled: number;
  paid: number;
  outstanding: number;
  status: InvoiceStatus;
}

export interface YakapBillingReport {
  period: YakapReportPeriod;
  dateFrom: string;
  dateTo: string;
  summary: YakapReportSummary;
  items: YakapReportRow[];
  total: number;
  totalPages: number;
  page: number;
  pageSize: number;
}
