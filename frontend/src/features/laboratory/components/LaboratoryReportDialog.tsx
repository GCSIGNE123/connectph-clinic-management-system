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
          is never left stranded alone at the bottom of one.

          Bug fix (duplicate 2-page output): `PrintableDocumentDialog`'s
          shared print CSS hides the rest of the page with `visibility:
          hidden` (not `display: none`) so the printable element - a
          DESCENDANT of that hidden subtree - can re-declare `visibility:
          visible` on itself (a `display: none` ancestor can never be
          un-hidden by a descendant, which is why the shared component
          doesn't use it). `visibility: hidden` does NOT remove an element
          from layout, though - the entire page behind the dialog (e.g. a
          long Laboratory worklist table) still occupies its full height,
          so the printed document's total height can exceed one physical
          page even though the report itself fits on one. The printable
          element is `position: fixed` (needed so it stays pinned at the
          page origin rather than printing wherever it happens to sit deep
          in that hidden tree) - and a `fixed` box is REPEATED on every
          page a print job spans, per the CSS Paged Media behavior used for
          running headers/footers. Combined, those two facts are the exact
          root cause: an oversized hidden background page forces a second
          print page to exist, and the fixed report reprints itself onto
          that extra page.

          Fix: collapse `<html>`/`<body>` to zero height at print time so
          the hidden background content no longer contributes any page
          height. This is safe specifically because the one `position:
          fixed` ancestor already between `<body>` and this printable div
          (the plain custom `Dialog`'s own full-viewport overlay wrapper -
          see `components/ui/dialog.tsx`) is,  by definition, positioned
          relative to the page/viewport, not clipped by an ancestor's
          `height`/`overflow` - so the report keeps rendering exactly as
          before while the excess page is gone. Scoped with `:has(...)` to
          only apply while THIS report's printable element actually exists
          in the DOM (i.e. only while this dialog is open and mid-print) -
          `html`/`body` are otherwise global elements, so this must never
          affect Receipt/Queue Slip/Prescription/Referral/Lab Request
          printing, which use the exact same shared `PrintableDocumentDialog`
          but a different `printableId` and are never open at the same
          time as this dialog. */}
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
          html:has(#laboratory-report-printable),
          body:has(#laboratory-report-printable) {
            height: 0 !important;
            overflow: hidden !important;
          }
        }
      `}</style>
    </>
  );
}
