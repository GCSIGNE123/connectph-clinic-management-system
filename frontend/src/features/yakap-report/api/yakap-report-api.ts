import { apiClient, apiFetchBlob } from "@/lib/api-client";
import type { InvoiceStatus } from "@/features/billing/types";
import type { YakapBillingReport, YakapReportParams } from "@/features/yakap-report/types";

interface RawRow {
  invoice_id: string;
  invoice_number: string;
  invoice_date: string;
  patient_id: string;
  patient_number: string;
  patient_name: string;
  visit_id: string | null;
  visit_number: string | null;
  consultation_count: number;
  laboratory_count: number;
  services: string[];
  total_billed: string | number;
  paid: string | number;
  outstanding: string | number;
  status: string;
}

interface RawReport {
  period: YakapBillingReport["period"];
  date_from: string;
  date_to: string;
  summary: {
    total_yakap_patients: number;
    total_invoices: number;
    total_consultations: number;
    total_laboratory_services: number;
    total_billed: string | number;
    total_paid: string | number;
    total_outstanding: string | number;
  };
  items: RawRow[];
  total: number;
  limit: number;
  offset: number;
}

const DEFAULT_PAGE_SIZE = 20;

/** Filter params shared by the JSON report and the CSV export (same filtered population). */
function filterQuery(params: YakapReportParams): URLSearchParams {
  const search = new URLSearchParams();
  search.set("period", params.period);
  if (params.period === "custom") {
    if (params.start) search.set("start", params.start);
    if (params.end) search.set("end", params.end);
  }
  if (params.search) search.set("q", params.search);
  return search;
}

export const yakapReportApi = {
  async get(params: YakapReportParams): Promise<YakapBillingReport> {
    const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;
    const page = params.page ?? 1;
    const search = filterQuery(params);
    search.set("limit", String(pageSize));
    search.set("offset", String((page - 1) * pageSize));
    const raw = await apiClient.get<RawReport>(`/billing/reports/yakap?${search.toString()}`);
    return {
      period: raw.period,
      dateFrom: raw.date_from,
      dateTo: raw.date_to,
      summary: {
        totalYakapPatients: raw.summary.total_yakap_patients,
        totalInvoices: raw.summary.total_invoices,
        totalConsultations: raw.summary.total_consultations,
        totalLaboratoryServices: raw.summary.total_laboratory_services,
        totalBilled: Number(raw.summary.total_billed),
        totalPaid: Number(raw.summary.total_paid),
        totalOutstanding: Number(raw.summary.total_outstanding),
      },
      items: raw.items.map((r) => ({
        invoiceId: r.invoice_id,
        invoiceNumber: r.invoice_number,
        invoiceDate: r.invoice_date,
        patientId: r.patient_id,
        patientNumber: r.patient_number,
        patientName: r.patient_name,
        visitId: r.visit_id,
        visitNumber: r.visit_number,
        consultationCount: r.consultation_count,
        laboratoryCount: r.laboratory_count,
        services: r.services,
        totalBilled: Number(r.total_billed),
        paid: Number(r.paid),
        outstanding: Number(r.outstanding),
        status: r.status as InvoiceStatus,
      })),
      total: raw.total,
      totalPages: Math.max(1, Math.ceil(raw.total / (raw.limit || 1))),
      page: Math.floor(raw.offset / (raw.limit || 1)) + 1,
      pageSize: raw.limit,
    };
  },

  /** Downloads the CSV for the whole filtered population (not just the visible page). */
  async exportCsv(params: YakapReportParams): Promise<void> {
    const blob = await apiFetchBlob(`/billing/reports/yakap/export?${filterQuery(params).toString()}`);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `yakap_billing_${params.period}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};
