"use client";

import type { ComponentType } from "react";
import { CalendarDays, FlaskConical, Receipt, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/layout/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { usePatients } from "@/features/patients/hooks/use-patients";

/** Stat card. Pass `value` for a real, query-derived number; omit it (or pass
 * `undefined`) for modules that have no backend data source yet, which
 * renders an explicit "No data yet" empty state instead of a fake number. */
function StatCard({
  label,
  icon: Icon,
  value,
  isLoading,
}: {
  label: string;
  icon: ComponentType<{ className?: string }>;
  value?: number;
  isLoading?: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <div className="text-2xl font-semibold text-foreground">
            {value !== undefined ? value.toLocaleString() : "—"}
          </div>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          {value !== undefined ? "Live count" : "No data yet"}
        </p>
      </CardContent>
    </Card>
  );
}

/**
 * Dashboard home. The Patients stat card is wired to a real backend query
 * (count of non-archived patients for the current clinic). The other stat
 * cards (appointments, invoices, lab requests) show an explicit empty state
 * because those modules are out of scope for this phase and have no backend
 * data source to query.
 */
/** Loading placeholder for the welcome banner while the current user loads. */
function WelcomeBannerSkeleton() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="space-y-2">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>
      <Skeleton className="h-6 w-28 rounded-full" />
    </div>
  );
}

export default function DashboardPage() {
  const { data: user, isLoading } = useCurrentUser();
  const { data: patientsPage, isLoading: patientsLoading } = usePatients({ page: 1, pageSize: 1 });
  const patientsTotal = patientsPage?.meta.total;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <WelcomeBannerSkeleton />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Patients" icon={Users} />
          <StatCard label="Today's appointments" icon={CalendarDays} />
          <StatCard label="Pending invoices" icon={Receipt} />
          <StatCard label="Lab requests" icon={FlaskConical} />
        </div>
      </div>
    );
  }

  const fullName = user ? `${user.firstName} ${user.lastName}` : "there";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Welcome back, {fullName}</h1>
          <p className="text-sm text-muted-foreground">
            {user?.clinic?.name ?? "Your clinic"}
            {user?.branch?.name ? ` · ${user.branch.name}` : ""}
            {user?.role ? ` · ${user.role}` : ""}
          </p>
        </div>
        <Badge variant="outline">Foundation preview</Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Patients" icon={Users} value={patientsTotal} isLoading={patientsLoading} />
        <StatCard label="Today's appointments" icon={CalendarDays} />
        <StatCard label="Pending invoices" icon={Receipt} />
        <StatCard label="Lab requests" icon={FlaskConical} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent>
            <EmptyState
              title="No recent activity"
              description="Activity across patients, appointments and billing will show up here once those modules are built."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Upcoming appointments</CardTitle>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={CalendarDays}
              title="No appointments scheduled"
              description="This is a placeholder widget for the appointments feature."
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
