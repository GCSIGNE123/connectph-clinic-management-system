"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useAppointmentDetail, useAvailableSlots } from "@/features/appointments/hooks/use-appointments";
import { useCancelAppointment, useRescheduleAppointment } from "@/features/appointments/hooks/use-appointment-mutations";
import { AppointmentStatusBadge } from "@/features/appointments/components/AppointmentStatusBadge";
import { formatDate, formatDateTime } from "@/lib/utils";
import {
  APPOINTMENT_CANCELLABLE_STATUSES,
  APPOINTMENT_MANAGE_ROLES,
  APPOINTMENT_RESCHEDULABLE_STATUSES,
  APPOINTMENT_TYPE_LABELS,
} from "@/features/appointments/types";

export interface AppointmentDetailsDialogProps {
  appointmentId: string | null;
  onOpenChange: (open: boolean) => void;
}

/** Full record + status + history timeline, mirroring the VisitTimeline
 * pattern used for `features/visits/components/VisitTimeline.tsx`. Reused
 * from both the Appointments List view and the Calendar (day/week/month/
 * agenda entries) - a single dialog, not a per-view duplicate.
 *
 * Edit Appointment reuses the existing `PATCH /appointments/{id}/reschedule`
 * mutation (`useRescheduleAppointment`) - the only appointment-editing
 * capability the backend actually exposes (date/time/reason); there is no
 * generic "edit all fields" endpoint, so this dialog doesn't invent one.
 * Cancel reuses the existing `useCancelAppointment` mutation and the same
 * `window.confirm` confirmation step already used on the List view's row
 * actions, for a consistent, already-established pattern rather than a new
 * one. Both buttons are gated by the same role set already used to show
 * "New Appointment"/List row actions, and by the backend's real
 * `APPOINTMENT_STATUS_TRANSITIONS` (mirrored in
 * `APPOINTMENT_RESCHEDULABLE_STATUSES`/`APPOINTMENT_CANCELLABLE_STATUSES`) -
 * never a frontend-invented rule. */
export function AppointmentDetailsDialog({ appointmentId, onOpenChange }: AppointmentDetailsDialogProps) {
  const { data, isLoading } = useAppointmentDetail(appointmentId);
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && APPOINTMENT_MANAGE_ROLES.has(currentUser.role));

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [rescheduleTime, setRescheduleTime] = useState("");
  const [rescheduleReason, setRescheduleReason] = useState("");

  const reschedule = useRescheduleAppointment();
  const cancel = useCancelAppointment();
  const slots = useAvailableSlots(data?.doctorId ?? null, rescheduleDate || null, data?.branchId);

  // Reset back to the read-only view (and clear the edit form) whenever a
  // different appointment is opened, or the dialog is closed.
  useEffect(() => {
    setMode("view");
    setRescheduleDate("");
    setRescheduleTime("");
    setRescheduleReason("");
  }, [appointmentId]);

  const canReschedule = Boolean(data && APPOINTMENT_RESCHEDULABLE_STATUSES.has(data.status));
  const canCancel = Boolean(data && APPOINTMENT_CANCELLABLE_STATUSES.has(data.status));

  async function handleReschedule() {
    if (!appointmentId || !rescheduleDate || !rescheduleTime) return;
    try {
      await reschedule.mutateAsync({
        id: appointmentId,
        input: { appointmentDate: rescheduleDate, startTime: rescheduleTime, reason: rescheduleReason || null },
      });
      // Reschedule creates a NEW appointment record (the old one becomes a
      // terminal "Rescheduled" row) - there's no longer a meaningful "this
      // same appointment, updated" to keep showing, so close the dialog.
      // The calendar/list have already been invalidated by the mutation
      // and will show the new slot on their next render.
      onOpenChange(false);
    } catch {
      // Surfaced via the mutation's own error toast.
    }
  }

  function handleCancel() {
    if (!appointmentId || !data) return;
    if (window.confirm(`Cancel appointment ${data.appointmentNumber}?`)) {
      cancel.mutate({ id: appointmentId });
    }
  }

  return (
    <Dialog open={Boolean(appointmentId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>{mode === "edit" ? "Edit Appointment" : "Appointment Details"}</DialogTitle>
        </DialogHeader>

        {isLoading || !data ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
          </div>
        ) : mode === "edit" ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {data.appointmentNumber} — {data.patientName ?? "—"} with Dr. {data.doctorName ?? "—"}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>New Date</Label>
                <Input
                  type="date"
                  value={rescheduleDate}
                  onChange={(e) => {
                    setRescheduleDate(e.target.value);
                    setRescheduleTime("");
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Reason (optional)</Label>
                <Input value={rescheduleReason} onChange={(e) => setRescheduleReason(e.target.value)} placeholder="e.g. Doctor requested" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Available Time Slots</Label>
              {!rescheduleDate ? (
                <p className="text-xs text-muted-foreground">Select a date to see available times.</p>
              ) : slots.isFetching ? (
                <p className="text-xs text-muted-foreground">Loading slots...</p>
              ) : (slots.data ?? []).length === 0 ? (
                <p className="text-xs text-destructive">No slots configured for this doctor on this day.</p>
              ) : (
                <div className="grid max-h-40 grid-cols-4 gap-2 overflow-y-auto">
                  {(slots.data ?? []).map((s) => (
                    <button
                      key={s.startTime}
                      type="button"
                      disabled={!s.isAvailable}
                      onClick={() => setRescheduleTime(s.startTime)}
                      title={s.reason ?? undefined}
                      className={`rounded-md border px-2 py-1 text-xs ${
                        rescheduleTime === s.startTime
                          ? "border-primary bg-primary text-primary-foreground"
                          : s.isAvailable
                          ? "border-border hover:bg-accent"
                          : "cursor-not-allowed border-border bg-muted text-muted-foreground line-through"
                      }`}
                    >
                      {s.startTime.slice(0, 5)}
                    </button>
                  ))}
                </div>
              )}
            </div>
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
              <Field label="Date" value={formatDate(data.appointmentDate)} />
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
                      {formatDateTime(h.changedAt)}
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

        <DialogFooter>
          {mode === "edit" ? (
            <>
              <Button type="button" variant="outline" onClick={() => setMode("view")}>
                Back
              </Button>
              <Button
                type="button"
                onClick={handleReschedule}
                disabled={!rescheduleDate || !rescheduleTime || reschedule.isPending}
              >
                {reschedule.isPending ? "Saving..." : "Save New Date/Time"}
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              {canManage && data && canCancel ? (
                <Button type="button" variant="destructive" onClick={handleCancel} disabled={cancel.isPending}>
                  {cancel.isPending ? "Cancelling..." : "Cancel Appointment"}
                </Button>
              ) : null}
              {canManage && data && canReschedule ? (
                <Button type="button" onClick={() => setMode("edit")}>
                  Edit Appointment
                </Button>
              ) : null}
            </>
          )}
        </DialogFooter>
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
