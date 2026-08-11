"use client";

import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { patientsApi } from "@/features/patients/api/patients-api";
import { useCreatePatient } from "@/features/patients/hooks/use-patient-mutations";
import { PatientGender, PatientCivilStatus } from "@/features/patients/types";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { useDebouncedValue } from "@/features/patients/hooks/use-patients";
import { useCreateQueue } from "@/features/queue/hooks/use-queue-mutations";
import { newQueueSchema, type NewQueueInput } from "@/features/queue/schemas/queue-schemas";
import { QUEUE_PRIORITY_LABELS, QueuePriority, VISIT_CLASSIFICATION_LABELS, VisitClassification } from "@/features/queue/types";
import { useShiftRequiredError } from "@/features/shifts/hooks/use-shift-required-error";
import { ShiftRequiredDialog } from "@/features/shifts/components/ShiftRequiredDialog";
import { visitsApi } from "@/features/visits/api/visits-api";
import type { VisitDetail } from "@/features/visits/types";
import { PreQueueVitalsStep } from "@/features/queue/components/PreQueueVitalsStep";
import { ApiError } from "@/lib/api-client";

interface SimpleOption {
  id: string;
  name: string;
  status?: string;
  department_id?: string | null;
  branch_id?: string | null;
  duration_minutes?: number | null;
  default_price?: string | number | null;
  service_name?: string;
  service_code?: string;
}

// Phase 21 (Vitals-before-Queue): the two service_code values that require
// vitals to be captured (via a draft Visit) BEFORE a Queue ticket can be
// created - see `services/queue_service.py::PRE_QUEUE_VITALS_SERVICE_CODES`
// on the backend, which is the actual enforcement; this is only used here
// to drive the frontend's step/button state (first line of defense).
const PRE_QUEUE_VITALS_SERVICE_CODES = new Set(["CONSULT", "FOLLOW-UP"]);

const departmentsApi = createCrudApi<SimpleOption>("/departments");
const doctorsApi = createCrudApi<SimpleOption & { first_name?: string; last_name?: string }>("/doctors");
const servicesApi = createCrudApi<SimpleOption>("/services");
const branchesApi = createCrudApi<SimpleOption>("/branches");

export interface NewQueueDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultBranchId?: string | null;
  onCreated?: (queueId: string) => void;
}

/**
 * Fast, keyboard-friendly single-form flow for raising a queue ticket:
 * search-or-create a patient, then branch/department/doctor/service/priority.
 * Deliberately a single compact form (not a multi-step wizard) - receptionist
 * workflow needs this to be quick for a walk-in patient already at the counter.
 */
