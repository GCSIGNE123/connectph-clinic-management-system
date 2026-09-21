import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import YakapBillingReportPage from "./page";
import type { YakapBillingReport } from "@/features/yakap-report/types";

const useYakapReportMock = vi.fn();
vi.mock("@/features/yakap-report/hooks/use-yakap-report", () => ({
  useYakapReport: (params: unknown) => useYakapReportMock(params),
}));
vi.mock("@/features/patients/hooks/use-patients", () => ({
  useDebouncedValue: <T,>(value: T) => value,
}));
const exportCsvMock = vi.fn();
vi.mock("@/features/yakap-report/api/yakap-report-api", () => ({
  yakapReportApi: { exportCsv: (p: unknown) => exportCsvMock(p) },
}));

const REPORT: YakapBillingReport = {
  period: "monthly",
  dateFrom: "2026-09-01",
  dateTo: "2026-09-30",
  summary: {
    totalYakapPatients: 2,
    totalInvoices: 3,
    totalConsultations: 3,
    totalLaboratoryServices: 4,
    totalBilled: 1750,
    totalPaid: 900,
    totalOutstanding: 850,
  },
  items: [
    {
      invoiceId: "inv-1",
      invoiceNumber: "INV-20260918-000001",
      invoiceDate: "2026-09-18",
      patientId: "p1",
      patientNumber: "PAT-000086",
      patientName: "YakapVerify PatientOne",
      visitId: "v1",
      visitNumber: "VIS-20260918-000004",
      consultationCount: 1,
      laboratoryCount: 2,
      services: ["Consultation", "CBC", "Urinalysis"],
      totalBilled: 650,
      paid: 300,
      outstanding: 350,
      status: "PartiallyPaid",
    },
    {
      invoiceId: "inv-2",
      invoiceNumber: "INV-20260901-000002",
      invoiceDate: "2026-09-01",
      patientId: "p1",
      patientNumber: "PAT-000086",
      patientName: "YakapVerify PatientOne",
      visitId: null,
      visitNumber: null,
      consultationCount: 1,
      laboratoryCount: 0,
      services: ["Consultation"],
      totalBilled: 300,
      paid: 300,
      outstanding: 0,
      status: "Paid",
    },
  ],
  total: 45,
  totalPages: 3,
  page: 1,
  pageSize: 20,
};

function ok(data: YakapBillingReport | undefined, extra: Record<string, unknown> = {}) {
  return { data, isLoading: false, isFetching: false, isError: false, error: null, ...extra };
}
const lastParams = () => useYakapReportMock.mock.calls.at(-1)?.[0];

