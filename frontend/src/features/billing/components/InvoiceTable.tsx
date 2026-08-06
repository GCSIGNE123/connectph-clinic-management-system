"use client";

import { useRouter } from "next/navigation";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { InvoiceStatusBadge } from "@/features/billing/components/InvoiceStatusBadge";
import type { InvoiceListItem } from "@/features/billing/types";

export function InvoiceTable({ items, isLoading }: { items: InvoiceListItem[]; isLoading: boolean }) {
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return <EmptyState title="No invoices found" description="No invoices match the current search or filters." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Invoice #</TableHead>
          <TableHead>Patient</TableHead>
          <TableHead>Visit #</TableHead>
          <TableHead>Doctor</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Total</TableHead>
          <TableHead className="text-right">Balance</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((inv) => (
          <TableRow key={inv.id} className="cursor-pointer" onClick={() => router.push(`/billing/${inv.id}`)}>
            <TableCell className="font-medium">{inv.invoiceNumber}</TableCell>
            <TableCell>{inv.patientName ?? "-"}</TableCell>
            <TableCell>{inv.visitNumber ?? "-"}</TableCell>
            <TableCell>{inv.doctorName ?? "-"}</TableCell>
            <TableCell>{inv.invoiceDate}</TableCell>
            <TableCell>
              <InvoiceStatusBadge status={inv.status} />
            </TableCell>
            <TableCell className="text-right">₱{inv.grandTotal.toFixed(2)}</TableCell>
            <TableCell className="text-right">₱{inv.balanceDue.toFixed(2)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
