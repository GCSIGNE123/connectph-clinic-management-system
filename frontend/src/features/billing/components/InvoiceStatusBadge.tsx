import { Badge } from "@/components/ui/badge";
import type { InvoiceStatus } from "@/features/billing/types";

const VARIANT_BY_STATUS: Record<InvoiceStatus, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  Draft: "outline",
  PendingPayment: "secondary",
  PartiallyPaid: "default",
  Paid: "success",
  Cancelled: "destructive",
};

const LABEL_BY_STATUS: Record<InvoiceStatus, string> = {
  Draft: "Draft",
  PendingPayment: "Pending Payment",
  PartiallyPaid: "Partially Paid",
  Paid: "Paid",
  Cancelled: "Cancelled",
};

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  return <Badge variant={VARIANT_BY_STATUS[status]}>{LABEL_BY_STATUS[status]}</Badge>;
}
