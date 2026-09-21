"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { useBillingDashboard } from "@/features/billing/hooks/use-billing-dashboard";
import { useInvoices } from "@/features/billing/hooks/use-invoices";
import { InvoiceTable } from "@/features/billing/components/InvoiceTable";
import type { InvoiceStatus } from "@/features/billing/types";

const STATUS_FILTERS: { value: InvoiceStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "PendingPayment", label: "Pending Payment" },
  { value: "PartiallyPaid", label: "Partially Paid" },
  { value: "Paid", label: "Paid" },
  { value: "Cancelled", label: "Cancelled" },
];

const PAGE_SIZE = 20;

export default function BillingDashboardPage() {
  const { data: dashboard, isLoading: dashboardLoading } = useBillingDashboard();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<InvoiceStatus | "">("");
  const [dateRange, setDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({});
  // Task #9: the list used to be hard-capped at 20 rows with no way to reach
  // older invoices. "Load more" grows the page size instead; it resets to 20
  // whenever a filter changes so the newest patients are always on top.
  const [limit, setLimit] = useState(PAGE_SIZE);
  const { data, isLoading } = useInvoices({
    q: q || undefined,
    status: status || undefined,
    dateFrom: dateRange.dateFrom,
    dateTo: dateRange.dateTo,
    limit,
    offset: 0,
  });
  const shownCount = data?.items.length ?? 0;
  const hasMore = (data?.total ?? 0) > shownCount;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Billing &amp; Cashier</h1>
        <p className="text-sm text-muted-foreground">Invoices, payments, and receipts for the clinic.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Pending Payments" value={dashboardLoading ? null : dashboard?.pendingPayments} />
        <StatCard label="Paid Today" value={dashboardLoading ? null : dashboard?.paidToday} />
        <StatCard label="Today's Revenue" value={dashboardLoading ? null : `₱${(dashboard?.todaysRevenue ?? 0).toFixed(2)}`} />
        <StatCard label="Outstanding Balance" value={dashboardLoading ? null : `₱${(dashboard?.outstandingBalance ?? 0).toFixed(2)}`} />
        <StatCard label="Refunds Pending" value={dashboardLoading ? null : dashboard?.refundsPending} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent payments</CardTitle>
        </CardHeader>
        <CardContent>
          {dashboardLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : dashboard && dashboard.recentPayments.length > 0 ? (
            <ul className="divide-y divide-border text-sm">
              {dashboard.recentPayments.map((p) => (
                <li key={p.id} className="flex items-center justify-between py-2">
                  <span>
                    {p.invoiceNumber} &middot; {p.patientName ?? "-"} &middot; {p.paymentMethod}
                  </span>
                  <span className="font-medium">₱{p.amount.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No payments recorded yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Invoices</CardTitle>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              placeholder="Search invoice, receipt, patient, visit, doctor, reference..."
              value={q}
              onChange={(e) => { setQ(e.target.value); setLimit(PAGE_SIZE); }}
              className="sm:w-80"
            />
            <Select value={status} onChange={(e) => { setStatus(e.target.value as InvoiceStatus | ""); setLimit(PAGE_SIZE); }} className="sm:w-48">
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </Select>
            <RecordDateRangeFilter onApply={(range) => { setDateRange(range); setLimit(PAGE_SIZE); }} timeZone="Asia/Manila" />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <InvoiceTable items={data?.items ?? []} isLoading={isLoading} />
          {hasMore ? (
            <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm text-muted-foreground">
              <span>
                Showing {shownCount} of {data?.total}
              </span>
              <Button type="button" variant="outline" size="sm" onClick={() => setLimit((l) => l + PAGE_SIZE)}>
                Load more
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        {value === null || value === undefined ? (
          <Skeleton className="mt-1 h-7 w-16" />
        ) : (
          <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
        )}
      </CardContent>
    </Card>
  );
}
