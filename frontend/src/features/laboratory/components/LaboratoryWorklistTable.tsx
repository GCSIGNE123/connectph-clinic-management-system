"use client";

import { useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { LaboratoryStatusBadge } from "@/features/laboratory/components/LaboratoryStatusBadge";
import { ResultEntryDialog } from "@/features/laboratory/components/ResultEntryDialog";
import { LaboratoryReportDialog } from "@/features/laboratory/components/LaboratoryReportDialog";
import { ReleaseResultsDialog } from "@/features/laboratory/components/ReleaseResultsDialog";
import { REPORT_ELIGIBLE_STATUSES } from "@/features/laboratory/components/LaboratoryOrderDetailDialog";
import { useCollectSpecimen, useStartProcessing } from "@/features/laboratory/hooks/use-laboratory";
import { nextActionFor } from "@/features/laboratory/types";
import type { LaboratoryOrder } from "@/features/laboratory/types";
import { formatDate } from "@/lib/utils";

interface LaboratoryWorklistTableProps {
  orders: LaboratoryOrder[];
  isLoading?: boolean;
  canManage?: boolean;
}

/** Direct "Print Results" from the worklist (previously only reachable via
 * Patient profile -> Laboratory History) - reuses the exact same
 * `REPORT_ELIGIBLE_STATUSES` gate and `LaboratoryReportDialog` ->
 * `LaboratoryReportView` -> `PrintableDocumentDialog` pipeline that
 * `PatientLaboratoryHistory` already uses, so there is only ever one
 * report renderer. `printOrderId` (not the full order) is all
 * `LaboratoryReportDialog` needs - it re-fetches `GET
 * /laboratory/orders/{id}` itself, which is the only call site that
 * populates `clinicName` for the report header. */
export function LaboratoryWorklistTable({ orders, isLoading, canManage = true }: LaboratoryWorklistTableProps) {
  const [resultOrder, setResultOrder] = useState<LaboratoryOrder | null>(null);
  const [printOrderId, setPrintOrderId] = useState<string | null>(null);
  const [releaseOrderId, setReleaseOrderId] = useState<string | null>(null);
  const collect = useCollectSpecimen();
  const startProcessing = useStartProcessing();

  if (isLoading) {
    return (
      <div className="space-y-2 p-4">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <EmptyState
        title="No laboratory orders"
        description="Orders placed by doctors, and walk-in Laboratory queue tickets, will appear here."
      />
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Order #</TableHead>
            <TableHead>Queue #</TableHead>
            <TableHead>Visit #</TableHead>
            <TableHead>Patient</TableHead>
            <TableHead>Doctor</TableHead>
            <TableHead>Test</TableHead>
            <TableHead>Priority</TableHead>
            <TableHead>Requested</TableHead>
            <TableHead>Status</TableHead>
            {canManage && <TableHead className="text-right">Actions</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {orders.map((order) => {
            const action = nextActionFor(order.status);
            return (
              <TableRow key={order.id}>
                <TableCell className="font-medium">{order.orderNumber ?? "-"}</TableCell>
                <TableCell>{order.queueNumber ?? "-"}</TableCell>
                <TableCell>{order.visitNumber ?? "-"}</TableCell>
                <TableCell>{order.patientName ?? "-"}</TableCell>
                <TableCell>{order.doctorName ?? "-"}</TableCell>
                <TableCell>{order.testType}</TableCell>
                <TableCell>{order.priority ?? "-"}</TableCell>
                <TableCell>{formatDate(order.createdAt)}</TableCell>
                <TableCell>
                  <LaboratoryStatusBadge status={order.status} />
                </TableCell>
                {canManage && (
                  <TableCell className="space-x-1 text-right">
                    {action?.action === "collect" && (
                      <Button size="sm" onClick={() => collect.mutate(order.id)} disabled={collect.isPending}>
                        {action.label}
                      </Button>
                    )}
                    {action?.action === "process" && (
                      <Button size="sm" onClick={() => startProcessing.mutate(order.id)} disabled={startProcessing.isPending}>
                        {action.label}
                      </Button>
                    )}
                    {action?.action === "results" && (
                      <Button size="sm" onClick={() => setResultOrder(order)}>
                        {action.label}
                      </Button>
                    )}
                    {action?.action === "release" && (
                      <Button size="sm" onClick={() => setReleaseOrderId(order.id)}>
                        {action.label}
                      </Button>
                    )}
                    {REPORT_ELIGIBLE_STATUSES.has(order.status) && (
                      <Button variant="ghost" size="sm" onClick={() => setPrintOrderId(order.id)}>
                        Print Results
                      </Button>
                    )}
                    {!action && !REPORT_ELIGIBLE_STATUSES.has(order.status) && (
                      <span className="text-xs text-muted-foreground">-</span>
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <ResultEntryDialog order={resultOrder} open={resultOrder !== null} onOpenChange={(open) => !open && setResultOrder(null)} />
      <LaboratoryReportDialog orderId={printOrderId} open={printOrderId !== null} onOpenChange={(open) => !open && setPrintOrderId(null)} />
      <ReleaseResultsDialog
        laboratoryOrderId={releaseOrderId}
        open={releaseOrderId !== null}
        onOpenChange={(open) => !open && setReleaseOrderId(null)}
      />
    </>
  );
}
