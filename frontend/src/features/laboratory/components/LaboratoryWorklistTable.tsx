"use client";

import { useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { LaboratoryStatusBadge } from "@/features/laboratory/components/LaboratoryStatusBadge";
import { ResultEntryDialog } from "@/features/laboratory/components/ResultEntryDialog";
import { useCollectSpecimen, useStartProcessing, useReleaseResults } from "@/features/laboratory/hooks/use-laboratory";
import { nextActionFor } from "@/features/laboratory/types";
import type { LaboratoryOrder } from "@/features/laboratory/types";
import { formatDate } from "@/lib/utils";

interface LaboratoryWorklistTableProps {
  orders: LaboratoryOrder[];
  isLoading?: boolean;
  canManage?: boolean;
}

export function LaboratoryWorklistTable({ orders, isLoading, canManage = true }: LaboratoryWorklistTableProps) {
  const [resultOrder, setResultOrder] = useState<LaboratoryOrder | null>(null);
  const collect = useCollectSpecimen();
  const startProcessing = useStartProcessing();
  const release = useReleaseResults();

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
                  <TableCell className="text-right">
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
                      <Button size="sm" onClick={() => release.mutate(order.id)} disabled={release.isPending}>
                        {action.label}
                      </Button>
                    )}
                    {!action && <span className="text-xs text-muted-foreground">-</span>}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <ResultEntryDialog order={resultOrder} open={resultOrder !== null} onOpenChange={(open) => !open && setResultOrder(null)} />
    </>
  );
}
