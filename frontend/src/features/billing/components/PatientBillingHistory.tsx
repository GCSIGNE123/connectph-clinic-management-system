"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { InvoiceStatusBadge } from "@/features/billing/components/InvoiceStatusBadge";
import { useBillingHistory } from "@/features/billing/hooks/use-invoices";
import { formatDate } from "@/lib/utils";

/** Real "Billing History" tab for the Patient Profile page (Phase 9),
 * replacing the Phase 3 "coming soon" placeholder. */
export function PatientBillingHistory({ patientId }: { patientId: string }) {
  const router = useRouter();
  const [dateRange, setDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({});
  const { data: items, isLoading } = useBillingHistory(patientId, dateRange);

  if (isLoading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="space-y-3">
        <RecordDateRangeFilter onApply={setDateRange} />
        <EmptyState title="No billing history" description="This patient has no invoices yet." />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <RecordDateRangeFilter onApply={setDateRange} />
      <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Invoice #</TableHead>
          <TableHead>Visit #</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Amount</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id} className="cursor-pointer" onClick={() => router.push(`/billing/${item.id}`)}>
            <TableCell className="font-medium">{item.invoiceNumber}</TableCell>
            <TableCell>{item.visitNumber ?? "-"}</TableCell>
            <TableCell>{formatDate(item.invoiceDate)}</TableCell>
            <TableCell>
              <InvoiceStatusBadge status={item.status} />
            </TableCell>
            <TableCell className="text-right">₱{item.grandTotal.toFixed(2)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
      </Table>
    </div>
  );
}
