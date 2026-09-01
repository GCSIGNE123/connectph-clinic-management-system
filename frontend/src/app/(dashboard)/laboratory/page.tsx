"use client";

import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { useLaboratoryDashboard, useLaboratoryWorklist } from "@/features/laboratory/hooks/use-laboratory";
import { LaboratoryWorklistTable } from "@/features/laboratory/components/LaboratoryWorklistTable";

export default function LaboratoryDashboardPage() {
  const { data: dashboard, isLoading: dashboardLoading } = useLaboratoryDashboard();
  const [dateRange, setDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({});
  const { data: orders, isLoading: ordersLoading } = useLaboratoryWorklist(dateRange);
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    if (!orders) return [];
    const query = q.trim().toLowerCase();
    if (!query) return orders;
    return orders.filter(
      (o) =>
        o.orderNumber?.toLowerCase().includes(query) ||
        o.patientName?.toLowerCase().includes(query) ||
        o.testType.toLowerCase().includes(query) ||
        o.doctorName?.toLowerCase().includes(query)
    );
  }, [orders, q]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Laboratory</h1>
        <p className="text-sm text-muted-foreground">Specimen collection, processing, result entry, and release.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Pending" value={dashboardLoading ? null : dashboard?.pending} />
        <StatCard label="Collected" value={dashboardLoading ? null : dashboard?.collected} />
        <StatCard label="Processing" value={dashboardLoading ? null : dashboard?.processing} />
        <StatCard label="Completed Today" value={dashboardLoading ? null : dashboard?.completedToday} />
        <StatCard label="STAT Orders" value={dashboardLoading ? null : dashboard?.statOrders} />
        <StatCard label="Cancelled" value={dashboardLoading ? null : dashboard?.cancelled} />
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Worklist</CardTitle>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder="Search order #, patient, test, doctor..."
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="sm:w-80"
            />
            <RecordDateRangeFilter onApply={setDateRange} />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <LaboratoryWorklistTable orders={filtered} isLoading={ordersLoading} />
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        {value === null || value === undefined ? (
          <Skeleton className="mt-1 h-7 w-16" />
        ) : (
          <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
        )}
      </CardContent>
    </Card>
  );
}
