"use client";

import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { usePatientAppointments } from "@/features/appointments/hooks/use-appointments";
import { AppointmentStatusBadge } from "@/features/appointments/components/AppointmentStatusBadge";
import type { AppointmentListItem } from "@/features/appointments/types";

/** Patient Profile "Appointments" tab (Phase 11) - Upcoming/Completed/
 * Cancelled/No-show buckets, mirroring `PatientLaboratoryHistory`'s shape. */
export function PatientAppointmentsHistory({ patientId }: { patientId: string }) {
  const { data, isLoading } = usePatientAppointments(patientId);

  if (isLoading) return <SkeletonList rows={3} />;

  const buckets = [
    { label: "Upcoming", items: data?.upcoming ?? [] },
    { label: "Completed", items: data?.completed ?? [] },
    { label: "Cancelled / Rescheduled", items: data?.cancelled ?? [] },
    { label: "No Show", items: data?.noShow ?? [] },
  ];

  const total = buckets.reduce((sum, b) => sum + b.items.length, 0);
  if (total === 0) {
    return <EmptyState title="No appointments yet" description="Appointments for this patient will appear here." />;
  }

  return (
    <div className="space-y-6">
      {buckets
        .filter((b) => b.items.length > 0)
        .map((bucket) => (
          <div key={bucket.label}>
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">{bucket.label}</h3>
            <Table items={bucket.items} />
          </div>
        ))}
    </div>
  );
}

function Table({ items }: { items: AppointmentListItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Appointment #</th>
            <th className="px-3 py-2">Doctor</th>
            <th className="px-3 py-2">Department</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-2 whitespace-nowrap">{a.appointmentDate} {a.startTime.slice(0, 5)}</td>
              <td className="px-3 py-2 font-mono text-xs">{a.appointmentNumber}</td>
              <td className="px-3 py-2 text-muted-foreground">{a.doctorName ?? "-"}</td>
              <td className="px-3 py-2 text-muted-foreground">{a.departmentName ?? "-"}</td>
              <td className="px-3 py-2">
                <AppointmentStatusBadge status={a.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
