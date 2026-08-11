"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { queueApi } from "@/features/queue/api/queue-api";
import { queueKeys } from "@/features/queue/hooks/use-queues";
import { QUEUE_PRIORITY_LABELS } from "@/features/queue/types";
import { ApiError } from "@/lib/api-client";

export interface QueueSlipDialogProps {
  queueId: string | null;
  onOpenChange: (open: boolean) => void;
}

/** Locale-default (browser/clinic setting, not hardcoded) date + time,
 * without the seconds or the comma `toLocaleString()` includes by default -
 * matches the compact single-line format a thermal ticket needs (e.g.
 * "8/11/2026 8:58 AM"). No explicit locale argument, same as every other
 * date/time display in this app - it follows whatever locale the browser
 * (and thus the clinic's own machine) is configured for. */
function formatSlipDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
}

/** One label/value line on the ticket. The value truncates with an ellipsis
 * rather than wrapping - a long patient/department/doctor name should never
 * grow the ticket's height (thermal rolls should cut right after the
 * content, not after however many lines a very long name happens to wrap
 * into), and the label must never be the part that gets truncated. */
function SlipField({ label, value }: { label: string; value: string }) {
  return (
    <p className="flex gap-1">
      <span className="shrink-0 text-muted-foreground">{label}:</span>
      <span className="min-w-0 flex-1 truncate" title={value}>
        {value}
      </span>
    </p>
  );
}

/**
 * Printable queue slip - clinic name, branch, queue number, priority,
 * patient/department/doctor, date/time, "Thank you!" footer. Deliberately
 * does not print the internal patient/queue UUID or the `qrToken` field
 * (still present on the `QueueSlip` API response, just not rendered here) -
 * a patient's paper ticket should carry nothing that identifies a database
 * row.
 *
 * Print layout is a dedicated 80mm-thermal `@page` rule (not the generic
 * `PrintableDocumentDialog`/Printer Settings paper-size selector other
 * documents use) - a queue ticket is always printed on the reception
 * counter's thermal receipt printer (e.g. POS-80), never A4/Letter, so
 * there's no paper-size choice to offer here. See the `<style jsx global>`
 * block below for the full rationale on each rule.
 */
