import { Badge } from "@/components/ui/badge";
import { VISIT_STATUS_LABELS, VisitStatus } from "@/features/visits/types";

const VARIANT_BY_STATUS: Record<VisitStatus, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  [VisitStatus.Registered]: "outline",
  [VisitStatus.Waiting]: "secondary",
  [VisitStatus.Called]: "default",
  [VisitStatus.InConsultation]: "default",
  [VisitStatus.Completed]: "success",
  [VisitStatus.Cancelled]: "destructive",
  [VisitStatus.NoShow]: "destructive",
  [VisitStatus.DraftVitals]: "outline",
};

export function VisitStatusBadge({ status }: { status: VisitStatus }) {
  return <Badge variant={VARIANT_BY_STATUS[status]}>{VISIT_STATUS_LABELS[status]}</Badge>;
}
