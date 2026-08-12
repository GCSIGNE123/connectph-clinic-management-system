"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";

const SYSTEM_STATUS_ROLES = new Set(["Owner", "Administrator"]);

// Same "poll on a short interval so the panel self-heals without any
// mutation-driven cache invalidation" pattern used by the Owner Dashboard
// (see frontend/src/features/analytics/hooks/use-analytics.ts) - connectivity
// state changes independently of anything this page itself does.
// Tightened from 30s to 10s for Post-RC1 Phase 2 Milestone 2 (Cloud Backup)
// per spec - this page only; every other page keeps its own interval.
const REFETCH_INTERVAL_MS = 10_000;

// Post-RC1 Phase 2.5: Production Cloud Deployment - frontend build version.
// No clean way to have the backend report a *frontend* health/version (the
// frontend is a separate Vercel deployment, possibly on a different host
// entirely), so this is self-reported by the frontend build itself via
// NEXT_PUBLIC_APP_VERSION (falls back to package.json's version at build
// time - see next.config / package.json). Documented choice, not an
// oversight.
const FRONTEND_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "unknown";

interface SystemStatusResponse {
  deployment_mode: string;
  app_version: string;
  local_status: string;
  cloud_status: "up" | "down" | "not_configured" | string;
  database_status: "reachable" | "unreachable" | string;
  internet_status: "reachable" | "unreachable" | string;
  last_successful_cloud_connection: string | null;
  last_checked_at: string | null;
  // Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync)
  pending_sync_jobs: number;
  last_successful_sync_at: string | null;
  last_failed_sync_at: string | null;
  last_failed_sync_reason: string | null;
  total_uploaded_today: number;
  retry_queue_count: number;
  average_sync_time_ms: number | null;
}

function StatusBadge({ ok, label }: { ok: boolean | null; label: string }) {
  const color =
    ok === null
      ? "bg-muted text-muted-foreground"
      : ok
        ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
        : "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>{label}</span>;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return "N/A";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Post-RC1 Phase 2 Milestone 1: Cloud Readiness - Admin System Status panel.
 *
 * Pure display/groundwork: shows the Connectivity Service's current state
 * (`GET /system/status`) so an admin can see, at a glance, whether this
 * install is fully local (the day-one state for every existing clinic -
 * Cloud Server Status reads "Not Configured", not "Down") or has a cloud
 * endpoint configured and reachable. Does not switch any app behavior.
 *
 * Gated to Owner/Administrator only, the same role set and pattern as the
 * Owner Dashboard, TV Displays, and Legacy Migration Wizard pages (backend
 * enforces this regardless via `require_system_status_role`; this is a
 * client-side UX short-circuit for a non-privileged user who navigates here
 * directly).
 */
export default function SystemStatusPage() {
  const { data: currentUser, isLoading: userLoading } = useCurrentUser();
  const canView = Boolean(currentUser && SYSTEM_STATUS_ROLES.has(currentUser.role ?? ""));

  const { data, isLoading, isError } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => apiClient.get<SystemStatusResponse>("/system/status"),
    refetchInterval: REFETCH_INTERVAL_MS,
    staleTime: 15_000,
    enabled: canView,
  });

  if (!userLoading && currentUser && !canView) {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-2 text-center">
        <h1 className="text-lg font-semibold">Access restricted</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          System Status is available to Owner and Administrator accounts only.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">System Status</h1>
        <p className="text-sm text-muted-foreground">
          Local/cloud connectivity groundwork for the upcoming hybrid deployment (Phase 2 Milestone 1). This
          install is currently running in <strong>{data?.deployment_mode ?? "local"}</strong> mode. Nothing
          here changes how the clinic workflows behave today.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Connectivity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Checking status...</p>
          ) : isError ? (
            <p className="text-sm text-red-600">Could not load system status.</p>
          ) : (
            <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Local Server</dt>
                <dd>
                  <StatusBadge ok={data?.local_status === "up"} label="Up" />
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Cloud Server</dt>
                <dd>
                  {data?.cloud_status === "up" ? (
                    <StatusBadge ok={true} label="Up" />
                  ) : data?.cloud_status === "down" ? (
                    <StatusBadge ok={false} label="Down" />
                  ) : (
                    <StatusBadge ok={null} label="Not Configured" />
                  )}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Database</dt>
                <dd>
                  <StatusBadge
                    ok={data?.database_status === "reachable"}
                    label={data?.database_status === "reachable" ? "Reachable" : "Unreachable"}
                  />
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Internet</dt>
                <dd>
                  <StatusBadge
                    ok={data?.internet_status === "reachable"}
                    label={data?.internet_status === "reachable" ? "Reachable" : "Unreachable"}
                  />
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3 sm:col-span-2">
                <dt className="text-sm font-medium">Last Successful Cloud Connection</dt>
                <dd className="text-sm text-muted-foreground">
                  {formatTimestamp(data?.last_successful_cloud_connection ?? null)}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Backend Version</dt>
                <dd className="text-sm font-semibold">{data?.app_version ?? "unknown"}</dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Frontend Version</dt>
                <dd className="text-sm font-semibold">{FRONTEND_VERSION}</dd>
              </div>
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cloud Backup - Sync Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Checking sync status...</p>
          ) : isError ? (
            <p className="text-sm text-red-600">Could not load sync status.</p>
          ) : (
            <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Pending Sync Jobs</dt>
                <dd className="text-sm font-semibold">{data?.pending_sync_jobs ?? 0}</dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Retry Queue</dt>
                <dd className="text-sm font-semibold">{data?.retry_queue_count ?? 0}</dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Total Uploaded Today</dt>
                <dd className="text-sm font-semibold">{data?.total_uploaded_today ?? 0}</dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3">
                <dt className="text-sm font-medium">Average Sync Time</dt>
                <dd className="text-sm font-semibold">{formatDuration(data?.average_sync_time_ms ?? null)}</dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3 sm:col-span-2">
                <dt className="text-sm font-medium">Last Successful Sync</dt>
                <dd className="text-sm text-muted-foreground">{formatTimestamp(data?.last_successful_sync_at ?? null)}</dd>
              </div>
              <div className="flex items-center justify-between gap-2 rounded-md border p-3 sm:col-span-2">
                <dt className="text-sm font-medium">Last Failed Sync</dt>
                <dd className="text-right text-sm text-muted-foreground">
                  {formatTimestamp(data?.last_failed_sync_at ?? null)}
                  {data?.last_failed_sync_reason ? (
                    <div className="mt-1 max-w-xs truncate text-xs text-red-600" title={data.last_failed_sync_reason}>
                      {data.last_failed_sync_reason}
                    </div>
                  ) : null}
                </dd>
              </div>
            </dl>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
