"use client";

import { useQuery } from "@tanstack/react-query";
import { visitsApi } from "@/features/visits/api/visits-api";
import type { VisitListParams } from "@/features/visits/types";

export const visitKeys = {
  all: ["visits"] as const,
  list: (params: VisitListParams) => ["visits", "list", params] as const,
  detail: (id: string) => ["visits", "detail", id] as const,
  timeline: (id: string) => ["visits", "timeline", id] as const,
  forPatient: (patientId: string, page: number) => ["visits", "patient", patientId, page] as const,
};

/** Visit List: search/filter/paginate. */
export function useVisits(params: VisitListParams) {
  return useQuery({
    queryKey: visitKeys.list(params),
    queryFn: () => visitsApi.list(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useVisitsForPatient(
  patientId: string | null,
  page = 1,
  pageSize = 10,
  dateRange?: { dateFrom?: string; dateTo?: string }
) {
  return useQuery({
    queryKey: [...visitKeys.forPatient(patientId ?? "", page), dateRange ?? {}],
    queryFn: () => visitsApi.listForPatient(patientId as string, { page, pageSize, ...dateRange }),
    enabled: Boolean(patientId),
    placeholderData: (previousData) => previousData,
  });
}
