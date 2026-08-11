"use client";

import type { ReactNode } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useQueueDetail } from "@/features/queue/hooks/use-queues";
import { useChangeQueueStatus, useReannounceQueue } from "@/features/queue/hooks/use-queue-mutations";
import { QueueStatusBadge } from "@/features/queue/components/QueueStatusBadge";
import {
  QUEUE_PRIORITY_LABELS,
  QUEUE_STATUS_LABELS,
  QUEUE_STATUS_TRANSITIONS,
  VISIT_CLASSIFICATION_LABELS,
  QueueStatus,
} from "@/features/queue/types";

export interface QueueDetailsDialogProps {
  queueId: string | null;
  onOpenChange: (open: boolean) => void;
  canTransition: boolean;
}

export function QueueDetailsDialog({ queueId, onOpenChange, canTransition }: QueueDetailsDialogProps) {
  const { data: queue, isLoading } = useQueueDetail(queueId);
  const changeStatus = useChangeQueueStatus();
  const reannounce = useReannounceQueue();

  return (
    <Dialog open={Boolean(queueId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Queue Ticket {queue?.queueNumber ?? ""}</DialogTitle>
        </DialogHeader>

        {isLoading || !queue ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-1/2" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Patient" value={`${queue.patientName ?? "—"} (${queue.patientNumber ?? "—"})`} />
              <Field label="Status" value={<QueueStatusBadge status={queue.status} />} />
              <Field label="Department" value={queue.departmentName ?? "—"} />
              <Field label="Doctor" value={queue.doctorName ?? "Unassigned"} />
              <Field label="Service" value={queue.serviceName ?? "—"} />
              <Field label="Priority" value={QUEUE_PRIORITY_LABELS[queue.priority]} />
              <Field label="Classification" value={VISIT_CLASSIFICATION_LABELS[queue.visitClassification]} />
              <Field label="Branch" value={queue.branchName ?? "—"} />
              <Field label="Created" value={new Date(queue.createdAt).toLocaleString()} />
            </div>

            {canTransition && ((QUEUE_STATUS_TRANSITIONS[queue.status]?.length ?? 0) > 0 || queue.status === QueueStatus.Called) ? (
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">Actions</p>
                <div className="flex flex-wrap gap-2">
                  {QUEUE_STATUS_TRANSITIONS[queue.status].map((next: QueueStatus) => (
                    <Button
                      key={next}
                      size="sm"
                      variant="outline"
                      disabled={changeStatus.isPending}
                      onClick={() => changeStatus.mutate({ id: queue.id, status: next })}
                    >
                      {next === QueueStatus.Called ? "Call" : QUEUE_STATUS_LABELS[next]}
                    </Button>
                  ))}
                  {/* Reception Queue Workflow Improvements (Feature 3): only
                      offered once already Called - re-announces the exact
                      same ticket/queue number, no new ticket or status
                      change (see `QueueService.reannounce`). */}
                  {queue.status === QueueStatus.Called ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={reannounce.isPending}
                      onClick={() => reannounce.mutate(queue.id)}
                    >
                      Re-announce
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}

            <div>
              <p className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">History</p>
              <ol className="space-y-2 border-l border-border pl-4">
                {queue.history.map((h) => (
                  <li key={h.id} className="relative">
                    <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-primary" />
                    <p className="font-medium">
                      {h.fromStatus ? `${QUEUE_STATUS_LABELS[h.fromStatus]} → ` : ""}
                      {QUEUE_STATUS_LABELS[h.toStatus]}
                    </p>
                    <p className="text-xs text-muted-foreground">{new Date(h.changedAt).toLocaleString()}</p>
                    {h.note ? <p className="text-xs text-muted-foreground">{h.note}</p> : null}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="font-medium">{value}</div>
    </div>
  );
}
