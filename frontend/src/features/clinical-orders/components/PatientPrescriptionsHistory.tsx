"use client";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { usePrescriptionsForPatient } from "@/features/clinical-orders/hooks/use-clinical-orders";
import { formatDate } from "@/lib/utils";

/** Patient Profile "Prescriptions" tab (Phase 9) - read-only history across
 * all of the patient's visits, per spec: Date/Doctor/Visit/Medicine/Status. */
export function PatientPrescriptionsHistory({ patientId }: { patientId: string }) {
  const { data: prescriptions, isLoading } = usePrescriptionsForPatient(patientId);

  if (isLoading) return <SkeletonList rows={3} />;
  if (!prescriptions || prescriptions.length === 0) {
    return <EmptyState title="No prescriptions yet" description="Prescriptions written for this patient will appear here." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Prescription #</th>
            <th className="px-3 py-2">Medicines</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {prescriptions.map((rx) => (
            <tr key={rx.id} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-2 whitespace-nowrap">{formatDate(rx.createdAt)}</td>
              <td className="px-3 py-2 font-mono text-xs">{rx.prescriptionNumber}</td>
              <td className="px-3 py-2 text-muted-foreground">{rx.items.map((i) => i.medicine).join(", ")}</td>
              <td className="px-3 py-2">
                <Badge variant={rx.status === "Finalized" ? "success" : "secondary"}>{rx.status}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
