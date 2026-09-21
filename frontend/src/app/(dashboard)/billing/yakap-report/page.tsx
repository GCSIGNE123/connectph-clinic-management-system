"use client";

import { useMemo, useState } from "react";
import { Download, Printer, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState } from "@/components/layout/EmptyState";
import { InvoiceStatusBadge } from "@/features/billing/components/InvoiceStatusBadge";
import { formatCurrency, formatNumber } from "@/features/analytics/lib/format";
import { useDebouncedValue } from "@/features/patients/hooks/use-patients";
import { useYakapReport } from "@/features/yakap-report/hooks/use-yakap-report";
import { yakapReportApi } from "@/features/yakap-report/api/yakap-report-api";
import { YAKAP_REPORT_PERIOD_LABELS, type YakapReportPeriod } from "@/features/yakap-report/types";
import { ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

/**
 * YAKAP Billing Report (Task #4). Population = invoices of patients marked
 * YAKAP beneficiaries (`Patient.is_yakap_beneficiary`); the per-visit queue
 * classification does not decide inclusion. Date basis = invoice date
 * (Asia/Manila). Every figure comes from the server - the totals cover the
 * whole filtered population, not just the visible page.
 */
export default function YakapBillingReportPage() {
  const [period, setPeriod] = useState<YakapReportPeriod>("monthly");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 350);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const params = useMemo(
    () => ({
      period,
      start: period === "custom" ? start || undefined : undefined,
      end: period === "custom" ? end || undefined : undefined,
      search: debouncedSearch || undefined,
      page,
      pageSize: PAGE_SIZE,
    }),
    [period, start, end, debouncedSearch, page]
  );

  const { data, isLoading, isFetching, isError, error } = useYakapReport(params);
  const customIncomplete = period === "custom" && (!start || !end);
  const invalidRange = period === "custom" && Boolean(start && end && start > end);

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      await yakapReportApi.exportCsv(params);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const summary = data?.summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <div>
          <h1 className="text-xl font-semibold text-foreground">YAKAP Billing Report</h1>
          <p className="text-sm text-muted-foreground">Billing for patients marked as YAKAP beneficiaries.</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={handleExport} disabled={exporting || customIncomplete || invalidRange}>
            <Download className="h-4 w-4" aria-hidden="true" />
            {exporting ? "Exporting…" : "Export CSV"}
          </Button>
          <Button type="button" variant="outline" onClick={() => window.print()} disabled={!data}>
            <Printer className="h-4 w-4" aria-hidden="true" />
            Print
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end print:hidden">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground" htmlFor="yakap-period">
            Period
          </label>
          <Select
            id="yakap-period"
            aria-label="Report period"
            className="w-full sm:w-52"
            value={period}
            onChange={(e) => {
              setPeriod(e.target.value as YakapReportPeriod);
              setPage(1);
            }}
          >
            {(Object.keys(YAKAP_REPORT_PERIOD_LABELS) as YakapReportPeriod[]).map((p) => (
              <option key={p} value={p}>
                {YAKAP_REPORT_PERIOD_LABELS[p]}
              </option>
            ))}
          </Select>
        </div>

        {period === "custom" ? (
          <>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="yakap-from">
                From
              </label>
              <Input
                id="yakap-from"
                type="date"
                aria-label="From date"
                value={start}
                onChange={(e) => {
                  setStart(e.target.value);
                  setPage(1);
                }}
                className="sm:w-44"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="yakap-to">
                To
              </label>
              <Input
                id="yakap-to"
                type="date"
                aria-label="To date"
                value={end}
                onChange={(e) => {
                  setEnd(e.target.value);
                  setPage(1);
                }}
                className="sm:w-44"
              />
            </div>
          </>
        ) : null}

        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            placeholder="Search patient, invoice, or visit"
            className="pl-8"
            value={searchInput}
            onChange={(e) => {
              setSearchInput(e.target.value);
              setPage(1);
            }}
            aria-label="Search YAKAP billing report"
          />
        </div>
      </div>

      {exportError ? (
        <p role="alert" className="text-sm text-destructive print:hidden">
          {exportError}
        </p>
      ) : null}
      {invalidRange ? (
        <p role="alert" className="text-sm text-destructive print:hidden">
          The start date must not be after the end date.
        </p>
      ) : null}

      <div id="yakap-report-printable" className="space-y-4">
        <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground" data-testid="yakap-report-note">
          YAKAP billing report is based on patients marked as YAKAP beneficiaries. Visit classification (Yakap/Regular) does
          not determine inclusion.
        </p>

        {data ? (
          <p className="text-sm text-muted-foreground" data-testid="yakap-report-range">
            {YAKAP_REPORT_PERIOD_LABELS[data.period]}: {formatDate(data.dateFrom)} – {formatDate(data.dateTo)} · by invoice
            date (Asia/Manila)
          </p>
        ) : null}

        {customIncomplete ? (
          <EmptyState title="Choose a date range" description="Pick both a start and an end date to run the report." />
        ) : invalidRange ? null : isError ? (
          <EmptyState
            title="Could not load the report"
            description={error instanceof ApiError ? error.message : "Something went wrong while loading the report."}
          />
        ) : isLoading || !summary ? (
          <div className="space-y-2" aria-busy="true" data-testid="yakap-report-loading">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <SummaryCard label="YAKAP Patients" value={formatNumber(summary.totalYakapPatients)} />
              <SummaryCard label="Consultations" value={formatNumber(summary.totalConsultations)} />
              <SummaryCard label="Laboratory Services" value={formatNumber(summary.totalLaboratoryServices)} />
              <SummaryCard label="Total Billed" value={formatCurrency(summary.totalBilled)} />
              <SummaryCard label="Total Paid" value={formatCurrency(summary.totalPaid)} />
              <SummaryCard label="Outstanding" value={formatCurrency(summary.totalOutstanding)} />
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Details</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data && data.items.length === 0 ? (
                  <EmptyState
                    title="No YAKAP billing records"
                    description={
                      debouncedSearch
                        ? `No YAKAP billing records match "${debouncedSearch}" in this period.`
                        : "No YAKAP patient invoices fall in this period."
                    }
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Patient</TableHead>
                        <TableHead>Visit</TableHead>
                        <TableHead>Invoice</TableHead>
                        <TableHead>Services</TableHead>
                        <TableHead className="text-right">Billed</TableHead>
                        <TableHead className="text-right">Paid</TableHead>
                        <TableHead className="text-right">Balance</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data?.items.map((row) => (
                        <TableRow key={row.invoiceId}>
                          <TableCell>{formatDate(row.invoiceDate)}</TableCell>
                          <TableCell>
                            <div className="font-medium">{row.patientName}</div>
                            <div className="text-xs text-muted-foreground">{row.patientNumber}</div>
                          </TableCell>
                          <TableCell>{row.visitNumber ?? "—"}</TableCell>
                          <TableCell>{row.invoiceNumber}</TableCell>
                          <TableCell className="max-w-56 text-xs text-muted-foreground">
                            {row.services.join(", ") || "—"}
                          </TableCell>
                          <TableCell className="text-right">{formatCurrency(row.totalBilled)}</TableCell>
                          <TableCell className="text-right">{formatCurrency(row.paid)}</TableCell>
                          <TableCell className="text-right">{formatCurrency(row.outstanding)}</TableCell>
                          <TableCell>
                            <InvoiceStatusBadge status={row.status} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {data && data.totalPages > 1 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground print:hidden">
          <span>
            Page {data.page} of {data.totalPages} ({data.total} invoices)
          </span>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" disabled={page <= 1 || isFetching} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= data.totalPages || isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}

      <style jsx global>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #yakap-report-printable,
          #yakap-report-printable * {
            visibility: visible;
          }
          #yakap-report-printable {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
          }
        }
      `}</style>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}
