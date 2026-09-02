"use client";

import { createPortal } from "react-dom";
import { PrintableDocumentDialog } from "@/features/clinical-orders/components/PrintableDocumentDialog";
import { LaboratoryReportView } from "@/features/laboratory/components/LaboratoryReportView";
import { useLaboratoryOrder } from "@/features/laboratory/hooks/use-laboratory";
import { buildLaboratoryReportFilename } from "@/features/laboratory/lib/report-filename";
import type { LaboratoryOrder } from "@/features/laboratory/types";

/** Bug fix (duplicate 2-page print/PDF output): a print-only copy of the
 * report, portaled directly onto `document.body` (a sibling of the app
 * root, not nested inside the dialog's own DOM subtree) - the exact same
 * proven pattern `QueueSlipPrintPortal` already established for this
 * codebase's other `visibility: hidden` + `position: fixed` print bug
 * (see that component's own doc comment).
 *
 * `PrintableDocumentDialog`'s shared print CSS hides the rest of the page
 * with `visibility: hidden` (not `display: none`, which would also hide
 * the printable element - its own descendant - beyond any hope of a
 * descendant re-declaring `visibility: visible`). `visibility: hidden`
 * does NOT remove content from LAYOUT, though - the real page behind the
 * dialog (e.g. the Laboratory worklist's own table, or a patient's
 * Laboratory History table) still occupies its full height. The printable
 * element is also `position: fixed` (needed so it prints at the page
 * origin rather than wherever it happens to sit nested deep in that
 * hidden tree) - and per CSS Paged Media, a `fixed` box is REPEATED on
 * EVERY page a print job spans, the same mechanism used for a running
 * header/footer. Combined: whenever the hidden background page is tall
 * enough to force a second physical print page to exist for ANY reason
 * (worklist row count, print-margin/DPI rounding, paper-size choice - not
 * just "the report is too long"), the fixed report reprints itself onto
 * that extra page, byte-for-byte identical to page 1. An earlier attempt
 * at fixing this collapsed `<html>`/`<body>` to zero height at print time
 * instead of removing the `visibility`+`fixed` mechanism - insufficient,
 * since collapsing height doesn't change the fact that ANY additional
 * print page still repeats the fixed element.
 *
 * The actual fix: stop relying on `visibility`+`fixed` at all. Once this
 * portaled copy is a genuine direct child of `<body>`, `@media print` can
 * hide every OTHER direct child of `<body>` with `display: none` (which
 * DOES remove content from layout, unlike `visibility`) and force-hide the
 * original in-dialog printable element too - the only thing left in flow
 * for the browser to paginate is this portal's own (one-page-tall) content,
 * rendered normally (no `position: fixed`), so it can never repeat.
 *
 * Follow-up (caught by an actual Print -> Save as PDF -> Adobe Reader
 * check, not just DOM/layout inspection): the shared component's own
 * `body * { visibility: hidden }` rule still applies to this portal and
 * every descendant of it - it only ever re-declares `visibility: visible`
 * for the OLD (now `display: none`-d) printable id, never for this new
 * one. Left unaddressed, that produced a real, confirmed symptom: exactly
 * one PDF page (the duplication WAS fixed), but a completely blank one -
 * `display: block` gives an element correct layout/pagination without
 * making it visible; `visibility: hidden` still paints nothing. See the
 * `visibility: visible !important` rule for `#laboratory-report-print-root`
 * in the stylesheet below, which overrides that inherited hidden state. */
