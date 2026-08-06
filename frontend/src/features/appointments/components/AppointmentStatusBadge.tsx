import { Badge } from "@/components/ui/badge";
import { APPOINTMENT_STATUS_LABELS, AppointmentStatus } from "@/features/appointments/types";

const VARIANT_BY_STATUS: Record<AppointmentStatus, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  [AppointmentStatus.Booked]: "secondary",
  [AppointmentStatus.Confirmed]: "default",
  [AppointmentStatus.CheckedIn]: "default",
  [AppointmentStatus.Waiting]: "secondary",
  [AppointmentStatus.InConsultation]: "default",
  [AppointmentStatus.Completed]: "success",
  [AppointmentStatus.Cancelled]: "destructive",
  [AppointmentStatus.NoShow]: "destructive",
  [AppointmentStatus.Rescheduled]: "outline",
};

export function AppointmentStatusBadge({ status }: { status: AppointmentStatus }) {
  return <Badge variant={VARIANT_BY_STATUS[status]}>{APPOINTMENT_STATUS_LABELS[status]}</Badge>;
}
