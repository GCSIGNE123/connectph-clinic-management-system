"use client";

import { useQuery } from "@tanstack/react-query";
import { doctorWorkspaceApi } from "@/features/doctor-workspace/api/doctor-workspace-api";

export const doctorWorkspaceKeys = {
  all: ["doctor-workspace"] as const,
  dashboard: (doctorId?: string) => ["doctor-workspace", "dashboard", doctorId ?? "self"] as const,
  queue: (doctorId?: string) => ["doctor-workspace", "queue", doctorId ?? "self"] as const,
};

export function useDoctorDashboard(doctorId?: string) {
  return useQuery({
    queryKey: doctorWorkspaceKeys.dashboard(doctorId),
    queryFn: () => doctorWorkspaceApi.getDashboard(doctorId),
    refetchInterval: 30_000,
  });
}
