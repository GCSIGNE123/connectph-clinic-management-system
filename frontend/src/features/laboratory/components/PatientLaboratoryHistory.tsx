"use client";

import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { useLaboratoryForPatient } from "@/features/laboratory/hooks/use-laboratory";
import { LaboratoryStatusBadge } from "@/features/laboratory/components/LaboratoryStatusBadge";
import { InterpretationBadge } from "@/features/laboratory/components/InterpretationBadge";
import { formatDate } from "@/lib/utils";

/** Patient Profile "Laboratory" tab (Phase 10) - read-only history of every
 * laboratory order/result across all of the patient's visits, mirroring
 * `PatientPrescriptionsHistory`'s shape. */
export function PatientLaboratoryHistory({ patientId }: { patientId: string }) {
  const { data: labOrders, isLoading } = useLaboratoryForPatient(patientId);

  if (isLoading) return <SkeletonList rows={3} />;
  if (!labOrders || labOrders.length === 0) {
    return <EmptyState title="No laboratory orders yet" description="Laboratory orders for this patient will appear here." />;
  }

  return (
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
