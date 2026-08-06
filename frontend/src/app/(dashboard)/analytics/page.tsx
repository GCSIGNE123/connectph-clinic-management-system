"use client";

import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useOwnerDashboard, useActivityFeed, useOwnerAlerts } from "@/features/analytics/hooks/use-analytics";
import { StatCardGrid } from "@/features/analytics/components/StatCardGrid";
import { ActivityFeed } from "@/features/analytics/components/ActivityFeed";
import { AlertsPanel } from "@/features/analytics/components/AlertsPanel";
import {
  AppointmentReportPanel,
  DoctorReportPanel,
  LaboratoryReportPanel,
  PatientReportPanel,
  QueueReportPanel,
  RevenueReportPanel,
} from "@/features/analytics/components/ReportPanels";

const ANALYTICS_ROLES = new Set(["Owner", "Administrator"]);

export default function OwnerDashboardPage() {
  const { data: currentUser, isLoading: userLoading } = useCurrentUser();
  const { data: dashboard, isLoading: dashboardLoading } = useOwnerDashboard();
  const { data: activity, isLoading: activityLoading } = useActivityFeed();
  const { data: alerts, isLoading: alertsLoading } = useOwnerAlerts();

  // The backend enforces this regardless (every /analytics/* endpoint 403s
  // for non-Owner/Administrator roles) - this is a client-side UX
  // short-circuit so a non-privileged user who navigates here directly sees
  // a clear message instead of a page full of failed-request error states.
  if (!userLoading && currentUser && !ANALYTICS_ROLES.has(currentUser.role ?? "")) {
    return (
      <div className="flex min-h-[50vh] flex-col items-center justify-center gap-2 text-center">
        <h1 className="text-lg font-semibold">Access restricted</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          The Owner Dashboard is available to Owner and Administrator accounts only.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="owner-dashboard-page">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Owner Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Clinic-wide performance, activity, and reports{dashboard ? ` for ${dashboard.today}` : ""}.
        </p>
      </div>

      <AlertsPanel alerts={alerts} isLoading={alertsLoading} />

      <StatCardGrid dashboard={dashboard} isLoading={dashboardLoading} />

      <ActivityFeed items={activity} isLoading={activityLoading} />

      <div>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Reports</h2>
        <div className="space-y-6">
          <PatientReportPanel />
          <DoctorReportPanel />
          <RevenueReportPanel />
          <QueueReportPanel />
          <LaboratoryReportPanel />
          <AppointmentReportPanel />
        </div>
      </div>
    </div>
  );
}
