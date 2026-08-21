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
import { SearchableSelect } from "@/components/ui/searchable-select";
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
import { LabPaymentStep } from "@/features/queue/components/LabPaymentStep";
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

  // Laboratory pay-first workflow: mirrors the vitals-step state above, but
  // for Laboratory tickets - a draft Visit + Laboratory invoice must be
  // created and PAID before the Queue ticket itself can exist (backend-
  // enforced, see `QueueService._create_queue_for_paid_lab_visit`). Kept
  // as its own parallel step (not merged with the vitals step) since the
  // two are mutually exclusive - a service can't be both Consultation/
  // Follow-up and Laboratory-department at once.
  const [labDraftVisit, setLabDraftVisit] = useState<VisitDetail | null>(null);
  const [showLabPaymentStep, setShowLabPaymentStep] = useState(false);
  const [labQueueError, setLabQueueError] = useState<string | null>(null);
  const [creatingLabDraft, setCreatingLabDraft] = useState(false);
  const [labDraftError, setLabDraftError] = useState<string | null>(null);
  // Multiple Laboratory Services in One Queue Transaction: the selected set
  // of Laboratory services for this ticket, in selection order. Deliberately
  // separate from the `serviceId` form field (which every other department
  // still uses as-is) - the pre-queue Visit and the Queue ticket itself
  // still carry a single "primary" service (`labServiceIds[0]`, mirrored
  // into `serviceId` when payment starts), but the invoice created for
  // payment gets one line item per id here. See `LabPaymentStep`'s
  // `serviceIds` prop.
  const [labServiceIds, setLabServiceIds] = useState<string[]>([]);

  const shiftError = useShiftRequiredError();
  const createQueue = useCreateQueue(shiftError.handleError);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    getValues,
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
      setLabDraftVisit(null);
      setShowLabPaymentStep(false);
      setLabQueueError(null);
      setLabDraftError(null);
      setLabServiceIds([]);
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

  // Laboratory pay-first workflow: detected by department NAME (matching
  // the same convention `QueueService._is_laboratory_department` uses on
  // the backend, which is the real enforcement - this is only the first
  // line of defense driving the frontend's step/button state, exactly like
  // `requiresVitals`/`PRE_QUEUE_VITALS_SERVICE_CODES` above). A direct API
  // call for this department without going through the pay-first steps is
  // still rejected server-side regardless of what this flag does here.
  const selectedDepartment = useMemo(
    () => (departments.data?.items ?? []).find((d) => d.id === departmentId),
    [departments.data, departmentId]
  );
  const isLaboratoryDepartment = Boolean(selectedDepartment?.name?.trim().toLowerCase() === "laboratory");

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

  // Same invalidation rule as above, for the Laboratory draft/invoice - a
  // changed patient/department/selected-services set means the invoice
  // already created for the previous selection no longer applies. Compared
  // by a stable joined key (order-independent membership, not array
  // identity) so re-rendering with the same selected services never
  // spuriously invalidates an in-progress payment step.
  const labServiceIdsKey = useMemo(() => [...labServiceIds].sort().join(","), [labServiceIds]);
  useEffect(() => {
    if (
      labDraftVisit &&
      (labDraftVisit.serviceId !== labServiceIds[0] || labDraftVisit.patientId !== patientId || labDraftVisit.departmentId !== departmentId)
    ) {
      setLabDraftVisit(null);
      setShowLabPaymentStep(false);
      setLabQueueError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labServiceIdsKey, patientId, departmentId, labDraftVisit]);

  // Clears any selected Laboratory services when the department changes
  // away from Laboratory (or to it, starting fresh) - the same pattern
  // `requiresVitals`/vitals-step state already resets on service change.
  useEffect(() => {
    setLabServiceIds([]);
  }, [departmentId]);

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

  async function handleProceedToLabPayment() {
    setLabDraftError(null);
    if (!patientId || !branchId || !departmentId || labServiceIds.length === 0) {
      setLabDraftError("Select patient, branch, department, and at least one Laboratory service first.");
      return;
    }
    setCreatingLabDraft(true);
    try {
      // The pre-queue Visit still carries one "primary" service (the first
      // selected) - `serviceId` is kept in sync here purely so the existing
      // draft-invalidation effect and `handleLabPaid`'s Queue-creation call
      // (Queue.service_id also stays singular) both read a value that
      // matches what was actually used. The full selected set is what
      // matters for the invoice - see `LabPaymentStep`'s `serviceIds` prop.
      setValue("serviceId", labServiceIds[0], { shouldValidate: false });
      // Doctor rule: never sent for Laboratory - the field is hidden below
      // and the backend treats it as fully optional for this department.
      const visit = labDraftVisit ?? (await visitsApi.createPreQueue({
        patientId, branchId, doctorId: null, departmentId, serviceId: labServiceIds[0],
      }));
      setLabDraftVisit(visit);
      setLabQueueError(null);
      setShowLabPaymentStep(true);
    } catch (err) {
      setLabDraftError(err instanceof ApiError ? err.message : "Could not start the Laboratory payment step.");
    } finally {
      setCreatingLabDraft(false);
    }
  }

  // Fires once `LabPaymentStep` observes the real invoice state reach
  // `Paid` (never assumed from department alone). Only NOW is the Queue
  // ticket created - the transactional guarantee this workflow requires:
  // if this call fails, no queue exists yet, and the receptionist gets an
  // explicit Retry rather than a silently-pretended success. Retrying is
  // safe - the backend's own draft-visit-status/duplicate-ticket guards
  // make a second `POST /queues` for the same paid visit a no-op-or-clear-
  // error, never a second ticket.
  async function handleLabPaid() {
    if (!labDraftVisit) return;
    setLabQueueError(null);
    const values = getValues();
    try {
      const result = await createQueue.mutateAsync({
        patientId: values.patientId,
        branchId: values.branchId,
        departmentId: values.departmentId,
        doctorId: null,
        serviceId: values.serviceId,
        priority: values.priority,
        notes: values.notes,
        visitId: labDraftVisit.id,
        visitClassification: values.visitClassification,
      });
      onOpenChange(false);
      onCreated?.(result.id);
    } catch {
      setLabQueueError("Payment was recorded, but the queue ticket could not be created. Click Retry to try again.");
    }
  }

  const onSubmit = handleSubmit(async (values) => {
    // Laboratory tickets never submit through this path - the "Create
    // Queue Ticket" button is replaced with "Proceed to Payment" below, but
    // pressing Enter in a text field still triggers native form submit, so
    // this is the real guard (defense in depth, matching the backend's own
    // rejection of a Laboratory queue with no visit_id).
    if (isLaboratoryDepartment) {
      await handleProceedToLabPayment();
      return;
    }
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

          {!showVitalsStep && !showLabPaymentStep ? (
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
                {/* Doctor rule: Laboratory tickets never require - and never
                    show - a doctor field, consistent with the backend
                    treating `doctor_id` as fully optional for this
                    department (see `QueueService`'s Doctor rule). Every
                    other department keeps the existing field exactly as
                    before. */}
                {!isLaboratoryDepartment ? (
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
                ) : null}
                {!isLaboratoryDepartment ? (
                  <div className="space-y-1.5">
                    <Label>Service</Label>
                    <SearchableSelect
                      value={serviceId}
                      onChange={(id) => setValue("serviceId", id, { shouldValidate: true })}
                      invalid={Boolean(errors.serviceId)}
                      disabled={vitalsSaved}
                      placeholder="Select service"
                      emptyLabel="No services match."
                      options={(services.data?.items ?? []).map((s) => ({
                        value: s.id,
                        label: `${s.service_name ?? s.name}${s.duration_minutes ? ` (${s.duration_minutes} min)` : ""}`,
                      }))}
                    />
                  </div>
                ) : null}
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

              {isLaboratoryDepartment ? (
                <div className="space-y-1.5">
                  <Label>Laboratory Services</Label>
                  <SearchableSelect
                    value=""
                    onChange={(id) => {
                      if (id && !labServiceIds.includes(id)) setLabServiceIds((prev) => [...prev, id]);
                    }}
                    placeholder="Select Laboratory Service"
                    emptyLabel="No services match."
                    // Already-selected services are excluded from the
                    // dropdown entirely - the same service can never be
                    // selected twice (no duplicate-quantity concept exists
                    // for a Laboratory test), so there's nothing to reject
                    // at click time; it simply isn't offered again.
                    options={(services.data?.items ?? [])
                      .filter((s) => !labServiceIds.includes(s.id))
                      .map((s) => ({ value: s.id, label: s.service_name ?? s.name }))}
                  />
                  {labServiceIds.length > 0 ? (
                    <div className="rounded-md border border-border">
                      <div className="divide-y divide-border">
                        {labServiceIds.map((id) => {
                          const svc = (services.data?.items ?? []).find((s) => s.id === id);
                          const price = Number(svc?.default_price ?? 0);
                          return (
                            <div key={id} className="flex items-center justify-between px-3 py-2 text-sm">
                              <span>{svc?.service_name ?? svc?.name ?? id}</span>
                              <span className="flex items-center gap-3">
                                <span className="tabular-nums">₱{price.toFixed(2)}</span>
                                <button
                                  type="button"
                                  className="text-xs text-destructive underline"
                                  onClick={() => setLabServiceIds((prev) => prev.filter((x) => x !== id))}
                                >
                                  Remove
                                </button>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                      <div className="flex items-center justify-between border-t border-border px-3 py-2 text-sm font-semibold">
                        <span>Total</span>
                        <span className="tabular-nums">
                          ₱
                          {labServiceIds
                            .reduce((sum, id) => sum + Number((services.data?.items ?? []).find((s) => s.id === id)?.default_price ?? 0), 0)
                            .toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">Select at least one Laboratory service to proceed.</p>
                  )}
                </div>
              ) : null}

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
              {isLaboratoryDepartment ? (
                <p className="text-xs text-muted-foreground">
                  Laboratory tickets are paid first - the next step creates and settles the invoice before the
                  queue ticket is raised.
                </p>
              ) : null}
              {labDraftError ? <p className="text-xs text-destructive">{labDraftError}</p> : null}
            </>
          ) : showVitalsStep && draftVisit ? (
            <PreQueueVitalsStep
              visitId={draftVisit.id}
              onSaved={() => {
                setVitalsSaved(true);
                setShowVitalsStep(false);
              }}
              onBack={() => setShowVitalsStep(false)}
            />
          ) : showLabPaymentStep && labDraftVisit ? (
            labQueueError ? (
              <div className="space-y-3">
                <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  {labQueueError}
                </div>
                <div className="flex justify-between pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowLabPaymentStep(false);
                      setLabQueueError(null);
                    }}
                  >
                    Back
                  </Button>
                  <Button type="button" onClick={handleLabPaid} disabled={createQueue.isPending}>
                    {createQueue.isPending ? "Retrying..." : "Retry"}
                  </Button>
                </div>
              </div>
            ) : (
              <LabPaymentStep
                visitId={labDraftVisit.id}
                serviceIds={labServiceIds}
                onPaid={handleLabPaid}
                onBack={() => setShowLabPaymentStep(false)}
              />
            )
          ) : null}

          {!showVitalsStep && !showLabPaymentStep ? (
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              {requiresVitals && !vitalsSaved ? (
                <Button type="button" onClick={handleEnterVitals} disabled={creatingDraft}>
                  {creatingDraft ? "Starting..." : "Enter Vitals"}
                </Button>
              ) : isLaboratoryDepartment ? (
                <Button
                  type="button"
                  onClick={handleProceedToLabPayment}
                  disabled={creatingLabDraft || labServiceIds.length === 0}
                >
                  {creatingLabDraft ? "Preparing..." : "Proceed to Payment"}
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
    // Reuses the same `addressLine` field the full Patients-module form
    // (`PatientFormDialog`) already registers - not a new address
    // structure, just the one existing free-text line surfaced here too.
    // Optional, matching the backend's nullable `address_line` column.
    addressLine: "",
  });

  useEffect(() => {
    if (open) {
      setForm({
        firstName: "", lastName: "", birthDate: "", gender: PatientGender.Male,
        civilStatus: PatientCivilStatus.Single, mobileNumber: "", addressLine: "",
      });
    }
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
          <div className="space-y-1.5">
            <Label>Address</Label>
            <Input value={form.addressLine} onChange={(e) => setForm((f) => ({ ...f, addressLine: e.target.value }))} />
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