describe("YakapBillingReportPage (Task #4)", () => {
  beforeEach(() => {
    useYakapReportMock.mockReset().mockReturnValue(ok(REPORT));
    exportCsvMock.mockReset().mockResolvedValue(undefined);
  });

  it("renders the title, the explanatory note, and defaults to the Monthly period", () => {
    render(<YakapBillingReportPage />);
    expect(screen.getByRole("heading", { name: "YAKAP Billing Report" })).toBeInTheDocument();
    expect(screen.getByTestId("yakap-report-note")).toHaveTextContent(
      "YAKAP billing report is based on patients marked as YAKAP beneficiaries. Visit classification (Yakap/Regular) does not determine inclusion."
    );
    expect(screen.getByLabelText("Report period")).toHaveValue("monthly");
    expect(lastParams()).toMatchObject({ period: "monthly", page: 1 });
    expect(screen.getByTestId("yakap-report-range")).toHaveTextContent("09/01/2026");
    expect(screen.getByTestId("yakap-report-range")).toHaveTextContent("Asia/Manila");
  });

  it("offers Weekly, Monthly, Yearly and Custom Date Range and sends the chosen period", async () => {
    const user = userEvent.setup();
    render(<YakapBillingReportPage />);
    const options = within(screen.getByLabelText("Report period")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Weekly", "Monthly", "Yearly", "Custom Date Range"]);

    for (const period of ["weekly", "yearly", "monthly"] as const) {
      await user.selectOptions(screen.getByLabelText("Report period"), period);
      await waitFor(() => expect(lastParams()).toMatchObject({ period, page: 1 }));
    }
  });

  it("custom range shows date inputs, sends start/end, and drops them for other periods", async () => {
    const user = userEvent.setup();
    render(<YakapBillingReportPage />);
    expect(screen.queryByLabelText("From date")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Report period"), "custom");
    expect(screen.getByText("Choose a date range")).toBeInTheDocument();

    await user.type(screen.getByLabelText("From date"), "2026-06-01");
    await user.type(screen.getByLabelText("To date"), "2026-06-30");
    await waitFor(() => expect(lastParams()).toMatchObject({ period: "custom", start: "2026-06-01", end: "2026-06-30" }));

    await user.selectOptions(screen.getByLabelText("Report period"), "weekly");
    await waitFor(() => expect(lastParams().start).toBeUndefined());
  });

  it("warns when the custom start is after the end and disables export", async () => {
    const user = userEvent.setup();
    render(<YakapBillingReportPage />);
    await user.selectOptions(screen.getByLabelText("Report period"), "custom");
    await user.type(screen.getByLabelText("From date"), "2026-06-30");
    await user.type(screen.getByLabelText("To date"), "2026-06-01");
    expect(screen.getByRole("alert")).toHaveTextContent("start date must not be after the end date");
    expect(screen.getByRole("button", { name: /Export CSV/ })).toBeDisabled();
  });

  it("shows the server-computed summary values", () => {
    render(<YakapBillingReportPage />);
    const cardValue = (label: string) => screen.getByText(label).parentElement as HTMLElement;
    expect(cardValue("YAKAP Patients")).toHaveTextContent("2");
    expect(cardValue("Consultations")).toHaveTextContent("3");
    expect(cardValue("Laboratory Services")).toHaveTextContent("4");
    expect(cardValue("Total Billed")).toHaveTextContent("1,750.00");
    expect(cardValue("Total Paid")).toHaveTextContent("900.00");
    expect(cardValue("Outstanding")).toHaveTextContent("850.00");
  });

  it("renders one detail row per invoice with services, amounts and status", () => {
    render(<YakapBillingReportPage />);
    const rows = screen.getAllByRole("row").slice(1); // skip header
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("INV-20260918-000001")).toBeInTheDocument();
    expect(within(rows[0]).getByText("YakapVerify PatientOne")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Consultation, CBC, Urinalysis")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Partially Paid")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Paid")).toBeInTheDocument();
  });

  it("shows a loading state", () => {
    useYakapReportMock.mockReturnValue(ok(undefined, { isLoading: true }));
    render(<YakapBillingReportPage />);
    expect(screen.getByTestId("yakap-report-loading")).toBeInTheDocument();
  });

  it("shows an error state without crashing", () => {
    useYakapReportMock.mockReturnValue(ok(undefined, { isError: true, error: new Error("boom") }));
    render(<YakapBillingReportPage />);
    expect(screen.getByText("Could not load the report")).toBeInTheDocument();
  });

  it("shows the empty state (with zeroed summary) when nothing qualifies, and a search-specific message", async () => {
    const user = userEvent.setup();
    const empty: YakapBillingReport = {
      ...REPORT,
      summary: {
        ...REPORT.summary,
        totalYakapPatients: 0,
        totalInvoices: 0,
        totalConsultations: 0,
        totalLaboratoryServices: 0,
        totalBilled: 0,
        totalPaid: 0,
        totalOutstanding: 0,
      },
      items: [],
      total: 0,
      totalPages: 1,
    };
    useYakapReportMock.mockReturnValue(ok(empty));
    render(<YakapBillingReportPage />);
    expect(screen.getByText("No YAKAP billing records")).toBeInTheDocument();
    expect(screen.getByText("No YAKAP patient invoices fall in this period.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search YAKAP billing report"), "Cruz");
    await waitFor(() => expect(screen.getByText(/No YAKAP billing records match "Cruz"/)).toBeInTheDocument());
    expect(lastParams()).toMatchObject({ search: "Cruz", page: 1 });
  });

  it("paginates: Next moves the page, and changing a filter resets to page 1", async () => {
    const user = userEvent.setup();
    render(<YakapBillingReportPage />);
    expect(screen.getByText(/Page 1 of 3 \(45 invoices\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ page: 2 }));
    await user.selectOptions(screen.getByLabelText("Report period"), "yearly");
    await waitFor(() => expect(lastParams()).toMatchObject({ period: "yearly", page: 1 }));
  });

  it("Export CSV sends the current filters (whole population, not the page)", async () => {
    const user = userEvent.setup();
    render(<YakapBillingReportPage />);
    await user.click(screen.getByRole("button", { name: /Export CSV/ }));
    await waitFor(() => expect(exportCsvMock).toHaveBeenCalledTimes(1));
    expect(exportCsvMock.mock.calls[0][0]).toMatchObject({ period: "monthly" });
  });

  it("Print calls window.print", async () => {
    const user = userEvent.setup();
    const printSpy = vi.spyOn(window, "print").mockImplementation(() => {});
    render(<YakapBillingReportPage />);
    await user.click(screen.getByRole("button", { name: /Print/ }));
    expect(printSpy).toHaveBeenCalled();
    printSpy.mockRestore();
  });
});
