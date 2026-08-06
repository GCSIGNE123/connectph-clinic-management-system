import { Badge } from "@/components/ui/badge";
import { QUEUE_STATUS_LABELS, QueueStatus } from "@/features/queue/types";

const VARIANT_BY_STATUS: Record<QueueStatus, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  [QueueStatus.Waiting]: "secondary",
  [QueueStatus.Called]: "default",
  [QueueStatus.Serving]: "default",
  [QueueStatus.Completed]: "success",
  [QueueStatus.Skipped]: "outline",
  [QueueStatus.Cancelled]: "destructive",
  [QueueStatus.NoShow]: "destructive",
};

export function QueueStatusBadge({ status }: { status: QueueStatus }) {
  return <Badge variant={VARIANT_BY_STATUS[status]}>{QUEUE_STATUS_LABELS[status]}</Badge>;
}