export function NewQueueDialog({ open, onOpenChange, defaultBranchId, onCreated }: NewQueueDialogProps) {
  const [patientSearch, setPatientSearch] = useState("");
  const debouncedSearch = useDebouncedValue(patientSearch, 300);
  const [selectedPatient, setSelectedPatient] = useState<{ id: string; label: string; isYakapBeneficiary: boolean } | null>(
    null
  );
  const [inlinePatientOpen, setInlinePatientOpen] = useState(false);

  // Phase 21 (Vitals-before-Queue): draft Visit created for Consultation/
  // Follow-up services before the queue ticket exists, plus whether the
  // vitals step is currently showing and whether it's been saved at least
  // once (gates the "Create Queue Ticket" button).
  const [draftVisit, setDraftVisit] = useState<VisitDetail | null>(null);
  const [showVitalsStep, setShowVitalsStep] = useState(false);
  const [vitalsSaved, setVitalsSaved] = useState(false);
  const [creatingDraft, setCreatingDraft] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);

  const shiftError = useShiftRequiredError();
  const createQueue = useCreateQueue(shiftError.handleError);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<NewQueueInput>({
    resolver: zodResolver(newQueueSchema),
    defaultValues: {
      patientId: "",
      branchId: defaultBranchId ?? "",
      departmentId: "",
      doctorId: "",
      serviceId: "",
      priority: QueuePriority.Normal,
      notes: "",
      visitClassification: VisitClassification.Regular,
    },
  });

  useEffect(() => {
    if (open) {
      reset({
        patientId: "",
        branchId: defaultBranchId ?? "",
        departmentId: "",
        doctorId: "",
        serviceId: "",
        priority: QueuePriority.Normal,
        notes: "",
        visitClassification: VisitClassification.Regular,
      });
      setSelectedPatient(null);
      setPatientSearch("");
      setDraftVisit(null);
      setShowVitalsStep(false);
      setVitalsSaved(false);
      setDraftError(null);
    }
  }, [open, defaultBranchId, reset]);

  const departmentId = watch("departmentId");
  const branchId = watch("branchId");
  const serviceId = watch("serviceId");
  const doctorId = watch("doctorId");
  const patientId = watch("patientId");

  const patientResults = useQuery({
    queryKey: ["queue-new", "patient-search", debouncedSearch],
    queryFn: () => patientsApi.list({ search: debouncedSearch, pageSize: 8, page: 1 }),
    enabled: debouncedSearch.trim().length >= 2 && !selectedPatient,
  });

  const branches = useQuery({ queryKey: ["queue-new", "branches"], queryFn: () => branchesApi.list({ limit: 100 }) });
  const departments = useQuery({
    queryKey: ["queue-new", "departments"],
    queryFn: () => departmentsApi.list({ status: "Active", limit: 100 }),
  });
  const doctors = useQuery({
    queryKey: ["queue-new", "doctors", departmentId, branchId],
    queryFn: () => doctorsApi.list({ status: "Active", limit: 100 }),
  });
  const services = useQuery({
    queryKey: ["queue-new", "services"],
    queryFn: () => servicesApi.list({ status: "Active", limit: 100 }),
  });

  const filteredDoctors = useMemo(() => {
    const items = doctors.data?.items ?? [];
    return items.filter((d) => {
      if (departmentId && d.department_id && d.department_id !== departmentId) return false;
      if (branchId && d.branch_id && d.branch_id !== branchId) return false;
      return true;
    });
  }, [doctors.data, departmentId, branchId]);

  function selectPatient(id: string, label: string, isYakapBeneficiary: boolean) {
    setSelectedPatient({ id, label, isYakapBeneficiary });
    setValue("patientId", id, { shouldValidate: true });
    // Phase 2.7 (YAKAP Patient Classification): pre-fills the per-ticket
    // classification from the patient's standing beneficiary flag - the
    // receptionist can still change it below before creating the ticket.
    setValue("visitClassification", isYakapBeneficiary ? VisitClassification.Yakap : VisitClassification.Regular);
    setPatientSearch("");
  }

  // Phase 21 (Vitals-before-Queue): Consultation/Follow-up services need
  // vitals captured first - detected via `service_code` since `ClinicService`
  // has no dedicated category field (see backend module docstring). Every
  // other service keeps today's exact single-step behavior untouched.
  const selectedService = useMemo(
    () => (services.data?.items ?? []).find((s) => s.id === serviceId),
    [services.data, serviceId]
  );
  const requiresVitals = Boolean(selectedService?.service_code && PRE_QUEUE_VITALS_SERVICE_CODES.has(selectedService.service_code));

  // A previously created draft only remains valid for the service/patient
  // it was created for - if the receptionist changes patient or service
  // after entering vitals, the draft no longer applies and must be redone.
  useEffect(() => {
    if (draftVisit && (draftVisit.serviceId !== serviceId || draftVisit.patientId !== patientId)) {
      setDraftVisit(null);
      setVitalsSaved(false);
      setShowVitalsStep(false);
    }
  }, [serviceId, patientId, draftVisit]);

  async function handleEnterVitals() {
    setDraftError(null);
    if (!patientId || !branchId || !departmentId || !serviceId) {
      setDraftError("Select patient, branch, department, and service first.");
      return;
    }
    if (!doctorId) {
      setDraftError("A doctor must be selected before entering vitals for this service.");
      return;
    }
    setCreatingDraft(true);
    try {
      const visit = draftVisit ?? (await visitsApi.createPreQueue({
        patientId, branchId, doctorId, departmentId, serviceId,
      }));
      setDraftVisit(visit);
      setShowVitalsStep(true);
    } catch (err) {
      setDraftError(err instanceof ApiError ? err.message : "Could not start vitals capture.");
    } finally {
      setCreatingDraft(false);
    }
  }

  const onSubmit = handleSubmit(async (values) => {
    // mutateAsync rejects on failure even though onError (see
    // use-queue-mutations.ts) already shows a toast with the backend's
    // message; without this try/catch that rejection propagates as an
    // unhandled promise rejection instead of being a handled UI error.
    try {
      const result = await createQueue.mutateAsync({
        patientId: values.patientId,
        branchId: values.branchId,
        departmentId: values.departmentId,
        doctorId: values.doctorId || null,
        serviceId: values.serviceId,
        priority: values.priority,
        notes: values.notes,
        visitId: requiresVitals ? draftVisit?.id ?? null : null,
        visitClassification: values.visitClassification,
      });
      onOpenChange(false);
      onCreated?.(result.id);
    } catch {
      // Already surfaced via the mutation's onError toast.
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>New Queue Ticket</DialogTitle>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label>Patient</Label>
            {selectedPatient ? (
              <div className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                <span>{selectedPatient.label}</span>
                <button
                  type="button"
                  className="text-xs text-primary underline"
                  onClick={() => {
                    setSelectedPatient(null);
                    setValue("patientId", "", { shouldValidate: true });
                  }}
                >
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
                      <div className="px-3 py-2 text-sm text-muted-foreground">
                        No matches.{" "}
                        <button type="button" className="text-primary underline" onClick={() => setInlinePatientOpen(true)}>
                          Create new patient
                        </button>
                      </div>
                    ) : (
                      patientResults.data?.data.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                          onClick={() =>
                            selectPatient(p.id, `${p.firstName} ${p.lastName} — ${p.patientNumber}`, p.isYakapBeneficiary)
                          }
                        >
                          <span>
                            {p.firstName} {p.lastName}
                          </span>
                          <span className="text-xs text-muted-foreground">{p.patientNumber}</span>
                        </button>
                      ))
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    className="text-xs text-primary underline"
                    onClick={() => setInlinePatientOpen(true)}
                  >
                    + Create new patient
                  </button>
                )}
              </>
            )}
            {errors.patientId ? <p className="text-xs text-destructive">{errors.patientId.message}</p> : null}
          </div>

          {!showVitalsStep ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Branch</Label>
                  <Select {...register("branchId")} invalid={Boolean(errors.branchId)} disabled={vitalsSaved}>
                    <option value="">Select branch</option>
                    {(branches.data?.items ?? []).map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Department</Label>
                  <Select {...register("departmentId")} invalid={Boolean(errors.departmentId)} disabled={vitalsSaved}>
                    <option value="">Select department</option>
                    {(departments.data?.items ?? []).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Doctor{requiresVitals ? "" : " (optional)"}</Label>
                  <Select {...register("doctorId")} disabled={vitalsSaved}>
                    <option value="">{requiresVitals ? "Select doctor" : "Any / unassigned"}</option>
                    {filteredDoctors.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.first_name} {d.last_name}
                      </option>
                    ))}
                  </Select>
                  {requiresVitals ? (
                    <p className="text-xs text-muted-foreground">
                      Required for this service - vitals are opened against the assigned doctor&apos;s consultation.
                    </p>
                  ) : null}
                </div>
                <div className="space-y-1.5">
                  <Label>Service</Label>
                  <Select {...register("serviceId")} invalid={Boolean(errors.serviceId)} disabled={vitalsSaved}>
                    <option value="">Select service</option>
                    {(services.data?.items ?? []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.service_name ?? s.name}
                        {s.duration_minutes ? ` (${s.duration_minutes} min)` : ""}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Priority</Label>
                  <Select {...register("priority")}>
                    {Object.values(QueuePriority).map((p) => (
                      <option key={p} value={p}>
                        {QUEUE_PRIORITY_LABELS[p]}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Classification</Label>
                  <Select {...register("visitClassification")}>
                    {Object.values(VisitClassification).map((c) => (
                      <option key={c} value={c}>
                        {VISIT_CLASSIFICATION_LABELS[c]}
                      </option>
                    ))}
                  </Select>
                  {selectedPatient?.isYakapBeneficiary ? (
                    <p className="text-xs text-muted-foreground">
                      Pre-filled from patient profile (YAKAP beneficiary) - change if this visit is being processed
                      differently.
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>Notes (optional)</Label>
                <Textarea rows={2} {...register("notes")} />
              </div>

              {requiresVitals && vitalsSaved ? (
                <div className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  <span className="text-green-600">Vitals recorded.</span>
                  <button type="button" className="text-xs text-primary underline" onClick={() => setShowVitalsStep(true)}>
                    Edit vitals
                  </button>
                </div>
              ) : null}
              {draftError ? <p className="text-xs text-destructive">{draftError}</p> : null}
            </>
          ) : draftVisit ? (
            <PreQueueVitalsStep
              visitId={draftVisit.id}
              onSaved={() => {
                setVitalsSaved(true);
                setShowVitalsStep(false);
              }}
              onBack={() => setShowVitalsStep(false)}
            />
          ) : null}

          {!showVitalsStep ? (
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              {requiresVitals && !vitalsSaved ? (
                <Button type="button" onClick={handleEnterVitals} disabled={creatingDraft}>
                  {creatingDraft ? "Starting..." : "Enter Vitals"}
                </Button>
              ) : (
                <Button type="submit" disabled={isSubmitting || createQueue.isPending}>
                  {createQueue.isPending ? "Creating..." : "Create Queue Ticket"}
                </Button>
              )}
            </DialogFooter>
          ) : null}
        </form>
      </DialogContent>

      <InlinePatientCreateDialog
        open={inlinePatientOpen}
        onOpenChange={setInlinePatientOpen}
        onCreated={(id, label) => {
          setInlinePatientOpen(false);
          // The inline quick-create form has no YAKAP field - defaults to
          // Regular, same as `Patient.is_yakap_beneficiary`'s own default.
          selectPatient(id, label, false);
        }}
      />
      <ShiftRequiredDialog open={shiftError.open} onOpenChange={shiftError.setOpen} />
    </Dialog>
  );
}

/**
 * Abbreviated patient-create form (name/birth date/gender/civil
 * status/mobile only) shown as an escape hatch from the New Queue flow, so a
 * receptionist doesn't have to leave the queue dialog to register a walk-in
 * who isn't in the system yet. Full demographic capture still happens later
 * from the Patients module - this only creates the minimum viable record.
 */
function InlinePatientCreateDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (patientId: string, label: string) => void;
}) {
  const createPatient = useCreatePatient();
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    birthDate: "",
    gender: PatientGender.Male,
    civilStatus: PatientCivilStatus.Single,
    mobileNumber: "",
  });

  useEffect(() => {
    if (open) setForm({ firstName: "", lastName: "", birthDate: "", gender: PatientGender.Male, civilStatus: PatientCivilStatus.Single, mobileNumber: "" });
  }, [open]);

  async function handleCreate() {
    try {
      const result = await createPatient.mutateAsync({
        input: { ...form, nationality: "Filipino" } as never,
        override: false,
      });
      if (result.patient) {
        onCreated(result.patient.id, `${result.patient.firstName} ${result.patient.lastName} — ${result.patient.patientNumber}`);
      } else if (result.duplicates.length > 0) {
        const d = result.duplicates[0];
        onCreated(d.id, `${d.fullName} — ${d.patientNumber}`);
      }
    } catch {
      // Already surfaced via the mutation's onError toast, if any.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Create New Patient</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>First name</Label>
              <Input value={form.firstName} onChange={(e) => setForm((f) => ({ ...f, firstName: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Last name</Label>
              <Input value={form.lastName} onChange={(e) => setForm((f) => ({ ...f, lastName: e.target.value }))} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Birth date</Label>
              <Input type="date" value={form.birthDate} onChange={(e) => setForm((f) => ({ ...f, birthDate: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label>Gender</Label>
              <Select value={form.gender} onChange={(e) => setForm((f) => ({ ...f, gender: e.target.value as PatientGender }))}>
                {Object.values(PatientGender).map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Mobile number</Label>
            <Input value={form.mobileNumber} onChange={(e) => setForm((f) => ({ ...f, mobileNumber: e.target.value }))} />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleCreate}
            disabled={createPatient.isPending || !form.firstName || !form.lastName || !form.birthDate || !form.mobileNumber}
          >
            {createPatient.isPending ? "Creating..." : "Create & Select"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
