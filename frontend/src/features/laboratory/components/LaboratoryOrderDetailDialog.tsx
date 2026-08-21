"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { LaboratoryStatusBadge } from "@/features/laboratory/components/LaboratoryStatusBadge";
import { InterpretationBadge } from "@/features/laboratory/components/InterpretationBadge";
import { LaboratoryAttachmentList } from "@/features/laboratory/components/LaboratoryAttachmentList";
import { LaboratoryReportDialog } from "@/features/laboratory/components/LaboratoryReportDialog";
import type { LaboratoryOrder } from "@/features/laboratory/types";

// Exported so other laboratory-order list surfaces (e.g.
// `PatientLaboratoryHistory`) can gate their own "Print Results" actions
// against the exact same eligibility rule, rather than duplicating the
// literal set and risking drift.
export const REPORT_ELIGIBLE_STATUSES = new Set(["Completed", "Released"]);

/** Feature 5 Part B: read-only laboratory order details, opened by
 * clicking a row in the Patient's Visit History -> Visit Details
 * "Laboratory" card. Reuses `InterpretationBadge` (Feature 3) and
 * `LaboratoryAttachmentList` (Feature 4) exactly as `ResultEntryDialog`
 * does - same authenticated, permission-gated attachment preview, just in
 * a read-only surface instead of an edit one. Every field shown here is
 * already present on the `LaboratoryOrder` object the caller already
 * fetched via the same `GET /visits/{id}/laboratory` call the card uses -
 * no new data or permission surface is introduced. */
export function LaboratoryOrderDetailDialog({
  order,
  open,
  onOpenChange,
}: {
  order: LaboratoryOrder | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [reportOpen, setReportOpen] = useState(false);

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{order ? `${order.testType} - ${order.orderNumber ?? ""}` : ""}</DialogTitle>
        </DialogHeader>
        {order ? (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <LaboratoryStatusBadge status={order.status} />
                {order.priority ? <span className="text-xs text-muted-foreground">Priority: {order.priority}</span> : null}
              </div>
              {/* Phase 4G: the report is only meaningful once results are
                  final - gated on status, not on which test this is. */}
              {REPORT_ELIGIBLE_STATUSES.has(order.status) ? (
                <Button type="button" variant="outline" size="sm" onClick={() => setReportOpen(true)}>
                  Print Report
                </Button>
              ) : null}
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground">Results</p>
              {order.results.length > 0 ? (
                <ul className="mt-1 space-y-1">
                  {order.results.map((r) => (
                    <li key={r.id} className="flex items-center justify-between gap-2 border-b border-border/50 py-1 last:border-0">
                      <span>
                        {r.parameterName}: {r.resultType === "Numeric" ? r.numericValue : r.textValue}
                        {r.units ? ` ${r.units}` : ""}
                        {r.normalRange ? ` (Normal: ${r.normalRange})` : ""}
                      </span>
                      {r.interpretation ? <InterpretationBadge value={r.interpretation} /> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-muted-foreground">No results entered yet.</p>
              )}
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground">Attachments</p>
              <div className="mt-1">
                <LaboratoryAttachmentList attachments={order.attachments} />
              </div>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
    <LaboratoryReportDialog orderId={order?.id ?? null} open={reportOpen} onOpenChange={setReportOpen} />
    </>
  );
}
