"use client";

import { useEffect, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { useQueueDetail } from "@/features/queue/hooks/use-queues";
import { useUpdateQueue } from "@/features/queue/hooks/use-queue-mutations";
import { editQueueSchema, type EditQueueInput } from "@/features/queue/schemas/queue-schemas";
import { QUEUE_PRIORITY_LABELS, QueuePriority, VISIT_CLASSIFICATION_LABELS, VisitClassification } from "@/features/queue/types";

interface SimpleOption {
  id: string;
  name: string;
  status?: string;
  department_id?: string | null;
  branch_id?: string | null;
  duration_minutes?: number | null;
  service_name?: string;
  first_name?: string;
  last_name?: string;
}

const departmentsApi = createCrudApi<SimpleOption>("/departments");
const doctorsApi = createCrudApi<SimpleOption>("/doctors");
const servicesApi = createCrudApi<SimpleOption>("/services");

export interface EditQueueDialogProps {
  queueId: string | null;
  onOpenChange: (open: boolean) => void;
}

/**
 * Edits a queue ticket's routing - department, doctor, service, priority,
 * classification, and notes. Deliberately a subset of `NewQueueDialog`'s
 * fields (patient and branch are not editable here, matching the backend's
 * own `QueueUpdate` schema - reassigning the patient or branch isn't a
 * "routing edit", it's effectively a different ticket). The full detail
 * (including `notes`, which the table's list view doesn't carry) is fetched
 * fresh via `useQueueDetail` so submitting never silently blanks a field
 * the receptionist never saw. Blocked (dialog won't even open meaningfully)
 * once the backend's own closed-ticket guard applies - see
 * `QueueService.update_queue`'s "Cannot edit a closed queue ticket." - the
 * table only ever renders the Edit action for non-Completed/Cancelled rows.
 */
export function EditQueueDialog({ queueId, onOpenChange }: EditQueueDialogProps) {
  const { data: queue, isLoading } = useQueueDetail(queueId);
  const updateQueue = useUpdateQueue(queueId ?? "");

  const departments = useQuery({
    queryKey: ["queue-edit", "departments"],
    queryFn: () => departmentsApi.list({ status: "Active", limit: 100 }),
    enabled: Boolean(queueId),
  });
  const doctors = useQuery({
    queryKey: ["queue-edit", "doctors"],
    queryFn: () => doctorsApi.list({ status: "Active", limit: 100 }),
    enabled: Boolean(queueId),
  });
  const services = useQuery({
    queryKey: ["queue-edit", "services"],
    queryFn: () => servicesApi.list({ status: "Active", limit: 100 }),
    enabled: Boolean(queueId),
  });

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<EditQueueInput>({
    resolver: zodResolver(editQueueSchema),
    defaultValues: {
      departmentId: "", doctorId: "", serviceId: "",
      priority: QueuePriority.Normal, notes: "", visitClassification: VisitClassification.Regular,
    },
  });

  // Re-seeds the form every time a (different) ticket's detail finishes
  // loading - not just on `queueId` change - so the fields are never left
  // showing the PREVIOUS ticket's values while this one is still fetching.
  useEffect(() => {
    if (queue) {
      reset({
        departmentId: queue.departmentId,
        doctorId: queue.doctorId ?? "",
        serviceId: queue.serviceId,
        priority: queue.priority,
        notes: queue.notes ?? "",
        visitClassification: queue.visitClassification,
      });
    }
  }, [queue, reset]);

  const departmentId = watch("departmentId");
  const serviceId = watch("serviceId");

  const filteredDoctors = useMemo(() => {
    const items = doctors.data?.items ?? [];
    return items.filter((d) => !departmentId || !d.department_id || d.department_id === departmentId);
  }, [doctors.data, departmentId]);

  const onSubmit = handleSubmit(async (values) => {
    if (!queueId) return;
    try {
      await updateQueue.mutateAsync({
        departmentId: values.departmentId || undefined,
        doctorId: values.doctorId || null,
        serviceId: values.serviceId || undefined,
        priority: values.priority,
        notes: values.notes,
        visitClassification: values.visitClassification,
      });
      onOpenChange(false);
    } catch {
      // Already surfaced via the mutation's onError toast.
    }
  });

  return (
    <Dialog open={Boolean(queueId)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" onClose={() => onOpenChange(false)}>
        <DialogHeader>
          <DialogTitle>Edit Queue Ticket {queue?.queueNumber ?? ""}</DialogTitle>
        </DialogHeader>

        {/* Also waits on the option lists, not just the ticket detail - the
            form's `reset()` below sets e.g. `departmentId` to a real value
            as soon as `queue` loads, but if that fires before the
            <Select>'s own <option>s exist yet, the browser has nowhere to
            apply the value and silently falls back to the empty
            placeholder (and nothing re-applies it once the options do
            arrive, since `reset()` isn't re-triggered by that). Waiting
            for both closes the race instead of only mostly avoiding it. */}
        {isLoading || !queue || !departments.data || !doctors.data || !services.data ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
              <span className="text-muted-foreground">Patient:</span>{" "}
              <span className="font-medium text-foreground">{queue.patientName ?? "—"}</span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Department</Label>
                <Select {...register("departmentId")} invalid={Boolean(errors.departmentId)}>
                  <option value="">Select department</option>
                  {(departments.data?.items ?? []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Doctor (optional)</Label>
                <Select {...register("doctorId")}>
                  <option value="">Any / unassigned</option>
                  {filteredDoctors.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.first_name} {d.last_name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Service</Label>
                <SearchableSelect
                  value={serviceId ?? ""}
                  onChange={(id) => setValue("serviceId", id, { shouldValidate: true })}
                  invalid={Boolean(errors.serviceId)}
                  placeholder="Select service"
                  emptyLabel="No services match."
                  options={(services.data?.items ?? []).map((s) => ({
                    value: s.id,
                    label: `${s.service_name ?? s.name}${s.duration_minutes ? ` (${s.duration_minutes} min)` : ""}`,
                  }))}
                />
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
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Notes (optional)</Label>
              <Textarea rows={2} {...register("notes")} />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting || updateQueue.isPending}>
                {updateQueue.isPending ? "Saving..." : "Save Changes"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
