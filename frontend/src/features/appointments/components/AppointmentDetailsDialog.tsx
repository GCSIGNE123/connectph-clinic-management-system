"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAppointmentDetail } from "@/features/appointments/hooks/use-appointments";
import { AppointmentStatusBadge } from "@/features/appointments/components/AppointmentStatusBadge";
import { APPOINTMENT_TYPE_LABELS } from "@/features/appointments/types";

export interface AppointmentDetailsDialogProps {
  appointmentId: string | null;
  onOpenChange: (open: boolean) => void;
}

/** Full record + status + history timeline, mirroring the VisitTimeline
 * pattern used for `features/visits/components/VisitTimeline.tsx`. */
export function AppointmentDetailsDialog({ appointmentId, onOpenChange }: AppointmentDetailsDialogProps) {
  const { data, isLoading } = useAppointmentDetail(appointmentId);

  return (
    <Dialog open={Boolean(appointmentId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>{data ? `Appointment ${data.appointmentNumber}` : "Appointment"}</DialogTitle>
        </DialogHeader>

        {isLoading || !data ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <AppointmentStatusBadge status={data.status} />
              <span className="text-sm text-muted-foreground">{APPOINTMENT_TYPE_LABELS[data.appointmentType]}</span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <Field label="Patient" value={`${data.patientName ?? "—"} (${data.patientNumber ?? "—"})`} />
              <Field label="Doctor" value={data.doctorName ?? "—"} />
              <Field label="Department" value={data.departmentName ?? "—"} />
              <Field label="Service" value={data.serviceName ?? "—"} />
              <Field label="Date" value={data.appointmentDate} />
              <Field label="Time" value={`${data.startTime.slice(0, 5)} – ${data.endTime.slice(0, 5)}`} />
              <Field label="Branch" value={data.branchName ?? "—"} />
              <Field label="Notes" value={data.notes ?? "—"} />
            </div>

            {data.queueId || data.visitId ? (
              <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
                Checked in — linked Queue ticket and Visit have been created.
              </div>
            ) : null}

            <div>
              <h3 className="mb-2 text-sm font-medium">History</h3>
              <ol className="space-y-2 border-l border-border pl-4">
                {data.history.map((h) => (
                  <li key={h.id} className="text-sm">
                    <div className="font-medium">{h.action}</div>
                    <div className="text-xs text-muted-foreground">
                      {new Date(h.changedAt).toLocaleString()}
                      {h.note ? ` — ${h.note}` : ""}
                    </div>
                    {h.fromValue || h.toValue ? (
                      <div className="text-xs text-muted-foreground">
                        {h.fromValue ?? "—"} → {h.toValue ?? "—"}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div>{value}</div>
    </div>
  );
}
