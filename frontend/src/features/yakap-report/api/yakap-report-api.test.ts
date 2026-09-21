import { beforeEach, describe, expect, it, vi } from "vitest";
import { yakapReportApi } from "./yakap-report-api";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a) },
  apiFetchBlob: vi.fn(),
}));

const RAW = {
  period: "custom",
  date_from: "2026-06-01",
  date_to: "2026-06-30",
  summary: {
    total_yakap_patients: 1,
    total_invoices: 1,
    total_consultations: 1,
    total_laboratory_services: 2,
    total_billed: "650.00",
    total_paid: "300.00",
    total_outstanding: "350.00",
  },
  items: [
    {
      invoice_id: "i1",
      invoice_number: "INV-1",
      invoice_date: "2026-06-05",
      patient_id: "p1",
      patient_number: "PAT-1",
      patient_name: "Yak One",
      visit_id: null,
      visit_number: null,
      consultation_count: 1,
      laboratory_count: 2,
      services: ["Consultation", "CBC"],
      total_billed: "650.00",
      paid: "300.00",
      outstanding: "350.00",
      status: "PartiallyPaid",
    },
  ],
  total: 45,
  limit: 20,
  offset: 20,
};

describe("yakapReportApi.get (Task #4)", () => {
  beforeEach(() => getMock.mockReset().mockResolvedValue(RAW));
  const urlOf = () => String(getMock.mock.calls.at(-1)?.[0]);

  it("sends custom start/end, search and pagination; omits start/end for a preset period", async () => {
    await yakapReportApi.get({ period: "custom", start: "2026-06-01", end: "2026-06-30", search: "Yak", page: 2, pageSize: 20 });
    const url = urlOf();
    expect(url).toContain("/billing/reports/yakap?");
    expect(url).toContain("period=custom");
    expect(url).toContain("start=2026-06-01");
    expect(url).toContain("end=2026-06-30");
    expect(url).toContain("q=Yak");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=20");

    await yakapReportApi.get({ period: "weekly", start: "2026-06-01", end: "2026-06-30" });
    expect(urlOf()).toContain("period=weekly");
    expect(urlOf()).not.toContain("start=");
  });

  it("maps decimals to numbers, snake_case to camelCase, and computes paging meta", async () => {
    const report = await yakapReportApi.get({ period: "custom", start: "2026-06-01", end: "2026-06-30", page: 2, pageSize: 20 });
    expect(report.summary).toEqual({
      totalYakapPatients: 1,
      totalInvoices: 1,
      totalConsultations: 1,
      totalLaboratoryServices: 2,
      totalBilled: 650,
      totalPaid: 300,
      totalOutstanding: 350,
    });
    expect(report.items[0]).toMatchObject({
      invoiceNumber: "INV-1",
      totalBilled: 650,
      paid: 300,
      outstanding: 350,
      status: "PartiallyPaid",
    });
    expect(report.total).toBe(45);
    expect(report.totalPages).toBe(3);
    expect(report.page).toBe(2);
  });
});
