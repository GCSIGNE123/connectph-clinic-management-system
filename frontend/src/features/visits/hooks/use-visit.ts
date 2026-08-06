"use client";

import { useQuery } from "@tanstack/react-query";
import { visitsApi } from "@/features/visits/api/visits-api";
import { visitKeys } from "@/features/visits/hooks/use-visits";

/** Single visit detail (includes the embedded timeline). */
export function useVisit(id: string | null) {
  return useQuery({
    queryKey: visitKeys.detail(id ?? ""),
    queryFn: () => visitsApi.get(id as string),
    enabled: Boolean(id),
  });
}

/** Standalone timeline fetch, for cases that only need the timeline without
 * the rest of the visit detail payload. */
export function useVisitTimeline(id: string | null) {
  return useQuery({
    queryKey: visitKeys.timeline(id ?? ""),
    queryFn: () => visitsApi.getTimeline(id as string),
    enabled: Boolean(id),
  });
}