export function QueueSlipDialog({ queueId, onOpenChange }: QueueSlipDialogProps) {
  const {
    data: slip,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: queueId ? queueKeys.slip(queueId) : ["queue", "slip", "none"],
    queryFn: () => queueApi.getSlip(queueId as string),
    enabled: Boolean(queueId),
    // Feature 1 (Reception Queue Workflow Improvements): a missing-vitals
    // rejection is not a transient failure - retrying it just re-triggers
    // the same 400, so don't burn TanStack Query's default retries on it.
    retry: false,
  });

  // Real backend enforcement (see `QueueService.get_slip`), not just a
  // disabled Print button - the slip request itself is rejected with 400
  // when required vitals are missing, and that's surfaced here instead of
  // ever rendering a printable ticket.
  const blockedMessage =
    isError && error instanceof ApiError
      ? error.message || "Vital signs must be taken before printing the queue ticket."
      : isError
        ? "Vital signs must be taken before printing the queue ticket."
        : null;

  return (
    <Dialog open={Boolean(queueId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Queue Slip</DialogTitle>
        </DialogHeader>

        {blockedMessage ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{blockedMessage}</p>
          </div>
        ) : isLoading || !slip ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div id="queue-slip-printable" className="space-y-2 rounded-md border border-border p-4 text-center">
            <p className="truncate text-base font-bold uppercase">{slip.clinicName}</p>
            <p className="truncate text-sm">{slip.branchName}</p>
            <p className="py-1 text-6xl font-extrabold tracking-wide">{slip.queueNumber}</p>
            <p className="text-sm font-semibold uppercase tracking-wide">{QUEUE_PRIORITY_LABELS[slip.priority]}</p>
            <div className="border-t border-dashed border-border" />
            <div className="space-y-1.5 pt-2 text-left text-sm">
              <SlipField label="Patient" value={slip.patientName} />
              <SlipField label="Department" value={slip.departmentName} />
              <SlipField label="Doctor" value={slip.doctorName ?? "Unassigned"} />
              <p>
                <span className="text-muted-foreground">Date: </span>
                {formatSlipDateTime(slip.createdAt)}
              </p>
            </div>
            {/* Feature 2: a small, secondary confirmation line - deliberately
                not styled to compete with the large queue number above it. */}
            {slip.vitalsTaken ? <p className="pt-1 text-xs font-semibold tracking-wide text-muted-foreground">VITALS TAKEN</p> : null}
            <p className="pt-2 text-sm font-medium">Thank you!</p>
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button type="button" onClick={() => window.print()} disabled={!slip || Boolean(blockedMessage)}>
            Print
          </Button>
        </DialogFooter>
      </DialogContent>

      <style jsx global>{`
        /* 80mm thermal roll (e.g. POS-80). Height is auto, not a fixed
           length like A4/Letter - a receipt printer's roll has no fixed
           page length, so the browser should paginate to exactly however
           tall the ticket content is, not a forced 210mm/11in page with
           blank space below. Zero page margin is required for the width
           below to actually reach 80mm (a nonzero @page margin shrinks
           the usable area) and is also the standard way to starve
           Chrome's built-in print header/footer (URL/title/date/page
           number) of the margin space it renders into - there is no CSS
           property that force-disables that browser-chrome UI directly,
           so this is the closest a print stylesheet can get without
           relying on the user manually unchecking "Headers and footers"
           in the OS print dialog.

           Deliberately declared at the STYLESHEET TOP LEVEL, not nested
           inside \`@media print\` (both are valid CSS, but real hardware
           testing found a difference): some Windows thermal-printer print
           pipelines negotiate the physical paper size with the OS/driver
           before Chrome finishes evaluating conditional (\`@media\`-nested)
           rules, so a nested \`@page\` was sometimes not honored in time -
           the driver would fall back to its own default paper profile
           (typically A4/Letter-shaped), and since our ticket content is
           only ~1-2 inches tall, the printer would feed the rest of that
           much taller default page as blank BEFORE ejecting/cutting,
           rather than starting the next print job immediately after the
           short ticket. \`@page\` only ever applies to paginated/print
           output regardless of nesting, so hoisting it here changes
           nothing for on-screen rendering. */
        @page {
          size: 80mm auto;
          margin: 0;
        }
        @media print {
          /* The dialog/app shell behind the ticket is hidden via the
             visibility property (not display: none) so hiding it doesn't
             also hide the printable ticket nested inside the same DOM
             subtree - but visibility: hidden still reserves layout space,
             so the full (very tall) app shell would otherwise still
             determine the page's content height under an auto-height
             @page, producing extra blank pages below the ticket.
             Collapsing the body element itself to zero height with
             overflow hidden fixes that: the ticket, positioned fixed
             (viewport-relative, not clipped by an ancestor's overflow),
             still renders correctly on top. */
          html,
          body {
            margin: 0 !important;
            padding: 0 !important;
          }
          body {
            height: 0 !important;
            overflow: hidden !important;
          }
          body * {
            visibility: hidden;
          }
          #queue-slip-printable,
          #queue-slip-printable * {
            visibility: visible;
          }
          #queue-slip-printable {
            position: fixed;
            top: 0;
            left: 0;
            /* Matches the @page width exactly; the printer's own
               unprintable edge margin is accounted for with inner padding
               (below) rather than an @page margin (which must stay 0 -
               see above), so content never touches the physical edge of
               the roll. */
            width: 80mm;
            margin: 0;
            padding: 3mm;
            box-sizing: border-box;
            border: none;
            box-shadow: none;
            background: #fff;
            color: #000;
          }
        }
      `}</style>
    </Dialog>
  );
}