function LaboratoryReportPrintPortal({ order }: { order: LaboratoryOrder }) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <div id="laboratory-report-print-root">
      <LaboratoryReportView order={order} />
    </div>,
    document.body
  );
}

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
        // Client request: default "Save as PDF" filename of
        // "<Patient_Name>-<last 4 Order # digits>.pdf" - read from the
        // exact same already-fetched order the report body itself renders
        // (never Visit #/Queue #, never a separate fetch); undefined while
        // the order hasn't loaded yet, which PrintableDocumentDialog
        // treats identically to omitting the prop (falls back to
        // document.title, unchanged from before this feature).
        printFilename={order ? buildLaboratoryReportFilename(order.patientName, order.orderNumber) : undefined}
      >
        {order ? <LaboratoryReportView order={order} /> : null}
      </PrintableDocumentDialog>

      {/* Print-only: the actual printed/PDF'd content comes from this
          portaled copy, not the on-screen preview above - see
          `LaboratoryReportPrintPortal`'s doc comment. Rendered whenever an
          order is loaded (same convention as `QueueSlipPrintPortal`) -
          `display: none` on screen (below) makes it invisible/inert
          outside of `@media print` regardless of the dialog's own
          `open` state. */}
      {order ? <LaboratoryReportPrintPortal order={order} /> : null}

      {/* Round 2 (clinic-approved reference layout): print-only refinements
          now scoped to the portaled print root (`#laboratory-report-print-
          root`) rather than the on-screen preview's id - see the bug-fix
          doc comment above `LaboratoryReportPrintPortal` for why the
          on-screen preview element is no longer what gets printed.
          `-webkit-print-color-adjust`/`print-color-adjust` so the navy
          table-header band actually prints (browsers drop background
          colors by default to save ink unless told not to), plus
          pagination rules so a long result set breaks cleanly across
          Letter pages: the column header repeats on every page, a result
          row is never split across a page boundary, and a section heading
          is never left stranded alone at the bottom of one. */}
      <style jsx global>{`
        /* Invisible on screen - only ever shown under @media print below.
           display: none (not visibility) so it never occupies on-screen
           layout space or gets included in the app's normal scroll flow. */
        #laboratory-report-print-root {
          display: none;
        }
        /* Round 9 (true page footer, on-screen preview): scoped to this
           printableId only (unique to the Laboratory Report - every other
           document type this shared PrintableDocumentDialog renders uses
           its own id, e.g. "prescription-printable"), so this never
           touches Prescription/Referral/Lab Request/Medical Certificate's
           own preview boxes. Turns the shared preview box into a flex
           column so LaboratoryReportView's own root (a flex child with
           flex-1) can stretch to the box's full (at-least-one-page)
           height, giving the signatory footer's margin-top:auto real
           leftover space to push into. The box's existing inline
           width/min-height and overflow-auto (from PrintableDocumentDialog)
           are untouched - this only adds display:flex +
           flex-direction:column, which doesn't change the box's own
           sizing, only how its single child is laid out inside it. */
        #laboratory-report-printable {
          display: flex;
          flex-direction: column;
        }
        @media print {
          /* The on-screen preview's printable element must never ALSO
             render during print - only the portaled copy above does now.
             display: none unconditionally wins over the shared
             PrintableDocumentDialog's own visibility: visible rule for
             this same id (no descendant can override display: none). */
          #laboratory-report-printable {
            display: none !important;
          }
          /* #laboratory-report-print-root is a direct child of body
             (portaled there via createPortal, a sibling of the app root).
             Hiding every OTHER direct child of body with display: none
             removes them from the flow entirely, so the only in-flow
             content left to measure the printed page against is the
             report itself - no visibility + fixed-position workaround
             needed, and nothing can repeat across an extra page since
             nothing forces an extra page to exist. */
          body > *:not(#laboratory-report-print-root) {
            display: none !important;
          }
          /* Round 9 (true page footer, print/PDF): display:flex +
             flex-direction:column (rather than plain block) lets
             LaboratoryReportView's root - a flex child with flex-1 -
             stretch to fill this box, exactly like the on-screen preview
             above, so the signatory footer's margin-top:auto has real
             leftover height to push into here too. min-height: 100vh is
             what supplies that height in the printed/PDF output: in print
             media, Chromium (the engine this codebase's own print/PDF
             testing already targets - see the doc comment above this
             component) resolves viewport units against the @page box set
             by PrintableDocumentDialog's own "@page { size: ...; margin:
             12mm; }" rule, so 100vh here means one page's printable height
             for whichever paper size is selected - not a fixed pixel
             value. This is a MINIMUM, not a fixed height: a report whose
             content genuinely exceeds one page still grows taller than
             100vh and paginates normally onto a second physical page (the
             browser's own pagination, untouched) - this rule never forces
             an extra page for a report that already fits, and never
             clips/hides overflow content (no max-height, no
             overflow:hidden anywhere here). */
          #laboratory-report-print-root {
            display: flex !important;
            flex-direction: column;
            width: 100%;
            min-height: 100vh;
          }
          /* The shared PrintableDocumentDialog's own print CSS sets
             "body * { visibility: hidden }" and only re-declares
             "visibility: visible" for the OLD #laboratory-report-printable
             id (now force-hidden above via display: none). Without this
             rule, this portaled root inherits that blanket
             visibility: hidden - it gets correct display:block LAYOUT
             (so pagination is correct, one page), but paints nothing,
             producing an entirely blank printed/PDF page. Confirmed via a
             real Print -> Save as PDF -> Adobe Reader check: 1 page, but
             blank, before this rule was added. */
          #laboratory-report-print-root,
          #laboratory-report-print-root * {
            visibility: visible !important;
          }
          #laboratory-report-print-root,
          #laboratory-report-print-root * {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          #laboratory-report-print-root thead {
            display: table-header-group;
          }
          #laboratory-report-print-root .report-row {
            break-inside: avoid;
          }
          #laboratory-report-print-root .section-heading {
            break-after: avoid;
          }
        }
      `}</style>
    </>
  );
}
