"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import type { Prescription } from "@/features/clinical-orders/types";

/** Feature 5 Part B: read-only prescription details, opened by clicking a
 * row in the Patient's Visit History -> Visit Details "Prescriptions"
 * card. Distinct from `PrescriptionTab`'s "Print" button (the full
 * clinic-letterhead prescription slip, which needs clinic branding and
 * the doctor's PRC/PTR numbers - context not available on the Visit
 * Details page) - this is a plain in-app detail view built entirely from
 * fields already present on the `Prescription` object the caller already
 * fetched. */
export function PrescriptionDetailDialog({
  prescription,
  open,
  onOpenChange,
}: {
  prescription: Prescription | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Prescription {prescription?.prescriptionNumber ?? ""}</DialogTitle>
        </DialogHeader>
        {prescription ? (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={prescription.status === "Finalized" ? "success" : "secondary"}>{prescription.status}</Badge>
              <span className="text-xs text-muted-foreground">{new Date(prescription.createdAt).toLocaleString()}</span>
            </div>
            <div className="space-y-2">
              {prescription.items.map((item, i) => (
                <div key={item.id} className="rounded-md border border-border p-2">
                  <p className="font-medium">
                    {i + 1}. {item.medicine}
                    {item.strength ? ` ${item.strength}` : ""}
                  </p>
                  <p className="text-muted-foreground">
                    {[item.dosage, item.route, item.frequency, item.duration ? `for ${item.duration}` : null, item.quantity ? `Qty: ${item.quantity}` : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  {item.instructions ? <p className="text-muted-foreground">Sig: {item.instructions}</p> : null}
                  {!item.substitutionAllowed ? <p className="text-xs italic text-muted-foreground">No generic substitution</p> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
