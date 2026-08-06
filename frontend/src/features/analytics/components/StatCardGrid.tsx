"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { OwnerDashboard } from "@/features/analytics/types";
import { formatCurrency, formatDuration, formatNumber } from "@/features/analytics/lib/format";

export interface StatCardGridProps {
  dashboard: OwnerDashboard | undefined;
  isLoading: boolean;
}

interface StatDef {
  label: string;
  value: (d: OwnerDashboard) => string;
}

interface StatGroup {
  title: string;
  stats: StatDef[];
}

const GROUPS: StatGroup[] = [
  {
    title: "Today's Activity",
    stats: [
      { label: "Patients Today", value: (d) => formatNumber(d.stats.patientsToday) },
      { label: "New Patients Today", value: (d) => formatNumber(d.stats.newPatientsToday) },
      { label: "Appointments Today", value: (d) => formatNumber(d.stats.appointmentsToday) },
      { label: "Walk-ins Today", value: (d) => formatNumber(d.stats.walkInsToday) },
      { label: "Completed Consultations", value: (d) => formatNumber(d.stats.completedConsultationsToday) },
      { label: "Cancelled Visits", value: (d) => formatNumber(d.stats.cancelledVisitsToday) },
      { label: "No Shows", value: (d) => formatNumber(d.stats.noShowsToday) },
    ],
  },
  {
    title: "Clinical",
    stats: [
      { label: "Laboratory Orders Today", value: (d) => formatNumber(d.stats.laboratoryOrdersToday) },
      { label: "Prescriptions Issued", value: (d) => formatNumber(d.stats.prescriptionsIssuedToday) },
      { label: "Doctors On Duty", value: (d) => formatNumber(d.stats.doctorsOnDuty) },
      { label: "Avg. Waiting Time", value: (d) => formatDuration(d.stats.avgWaitingSeconds) },
      { label: "Avg. Consultation Time", value: (d) => formatDuration(d.stats.avgConsultationSeconds) },
    ],
  },
  {
    title: "Financial",
    stats: [
      { label: "Collected Revenue Today", value: (d) => formatCurrency(d.stats.collectedRevenueToday) },
      { label: "Outstanding Balance", value: (d) => formatCurrency(d.stats.outstandingBalance) },
      { label: "Pending Payments", value: (d) => `${formatNumber(d.stats.pendingPaymentsCount)} (${formatCurrency(d.stats.pendingPaymentsAmount)})` },
    ],
  },
];

export function StatCardGrid({ dashboard, isLoading }: StatCardGridProps) {
  if (isLoading || !dashboard) {
    return (
      <div className="space-y-6">
        {GROUPS.map((group) => (
          <div key={group.title}>
            <Skeleton className="mb-2 h-4 w-32" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {group.stats.map((s) => (
                <Skeleton key={s.label} className="h-24 w-full rounded-lg" />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="owner-stat-card-grid">
      {GROUPS.map((group) => (
        <div key={group.title}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.title}</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {group.stats.map((stat) => (
              <Card key={stat.label}>
                <CardContent className="p-4">
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                  <p className="mt-1 text-xl font-semibold">{stat.value(dashboard)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
