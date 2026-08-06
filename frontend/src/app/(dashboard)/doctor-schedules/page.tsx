"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { DoctorScheduleForm } from "@/features/appointments/components/DoctorScheduleForm";
import { EmptyState } from "@/components/layout/EmptyState";

interface SimpleDoctor {
  id: string;
  first_name: string;
  last_name: string;
  status?: string;
}

const doctorsApi = createCrudApi<SimpleDoctor>("/doctors");

/**
 * Administrator-only Doctor Schedule admin page (Phase 11): working
 * days/hours/lunch break/slot duration/max-per-day, plus vacation/blocked
 * dates. Placed alongside Doctors in Clinic Configuration since it manages
 * per-doctor configuration, not appointment records themselves.
 */
export default function DoctorSchedulesPage() {
  const { data } = useQuery({ queryKey: ["doctor-schedules", "doctors"], queryFn: () => doctorsApi.list({ status: "Active", limit: 100 }) });
  const doctors = data?.items ?? [];
  const [doctorId, setDoctorId] = useState("");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Doctor Schedules</h1>
        <p className="text-sm text-muted-foreground">
          Configure each doctor&apos;s working days/hours, lunch break, appointment slot duration, and vacation/blocked dates.
          These drive the Time Slot Engine used when booking appointments.
        </p>
      </div>

      <Card className="p-4">
        <div className="max-w-sm space-y-1.5">
          <label className="text-sm font-medium">Doctor</label>
          <Select value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
            <option value="">Select a doctor</option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>
                Dr. {d.first_name} {d.last_name}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {doctorId ? (
        <DoctorScheduleForm doctorId={doctorId} />
      ) : (
        <EmptyState title="Select a doctor" description="Choose a doctor above to view or edit their schedule." />
      )}
    </div>
  );
}
