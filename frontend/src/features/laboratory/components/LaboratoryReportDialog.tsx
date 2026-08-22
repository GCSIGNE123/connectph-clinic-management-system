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
    <>
      <PrintableDocumentDialog
        open={open}
        onOpenChange={onOpenChange}
        title="Laboratory Report"
        printableId="laboratory-report-printable"
        // Med-tech request: the Laboratory Report is designed specifically
        // for Short Bond / Letter (8.5 x 11in) portrait, using the full page
        // width for the five-column result table - not the clinic-wide
        // default (A4). Still overridable via the paper-size selector.
        defaultPaperSize="Letter"
      >
        {order ? <LaboratoryReportView order={order} /> : null}
      </PrintableDocumentDialog>

      {/* Round 2 (clinic-approved reference layout): print-only refinements
          scoped to this report's own printable id, layered on top of
          `PrintableDocumentDialog`'s shared full-width/Letter-portrait CSS
          rather than touching that shared component again -
          `-webkit-print-color-adjust`/`print-color-adjust` so the navy
          table-header band actually prints (browsers drop background
          colors by default to save ink unless told not to), plus
          pagination rules so a long result set breaks cleanly across
          Letter pages: the column header repeats on every page, a result
          row is never split across a page boundary, and a section heading
          is never left stranded alone at the bottom of one. */}
      <style jsx global>{`
        @media print {
          #laboratory-report-printable,
          #laboratory-report-printable * {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          #laboratory-report-printable thead {
            display: table-header-group;
          }
          #laboratory-report-printable .report-row {
            break-inside: avoid;
          }
          #laboratory-report-printable .section-heading {
            break-after: avoid;
          }
        }
      `}</style>
    </>
  );
}
