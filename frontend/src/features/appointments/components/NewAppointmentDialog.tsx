"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { patientsApi } from "@/features/patients/api/patients-api";
import { useDebouncedValue } from "@/features/patients/hooks/use-patients";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { useCreateAppointment } from "@/features/appointments/hooks/use-appointment-mutations";
import { useAvailableSlots } from "@/features/appointments/hooks/use-appointments";
import { AppointmentType, APPOINTMENT_TYPE_LABELS } from "@/features/appointments/types";

interface SimpleOption {
  id: string;
  name: string;
  status?: string;
  department_id?: string | null;
  branch_id?: string | null;
  service_name?: string;
  first_name?: string;
  last_name?: string;
}

const departmentsApi = createCrudApi<SimpleOption>("/departments");
const doctorsApi = createCrudApi<SimpleOption>("/doctors");
const servicesApi = createCrudApi<SimpleOption>("/services");
const branchesApi = createCrudApi<SimpleOption>("/branches");

export interface NewAppointmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultBranchId?: string | null;
  onCreated?: (appointmentId: string) => void;
}

/**
 * Books a new appointment. Reuses the exact search-or-create-inline patient
 * pattern from `features/queue/components/NewQueueDialog.tsx` (only a real
 * patient search is included here for brevity - the inline-create escape
 * hatch is left as a follow-up; new patients can still be registered from
 * the Patients module first). The date/time step calls the Time Slot Engine
 * (`GET /doctors/{id}/available-slots`) and only lets the user pick a slot
 * the backend reports as genuinely open - the same validation the backend
 * enforces again on submit.
 */
