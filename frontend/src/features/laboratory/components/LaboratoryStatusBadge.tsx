import { Badge } from "@/components/ui/badge";
import type { LaboratoryOrderStatus } from "@/features/laboratory/types";

const VARIANT_BY_STATUS: Record<LaboratoryOrderStatus, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  Requested: "outline",
  Collected: "secondary",
  Processing: "default",
  Completed: "default",
  Released: "success",
  Cancelled: "destructive",
};

export function LaboratoryStatusBadge({ status }: { status: LaboratoryOrderStatus }) {
  return <Badge variant={VARIANT_BY_STATUS[status]}>{status}</Badge>;
}
