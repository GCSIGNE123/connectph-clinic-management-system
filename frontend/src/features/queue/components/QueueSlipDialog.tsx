"use client";

import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { queueApi } from "@/features/queue/api/queue-api";
import { queueKeys } from "@/features/queue/hooks/use-queues";
import { QUEUE_PRIORITY_LABELS } from "@/features/queue/types";

export interface QueueSlipDialogProps {
  queueId: string | null;
  onOpenChange: (open: boolean) => void;
}

/** Printable queue slip - clinic/branch/queue number/patient/doctor/date/QR. */
export function QueueSlipDialog({ queueId, onOpenChange }: QueueSlipDialogProps) {
  const { data: slip, isLoading } = useQuery({
    queryKey: queueId ? queueKeys.slip(queueId) : ["queue", "slip", "none"],
    queryFn: () => queueApi.getSlip(queueId as string),
    enabled: Boolean(queueId),
  });

  return (
    <Dialog open={Boolean(queueId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Queue Slip</DialogTitle>
        </DialogHeader>

        {isLoading || !slip ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div id="queue-slip-printable" className="space-y-3 rounded-md border border-border p-4 text-center">
            <p className="text-sm font-semibold">{slip.clinicName}</p>
            <p className="text-xs text-muted-foreground">{slip.branchName}</p>
            <p className="text-5xl font-bold tracking-wide">{slip.queueNumber}</p>
            <p className="text-xs uppercase text-muted-foreground">{QUEUE_PRIORITY_LABELS[slip.priority]}</p>
            <div className="space-y-1 border-t border-dashed border-border pt-3 text-left text-sm">
              <p>
                <span className="text-muted-foreground">Patient: </span>
                {slip.patientName}
              </p>
              <p>
                <span className="text-muted-foreground">Department: </span>
                {slip.departmentName}
              </p>
              <p>
                <span className="text-muted-foreground">Doctor: </span>
                {slip.doctorName ?? "Unassigned"}
              </p>
              <p>
                <span className="text-muted-foreground">Date: </span>
                {new Date(slip.createdAt).toLocaleString()}
              </p>
            </div>
            <p className="break-all font-mono text-[10px] text-muted-foreground">{slip.qrToken}</p>
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button type="button" onClick={() => window.print()} disabled={!slip}>
            Print
          </Button>
        </DialogFooter>
      </DialogContent>

      <style jsx global>{`
        @media print {
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
            width: 100%;
            border: none;
          }
        }
      `}</style>
    </Dialog>
  );
}
