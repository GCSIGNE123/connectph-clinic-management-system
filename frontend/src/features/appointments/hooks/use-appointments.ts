"use client";

import { useQuery } from "@tanstack/react-query";
import { appointmentsApi } from "@/features/appointments/api/appointments-api";
import type { AppointmentListParams } from "@/features/appointments/types";

export const appointmentKeys = {
  all: ["appointments"] as const,
  list: (params: AppointmentListParams) => ["appointments", "list", params] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
  history: (id: string) => ["appointments", "history", id] as const,
  forPatient: (patientId: string) => ["appointments", "patient", patientId] as const,
  slots: (doctorId: string, date: string) => ["appointments", "slots", doctorId, date] as const,
  calendar: (params: AppointmentListParams) => ["appointments", "calendar", params] as const,
  schedule: (doctorId: string) => ["appointments", "schedule", doctorId] as const,
  receptionDashboard: (date?: string) => ["appointments", "dashboard", "reception", date] as const,
  doctorDashboard: (doctorId: string, date?: string) => ["appointments", "dashboard", "doctor", doctorId, date] as const,
};

export function useAppointments(params: AppointmentListParams) {
  return useQuery({
    queryKey: appointmentKeys.list(params),
    queryFn: () => appointmentsApi.list(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useAppointmentDetail(id: string | null) {
  return useQuery({
    queryKey: appointmentKeys.detail(id ?? ""),
    queryFn: () => appointmentsApi.get(id as string),
    enabled: Boolean(id),
  });
}

export function useAppointmentCalendar(params: AppointmentListParams) {
  return useQuery({
    queryKey: appointmentKeys.calendar(params),
    queryFn: () => appointmentsApi.calendar(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useAvailableSlots(doctorId: string | null, date: string | null, branchId?: string) {
  return useQuery({
    queryKey: appointmentKeys.slots(doctorId ?? "", date ?? ""),
    queryFn: () => appointmentsApi.availableSlots(doctorId as string, date as string, branchId),
    enabled: Boolean(doctorId && date),
  });
}

export function useDoctorSchedule(doctorId: string | null) {
  return useQuery({
    queryKey: appointmentKeys.schedule(doctorId ?? ""),
    queryFn: () => appointmentsApi.getSchedule(doctorId as string),
    enabled: Boolean(doctorId),
  });
}

export function usePatientAppointments(
  patientId: string | null,
  params?: { dateFrom?: string; dateTo?: string }
) {
  return useQuery({
    queryKey: [...appointmentKeys.forPatient(patientId ?? ""), params ?? {}],
    queryFn: () => appointmentsApi.listForPatient(patientId as string, params),
    enabled: Boolean(patientId),
  });
}
