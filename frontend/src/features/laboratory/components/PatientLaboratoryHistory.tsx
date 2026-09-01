"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { useLaboratoryForPatient } from "@/features/laboratory/hooks/use-laboratory";
import { LaboratoryStatusBadge } from "@/features/laboratory/components/LaboratoryStatusBadge";
import { InterpretationBadge } from "@/features/laboratory/components/InterpretationBadge";
import { LaboratoryOrderDetailDialog, REPORT_ELIGIBLE_STATUSES } from "@/features/laboratory/components/LaboratoryOrderDetailDialog";
import { LaboratoryReportDialog } from "@/features/laboratory/components/LaboratoryReportDialog";
import type { LaboratoryOrder } from "@/features/laboratory/types";
import { formatDate } from "@/lib/utils";

/** Patient Profile "Laboratory" tab (Phase 10) - read-only history of every
 * laboratory order/result across all of the patient's visits, mirroring
 * `PatientPrescriptionsHistory`'s shape.
 *
 * Reprint (new): each row gets a "View" action (opens the same
 * `LaboratoryOrderDetailDialog` used from Visit History, whose own "Print
 * Report" button is already gated to Completed/Released) and, for rows
 * already eligible, a direct "Print Results" shortcut straight into
 * `LaboratoryReportDialog` - both routes end at the exact same print
 * pipeline (`LaboratoryReportDialog` -> `LaboratoryReportView` ->
 * `PrintableDocumentDialog`), no second implementation. Printing re-fetches
 * `GET /laboratory/orders/{id}`, which returns this specific order's own
 * persisted `LaboratoryResult` rows (already-captured units/normal range/
 * interpretation) - never the current template/reference-range config, so
 * a later template edit can't change what an old printed report shows. */
export function PatientLaboratoryHistory({ patientId }: { patientId: string }) {
  const [dateRange, setDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({});
  const { data: labOrders, isLoading } = useLaboratoryForPatient(patientId, dateRange);
  const [selected, setSelected] = useState<LaboratoryOrder | null>(null);
  const [printOrderId, setPrintOrderId] = useState<string | null>(null);

  if (isLoading) return <SkeletonList rows={3} />;
  if (!labOrders || labOrders.length === 0) {
    return (
      <div className="space-y-3">
        <RecordDateRangeFilter onApply={setDateRange} />
        <EmptyState title="No laboratory orders yet" description="Laboratory orders for this patient will appear here." />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <RecordDateRangeFilter onApply={setDateRange} />
      <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Order #</th>
            <th className="px-3 py-2">Test</th>
            <th className="px-3 py-2">Doctor</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Results</th>
            <th className="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {labOrders.map((lo) => (
            <tr key={lo.id} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-2 whitespace-nowrap">{formatDate(lo.createdAt)}</td>
              <td className="px-3 py-2 font-mono text-xs">{lo.orderNumber ?? "-"}</td>
              <td className="px-3 py-2">{lo.testType}</td>
              <td className="px-3 py-2 text-muted-foreground">{lo.doctorName ?? "-"}</td>
              <td className="px-3 py-2">
                <LaboratoryStatusBadge status={lo.status} />
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {lo.results.length > 0 ? (
                  <ul className="space-y-1">
                    {lo.results.map((r) => (
                      <li key={r.id} className="flex items-center gap-2 whitespace-nowrap">
                        <span>
                          {r.parameterName}: {r.resultType === "Numeric" ? r.numericValue : r.textValue}
                        </span>
                        {r.interpretation && <InterpretationBadge value={r.interpretation} />}
                      </li>
                    ))}
                  </ul>
                ) : (
                  "-"
                )}
              </td>
              <td className="px-3 py-2 whitespace-nowrap">
                <Button type="button" variant="ghost" size="sm" onClick={() => setSelected(lo)}>
                  View
                </Button>
                {REPORT_ELIGIBLE_STATUSES.has(lo.status) ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setPrintOrderId(lo.id)}>
                    Print Results
                  </Button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <LaboratoryOrderDetailDialog order={selected} open={selected !== null} onOpenChange={(open) => !open && setSelected(null)} />
      <LaboratoryReportDialog orderId={printOrderId} open={printOrderId !== null} onOpenChange={(open) => !open && setPrintOrderId(null)} />
      </div>
    </div>
  );
}