export function NewAppointmentDialog({ open, onOpenChange, defaultBranchId, onCreated }: NewAppointmentDialogProps) {
  const [patientSearch, setPatientSearch] = useState("");
  const debouncedSearch = useDebouncedValue(patientSearch, 300);
  const [selectedPatient, setSelectedPatient] = useState<{ id: string; label: string } | null>(null);

  const [branchId, setBranchId] = useState(defaultBranchId ?? "");
  const [departmentId, setDepartmentId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [appointmentType, setAppointmentType] = useState<AppointmentType>(AppointmentType.NewConsultation);
  const [appointmentDate, setAppointmentDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const createAppointment = useCreateAppointment();

  useEffect(() => {
    if (open) {
      setSelectedPatient(null);
      setPatientSearch("");
      setBranchId(defaultBranchId ?? "");
      setDepartmentId("");
      setDoctorId("");
      setServiceId("");
      setAppointmentType(AppointmentType.NewConsultation);
      setAppointmentDate("");
      setStartTime("");
      setNotes("");
      setFormError(null);
    }
  }, [open, defaultBranchId]);

  const patientResults = useQuery({
    queryKey: ["appointment-new", "patient-search", debouncedSearch],
    queryFn: () => patientsApi.list({ search: debouncedSearch, pageSize: 8, page: 1 }),
    enabled: debouncedSearch.trim().length >= 2 && !selectedPatient,
  });

  const branches = useQuery({ queryKey: ["appointment-new", "branches"], queryFn: () => branchesApi.list({ limit: 100 }) });
  const departments = useQuery({ queryKey: ["appointment-new", "departments"], queryFn: () => departmentsApi.list({ status: "Active", limit: 100 }) });
  const doctors = useQuery({ queryKey: ["appointment-new", "doctors"], queryFn: () => doctorsApi.list({ status: "Active", limit: 100 }) });
  const services = useQuery({ queryKey: ["appointment-new", "services"], queryFn: () => servicesApi.list({ status: "Active", limit: 100 }) });

  const filteredDoctors = useMemo(() => {
    const items = doctors.data?.items ?? [];
    return items.filter((d) => {
      if (departmentId && d.department_id && d.department_id !== departmentId) return false;
      if (branchId && d.branch_id && d.branch_id !== branchId) return false;
      return true;
    });
  }, [doctors.data, departmentId, branchId]);

  // Department-aware Service filtering: NULL `department_id` is shared
  // across every department; an assigned service is only offered for its
  // own department. Same convention as `filteredDoctors` above.
  const filteredServices = useMemo(() => {
    const items = services.data?.items ?? [];
    return items.filter((s) => !departmentId || !s.department_id || s.department_id === departmentId);
  }, [services.data, departmentId]);

  // Transition rule: clear the selected Service when the Department changes
  // and the current selection is no longer valid for it.
  useEffect(() => {
    if (serviceId && !filteredServices.some((s) => s.id === serviceId)) {
      setServiceId("");
    }
  }, [filteredServices, serviceId]);

  const slots = useAvailableSlots(doctorId || null, appointmentDate || null, branchId || undefined);

  function selectPatient(id: string, label: string) {
    setSelectedPatient({ id, label });
    setPatientSearch("");
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!selectedPatient) return setFormError("Select a patient.");
    if (!branchId) return setFormError("Select a branch.");
    if (!doctorId) return setFormError("Select a doctor.");
    if (!appointmentDate) return setFormError("Select a date.");
    if (!startTime) return setFormError("Select an available time slot.");

    try {
      const result = await createAppointment.mutateAsync({
        patientId: selectedPatient.id,
        branchId,
        doctorId,
        departmentId: departmentId || null,
        serviceId: serviceId || null,
        appointmentType,
        appointmentDate,
        startTime,
        notes,
      });
      onOpenChange(false);
      onCreated?.(result.id);
    } catch {
      // Already surfaced via the mutation's onError toast.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>New Appointment</DialogTitle>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label>Patient</Label>
            {selectedPatient ? (
              <div className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                <span>{selectedPatient.label}</span>
                <button type="button" className="text-xs text-primary underline" onClick={() => setSelectedPatient(null)}>
                  Change
                </button>
              </div>
            ) : (
              <>
                <Input
                  placeholder="Search by name, patient number, or mobile"
                  value={patientSearch}
                  onChange={(e) => setPatientSearch(e.target.value)}
                  autoFocus
                />
                {patientSearch.trim().length >= 2 ? (
                  <div className="max-h-40 overflow-y-auto rounded-md border border-border">
                    {patientResults.isFetching ? (
                      <p className="px-3 py-2 text-sm text-muted-foreground">Searching...</p>
                    ) : (patientResults.data?.data.length ?? 0) === 0 ? (
                      <div className="px-3 py-2 text-sm text-muted-foreground">No matches. Register the patient first from the Patients module.</div>
                    ) : (
                      patientResults.data?.data.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                          onClick={() => selectPatient(p.id, `${p.firstName} ${p.lastName} — ${p.patientNumber}`)}
                        >
                          <span>{p.firstName} {p.lastName}</span>
                          <span className="text-xs text-muted-foreground">{p.patientNumber}</span>
                        </button>
                      ))
                    )}
                  </div>
                ) : null}
              </>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Branch</Label>
              <Select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
                <option value="">Select branch</option>
                {(branches.data?.items ?? []).map((b) => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Department</Label>
              <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
                <option value="">Select department</option>
                {(departments.data?.items ?? []).map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Doctor</Label>
              <Select value={doctorId} onChange={(e) => { setDoctorId(e.target.value); setStartTime(""); }}>
                <option value="">Select doctor</option>
                {filteredDoctors.map((d) => (
                  <option key={d.id} value={d.id}>{d.first_name} {d.last_name}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Service (optional)</Label>
              <Select value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
                <option value="">Select service</option>
                {filteredServices.length === 0 ? (
                  <option value="" disabled>
                    No services available for this department.
                  </option>
                ) : (
                  filteredServices.map((s) => (
                    <option key={s.id} value={s.id}>{s.service_name ?? s.name}</option>
                  ))
                )}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={appointmentType} onChange={(e) => setAppointmentType(e.target.value as AppointmentType)}>
                {Object.values(AppointmentType).map((t) => (
                  <option key={t} value={t}>{APPOINTMENT_TYPE_LABELS[t]}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Date</Label>
              <Input type="date" value={appointmentDate} onChange={(e) => { setAppointmentDate(e.target.value); setStartTime(""); }} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Available Time Slots</Label>
            {!doctorId || !appointmentDate ? (
              <p className="text-xs text-muted-foreground">Select a doctor and date to see available slots.</p>
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
                    onClick={() => setStartTime(s.startTime)}
                    title={s.reason ?? undefined}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      startTime === s.startTime
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

          <div className="space-y-1.5">
            <Label>Notes (optional)</Label>
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          {formError ? <p className="text-xs text-destructive">{formError}</p> : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createAppointment.isPending}>
              {createAppointment.isPending ? "Booking..." : "Book Appointment"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
