"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { appointmentsApi } from "@/features/appointments/api/appointments-api";
import { appointmentKeys } from "@/features/appointments/hooks/use-appointments";
import { queueKeys } from "@/features/queue/hooks/use-queues";
import { visitKeys } from "@/features/visits/hooks/use-visits";
import type { CreateAppointmentInput, RescheduleAppointmentInput } from "@/features/appointments/types";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/**
 * Every mutation below invalidates `appointmentKeys.all` unconditionally.
 * `check-in` additionally invalidates `visitKeys.all` and `queueKeys.all`
 * because it creates a real Queue ticket AND a linked Visit in the same
 * backend transaction (see `services/appointment_service.py::check_in_appointment`,
 * which calls the existing `QueueService.create_queue()`) - this is the
 * exact cross-entity cache-invalidation lesson documented in
 * docs/TESTING.md across Phases 7/8/9/10: forgetting to invalidate the
 * OTHER feature's keys leaves the Reception Queue screen and the Visit
 * Timeline silently stale even though the backend state is correct.
 */

export function useCreateAppointment() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: CreateAppointmentInput) => appointmentsApi.create(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      toast({ title: "Appointment booked", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not book appointment", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useConfirmAppointment() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => appointmentsApi.confirm(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      toast({ title: "Appointment confirmed", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not confirm", description: errorMessage(error, "Please try again."), variant: "error" }),
  });
}

export function useRescheduleAppointment() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: RescheduleAppointmentInput }) => appointmentsApi.reschedule(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      toast({ title: "Appointment rescheduled", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not reschedule", description: errorMessage(error, "That slot may not be valid."), variant: "error" }),
  });
}

export function useCancelAppointment() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => appointmentsApi.cancel(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      toast({ title: "Appointment cancelled", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not cancel", description: errorMessage(error, "Please try again."), variant: "error" }),
  });
}

/** `onShiftRequired` (item 7): see `use-payments.ts::useRecordPayment` doc -
 * same pattern, since check-in is now also gated behind "Receptionist has
 * an open shift" (it delegates to `QueueService.create_queue()` on the
 * backend, the same enforcement point walk-in queueing uses). */
export function useCheckInAppointment(onShiftRequired?: (error: unknown) => boolean) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => appointmentsApi.checkIn(id),
    onSuccess: () => {
      // The critical multi-entity invalidation: a new Queue ticket AND a
      // new Visit now exist, so the Reception Queue screen, the Visits
      // list/detail, and the Doctor Dashboard must all refetch alongside
      // this feature's own appointment list/detail.
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      queryClient.invalidateQueries({ queryKey: queueKeys.all });
      queryClient.invalidateQueries({ queryKey: visitKeys.all });
      toast({ title: "Checked in - queue ticket and visit created", variant: "success" });
    },
    onError: (error) => {
      if (onShiftRequired?.(error)) return;
      toast({ title: "Could not check in", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useCompleteAppointment() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => appointmentsApi.complete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      queryClient.invalidateQueries({ queryKey: visitKeys.all });
      toast({ title: "Appointment completed", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not complete", description: errorMessage(error, "Please try again."), variant: "error" }),
  });
}

export function useMarkNoShow() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => appointmentsApi.noShow(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      toast({ title: "Marked as No Show", variant: "success" });
    },
    onError: (error) => toast({ title: "Could not update", description: errorMessage(error, "Please try again."), variant: "error" }),
  });
}
