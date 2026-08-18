"use client";

import { PrintableDocumentDialog } from "@/features/clinical-orders/components/PrintableDocumentDialog";
import { LaboratoryReportView } from "@/features/laboratory/components/LaboratoryReportView";
import { useLaboratoryOrder } from "@/features/laboratory/hooks/use-laboratory";

/** Phase 4G: reuses the exact same generic print pipeline every other
 * printable document in this app already uses (Receipt, Queue Slip,
 * Prescription/Lab Request/Referral) - no new print subsystem, no PDF
 * library, just `PrintableDocumentDialog` wrapping the read-only
 * `LaboratoryReportView`.
 *
 * Fetches the order by id itself (rather than accepting an already-loaded
 * `LaboratoryOrder` prop) because `clinicName` is only populated by
 * `GET /laboratory/orders/{id}` (see that endpoint's Phase 4G note) - a
 * caller's own list-fetched order (`listForVisit`/`listForPatient`) never
 * has it. */
export function LaboratoryReportDialog({
  orderId,
  open,
  onOpenChange,
}: {
  orderId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: order } = useLaboratoryOrder(open ? orderId : null);

  return (
    <PrintableDocumentDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Laboratory Report"
      printableId="laboratory-report-printable"
    >
      {order ? <LaboratoryReportView order={order} /> : null}
    </PrintableDocumentDialog>
  );
}
