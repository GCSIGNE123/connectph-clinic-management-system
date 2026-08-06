"use client";

import { useState } from "react";
import { Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useDebouncedValue } from "@/features/patients/hooks/use-patients";
import { useAppointments } from "@/features/appointments/hooks/use-appointments";
import {
  useCancelAppointment,
  useCheckInAppointment,
  useCompleteAppointment,
  useConfirmAppointment,
  useMarkNoShow,
} from "@/features/appointments/hooks/use-appointment-mutations";
import { NewAppointmentDialog } from "@/features/appointments/components/NewAppointmentDialog";
import { AppointmentTable } from "@/features/appointments/components/AppointmentTable";
import { AppointmentDetailsDialog } from "@/features/appointments/components/AppointmentDetailsDialog";
import { AppointmentCalendar } from "@/features/appointments/components/AppointmentCalendar";
import { APPOINTMENT_STATUS_LABELS, AppointmentStatus, type AppointmentListItem } from "@/features/appointments/types";
import { Role } from "@/types";
import { useShiftRequiredError } from "@/features/shifts/hooks/use-shift-required-error";
import { ShiftRequiredDialog } from "@/features/shifts/components/ShiftRequiredDialog";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);
const COMPLETE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Doctor]);

type PageView = "list" | "calendar";

/**
 * Appointment Dashboard: search/filter, list view, New Appointment booking,
 * and the full lifecycle actions (Confirm/Check-in/Complete/No-show/Cancel)
 * contextual to status and role. Check-in is the critical action that also
 * creates a real Queue ticket + Visit - see
 * `hooks/use-appointment-mutations.ts::useCheckInAppointment` for the
 * cross-feature cache invalidation this triggers.
 */
export default function AppointmentsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const canComplete = Boolean(currentUser && COMPLETE_ROLES.has(currentUser.role));

  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [newAppointmentOpen, setNewAppointmentOpen] = useState(false);
  const [detailsId, setDetailsId] = useState<string | null>(null);
  const [view, setView] = useState<PageView>("list");

  const { data, isLoading } = useAppointments({
    search: debouncedSearch || undefined,
    status: status || undefined,
    pageSize: 50,
  });

  const confirmAppointment = useConfirmAppointment();
  const shiftError = useShiftRequiredError();
  const checkInAppointment = useCheckInAppointment(shiftError.handleError);
  const cancelAppointment = useCancelAppointment();
  const completeAppointment = useCompleteAppointment();
  const markNoShow = useMarkNoShow();

  function onConfirm(item: AppointmentListItem) {
    confirmAppointment.mutate(item.id);
  }
  function onCheckIn(item: AppointmentListItem) {
    checkInAppointment.mutate(item.id);
  }
  function onCancel(item: AppointmentListItem) {
    if (window.confirm(`Cancel appointment ${item.appointmentNumber}?`)) {
      cancelAppointment.mutate({ id: item.id });
    }
  }
  function onComplete(item: AppointmentListItem) {
    completeAppointment.mutate(item.id);
  }
  function onNoShow(item: AppointmentListItem) {
    if (window.confirm(`Mark ${item.appointmentNumber} as No Show?`)) {
      markNoShow.mutate(item.id);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Appointments</h1>
          <p className="text-sm text-muted-foreground">
            Book, confirm, check in, and track appointments through Booked → Confirmed → Checked-in → Completed.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1 rounded-md border border-border p-1">
            <button
              type="button"
              onClick={() => setView("list")}
              className={`rounded px-3 py-1 text-xs ${view === "list" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"}`}
            >
              List
            </button>
            <button
              type="button"
              onClick={() => setView("calendar")}
              className={`rounded px-3 py-1 text-xs ${view === "calendar" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"}`}
            >
              Calendar
            </button>
          </div>
          {canManage ? (
            <Button onClick={() => setNewAppointmentOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Appointment
            </Button>
          ) : null}
        </div>
      </div>

      {view === "calendar" ? (
        <AppointmentCalendar />
      ) : (
        <Card>
          <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by appointment #, patient name, number, or mobile"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="pl-9"
              />
            </div>
            <Select value={status} onChange={(e) => setStatus(e.target.value as AppointmentStatus | "")} className="sm:w-56">
              <option value="">All statuses</option>
              {Object.values(AppointmentStatus).map((s) => (
                <option key={s} value={s}>{APPOINTMENT_STATUS_LABELS[s]}</option>
              ))}
            </Select>
          </div>

          <AppointmentTable
            items={data?.data ?? []}
            isLoading={isLoading}
            onView={(item) => setDetailsId(item.id)}
            onConfirm={onConfirm}
            onCheckIn={onCheckIn}
            onCancel={onCancel}
            onComplete={onComplete}
            onNoShow={onNoShow}
            canManage={canManage}
            canComplete={canComplete}
          />
        </Card>
      )}

      <NewAppointmentDialog
        open={newAppointmentOpen}
        onOpenChange={setNewAppointmentOpen}
        defaultBranchId={currentUser?.branchId ?? undefined}
        onCreated={(id) => setDetailsId(id)}
      />

      <AppointmentDetailsDialog appointmentId={detailsId} onOpenChange={(open) => !open && setDetailsId(null)} />
      <ShiftRequiredDialog open={shiftError.open} onOpenChange={shiftError.setOpen} />
    </div>
  );
}
