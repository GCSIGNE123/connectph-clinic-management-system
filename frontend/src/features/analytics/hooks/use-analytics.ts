"use client";

import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/features/analytics/api/analytics-api";
import type { ReportFilters } from "@/features/analytics/types";

/**
 * This dashboard has no direct mutations of its own to hook `onSuccess`
 * cache-invalidation into (it is a pure read/aggregation layer over data
 * mutated elsewhere in the app - a new payment, a completed consultation, a
 * new lab order all change what these numbers should read). Per the
 * project's documented "stale cache" lesson (see docs/TESTING.md), the
 * fix here is a *polling* policy rather than mutation-driven invalidation:
 * every query below refetches on a short interval AND on window refocus, so
 * the Owner Dashboard self-heals within ~30s of any underlying change
 * without requiring every other feature's mutations to know this dashboard
 * exists. `staleTime` is kept shorter than `refetchInterval` so a manual
 * back-navigation to this page also gets a fresh fetch, not a stale cache
 * hit.
 */
const REFETCH_INTERVAL_MS = 30_000;
const STALE_TIME_MS = 15_000;

export const analyticsKeys = {
  dashboard: () => ["analytics", "dashboard"] as const,
  activityFeed: () => ["analytics", "activity-feed"] as const,
  alerts: () => ["analytics", "alerts"] as const,
  report: (report: string, filters: ReportFilters) => ["analytics", "report", report, filters] as const,
};

function liveQueryOptions() {
  return {
    refetchInterval: REFETCH_INTERVAL_MS,
    refetchOnWindowFocus: true,
    staleTime: STALE_TIME_MS,
  };
}

export function useOwnerDashboard() {
  return useQuery({
    queryKey: analyticsKeys.dashboard(),
    queryFn: () => analyticsApi.getDashboard(),
    ...liveQueryOptions(),
  });
}

export function useActivityFeed(limit = 50) {
  return useQuery({
    queryKey: analyticsKeys.activityFeed(),
    queryFn: () => analyticsApi.getActivityFeed(limit),
    ...liveQueryOptions(),
  });
}

export function useOwnerAlerts() {
  return useQuery({
    queryKey: analyticsKeys.alerts(),
    queryFn: () => analyticsApi.getAlerts(),
    ...liveQueryOptions(),
  });
}

export function usePatientReport(filters: ReportFilters) {
  return useQuery({
    queryKey: analyticsKeys.report("patients", filters),
    queryFn: () => analyticsApi.getPatientReport(filters),
    staleTime: STALE_TIME_MS,
  });
}

export function useDoctorReport(filters: ReportFilters) {
  return useQuery({
    queryKey: analyticsKeys.report("doctors", filters),
    queryFn: () => analyticsApi.getDoctorReport(filters),
    staleTime: STALE_TIME_MS,
  });
}

export function useRevenueReport(filters: ReportFilters) {
  return useQuery({
    queryKey: analyticsKeys.report("revenue", filters),
    queryFn: () => analyticsApi.getRevenueReport(filters),
    staleTime: STALE_TIME_MS,
  });
}

export function useQueueReport(filters: ReportFilters) {
  return useQuery({
    queryKey: analyticsKeys.report("queue", filters),
    queryFn: () => analyticsApi.getQueueReport(filters),
    staleTime: STALE_TIME_MS,
  });
}

export function useLaboratoryReport(filters: ReportFilters) {
  return useQuery({
    queryKey: analyticsKeys.report("laboratory", filters),
    queryFn: () => analyticsApi.getLaboratoryReport(filters),
    staleTime: STALE_TIME_MS,
  });
}

export function useAppointmentReport(filters: ReportFilters) {
  return useQuery({
    queryKey: analyticsKeys.report("appointments", filters),
    queryFn: () => analyticsApi.getAppointmentReport(filters),
    staleTime: STALE_TIME_MS,
  });
}
