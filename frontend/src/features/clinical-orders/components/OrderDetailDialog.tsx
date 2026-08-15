"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { formatDate, formatDateTime } from "@/lib/utils";
import type { Order, OrderStatus } from "@/features/clinical-orders/types";

const STATUS_VARIANT: Record<OrderStatus, "default" | "secondary" | "success" | "destructive"> = {
  Requested: "secondary", Collected: "default", Processing: "default", Completed: "success", Cancelled: "destructive",
};

/** Feature 5 Part B: read-only order details, opened by clicking a row in
 * the Patient's Visit History -> Visit Details "Orders" card. Distinct
 * from `ClinicalOrdersTab`'s "Print" button (a Laboratory-Request print
 * slip, lab-category-only, needs clinic/doctor letterhead context) - this
 * is a generic detail view for any order category, built from fields
 * already present on the `Order` object the caller already fetched, so it
 * exposes nothing beyond what that caller could already see. */
export function OrderDetailDialog({
  order,
  open,
  onOpenChange,
}: {
  order: Order | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Order {order?.orderNumber ?? ""}</DialogTitle>
        </DialogHeader>
        {order ? (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{order.orderCategory}</Badge>
              <Badge variant={order.priority === "STAT" ? "destructive" : "secondary"}>{order.priority}</Badge>
              <Badge variant={STATUS_VARIANT[order.status]}>{order.status}</Badge>
            </div>
            <DetailRow label="Date" value={formatDateTime(order.createdAt)} />
            {order.scheduledDate ? <DetailRow label="Scheduled date" value={formatDate(order.scheduledDate)} /> : null}
            <div>
              <p className="text-xs font-medium text-muted-foreground">Items</p>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {order.items.map((item) => (
                  <li key={item.id}>
                    {item.itemName}
                    {item.examType ? ` — ${item.examType}${item.bodyPart ? ` (${item.bodyPart})` : ""}` : ""}
                    {item.clinicalIndication ? ` (${item.clinicalIndication})` : ""}
                  </li>
                ))}
              </ul>
            </div>
            {order.clinicalNotes ? (
              <div>
                <p className="text-xs font-medium text-muted-foreground">Clinical notes</p>
                <p className="mt-1">{order.clinicalNotes}</p>
              </div>
            ) : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}
