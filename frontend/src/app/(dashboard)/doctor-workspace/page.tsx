"use client";

import type { ComponentType } from "react";
import { CalendarClock, CheckCircle2, Clock, PhoneCall, PlayCircle, SkipForward, Stethoscope, Timer, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useDoctorDashboard } from "@/features/doctor-workspace/hooks/use-doctor-dashboard";
import { useDoctorQueue, useDoctorWorkspaceRealtime } from "@/features/doctor-workspace/hooks/use-doctor-queue";
import { useDoctorSession, useNextPatient, useStartDoctorSession } from "@/features/doctor-workspace/hooks/use-doctor-session";
import { DoctorQueueTable } from "@/features/doctor-workspace/components/DoctorQueueTable";
import { formatDate } from "@/lib/utils";

function StatCard({
  label,
  icon: Icon,
  value,
  isLoading,
}: {
  label: string;
  icon: ComponentType<{ className?: string }>;
  value?: string | number;
  isLoading?: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </CardHeader>
      <CardContent>
        {isLoading ? <Skeleton className="h-8 w-16" /> : <div className="text-2xl font-semibold text-foreground">{value ?? "—"}</div>}
      </CardContent>
    </Card>
  );
}

function formatAvgDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "No data yet";
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "<1 min";
  return `${minutes} min`;
}

export default function DoctorWorkspacePage() {
  const { data: currentUser, isLoading: userLoading } = useCurrentUser();
  const { data: dashboard, isLoading: dashboardLoading } = useDoctorDashboard();
  const { data: queueItems, isLoading: queueLoading } = useDoctorQueue();
  useDoctorWorkspaceRealtime();

  const isReadOnly = currentUser?.role === "Receptionist";
  // Item 14: Doctor Session Control is a Doctor-only self-service action
  // (Owner/Administrator can view any doctor's dashboard via `doctorId`,
  // but "Start Receiving Patients"/"Next Patient" are the doctor's own
  // controls over their own day, not an admin override).
  const isDoctor = currentUser?.role === "Doctor";
  const { data: session } = useDoctorSession(undefined, isDoctor);
  const startSession = useStartDoctorSession(undefined);
  const nextPatient = useNextPatient(undefined);
  const today = formatDate(new Date());

  if (userLoading) {
    return <SkeletonList rows={6} />;
  }

  if (currentUser && !["Owner", "Administrator", "Doctor", "Receptionist"].includes(currentUser.role)) {
    return (
      <EmptyState
        title="No access"
        description="The Doctor Workspace is only available to Doctor, Administrator, Owner, and Receptionist accounts."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-foreground">Doctor Workspace</h1>
        <p className="text-sm text-muted-foreground">
          {today}
          {dashboard?.doctorName ? ` · ${dashboard.doctorName}` : ""}
          {dashboard?.branchName ? ` · ${dashboard.branchName}` : ""}
          {dashboard?.departmentName ? ` · ${dashboard.departmentName}` : ""}
        </p>
      </div>

      {isDoctor ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
            <div className="text-sm text-muted-foreground">
              {session?.active ? (
                <span className="text-foreground">
                  Session active — receiving patients since{" "}
                  {session.started_at ? new Date(session.started_at).toLocaleTimeString() : ""}
                </span>
              ) : (
                <span>You have not started receiving patients today.</span>
              )}
            </div>
            <div className="flex gap-2">
              {!session?.active ? (
                <Button onClick={() => startSession.mutate()} disabled={startSession.isPending}>
                  <PlayCircle className="mr-2 h-4 w-4" aria-hidden="true" />
                  Start Receiving Patients
                </Button>
              ) : (
                <Button variant="outline" onClick={() => nextPatient.mutate()} disabled={nextPatient.isPending}>
                  <SkipForward className="mr-2 h-4 w-4" aria-hidden="true" />
                  Next Patient
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Waiting" icon={Clock} value={dashboard?.stats.waiting} isLoading={dashboardLoading} />
        <StatCard label="Called" icon={PhoneCall} value={dashboard?.stats.called} isLoading={dashboardLoading} />
        <StatCard label="Serving" icon={Stethoscope} value={dashboard?.stats.serving} isLoading={dashboardLoading} />
        <StatCard label="Completed Today" icon={CheckCircle2} value={dashboard?.stats.completedToday} isLoading={dashboardLoading} />
        <StatCard label="Cancelled" icon={XCircle} value={dashboard?.stats.cancelled} isLoading={dashboardLoading} />
        <StatCard
          label="Avg Consultation Time"
          icon={Timer}
          value={formatAvgDuration(dashboard?.stats.avgConsultationSeconds)}
          isLoading={dashboardLoading}
        />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center gap-2 space-y-0">
          <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle>Today&apos;s Queue</CardTitle>
        </CardHeader>
        <CardContent>
          {queueLoading ? <SkeletonList rows={5} /> : <DoctorQueueTable items={queueItems ?? []} readOnly={isReadOnly} />}
        </CardContent>
      </Card>
    </div>
  );
}
