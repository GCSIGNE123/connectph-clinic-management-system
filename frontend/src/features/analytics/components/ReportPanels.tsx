"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { BarChart } from "@/features/analytics/components/BarChart";
import { LineChart } from "@/features/analytics/components/LineChart";
import { DateRangeFilter } from "@/features/analytics/components/DateRangeFilter";
import { ExportButtons } from "@/features/analytics/components/ExportButtons";
import { ReportSection } from "@/features/analytics/components/ReportSection";
import {
  useAppointmentReport,
  useDoctorReport,
  useLaboratoryReport,
  usePatientReport,
  useQueueReport,
  useRevenueReport,
} from "@/features/analytics/hooks/use-analytics";
import { formatCurrency, formatDuration, formatNumber, formatPercent } from "@/features/analytics/lib/format";
import { isValidCustomRange } from "@/features/analytics/lib/date-range";
import type { DateRangePreset, ReportFilters } from "@/features/analytics/types";

function useReportFilters(): [ReportFilters, (next: { preset: DateRangePreset; start?: string; end?: string }) => void] {
  const [preset, setPreset] = useState<DateRangePreset>("today");
  const [start, setStart] = useState<string | undefined>();
  const [end, setEnd] = useState<string | undefined>();

  const filters: ReportFilters = { dateRange: preset, start, end };
  const onChange = (next: { preset: DateRangePreset; start?: string; end?: string }) => {
    setPreset(next.preset);
    setStart(next.start);
    setEnd(next.end);
  };
  return [filters, onChange];
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

export function PatientReportPanel() {
  const [filters, onChange] = useReportFilters();
  const validRange = isValidCustomRange(filters.dateRange, filters.start, filters.end);
  const { data, isLoading } = usePatientReport(filters);

  return (
    <ReportSection
      title="Patient Report"
      isLoading={isLoading || !validRange}
      filters={<DateRangeFilter preset={filters.dateRange} start={filters.start} end={filters.end} onChange={onChange} />}
      actions={<ExportButtons report="patients" filters={filters} />}
    >
      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MiniStat label="New Patients" value={formatNumber(data.newPatients)} />
            <MiniStat label="Returning Patients" value={formatNumber(data.returningPatients)} />
            <MiniStat label="Total Visits" value={formatNumber(data.totalVisits)} />
            <MiniStat label="Gender Groups" value={formatNumber(data.genderDistribution.length)} />
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Daily Patient Census</p>
            <LineChart data={data.dailyCensus} formatValue={formatNumber} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium">Age Distribution</p>
              <BarChart data={data.ageDistribution} formatValue={formatNumber} />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Gender Distribution</p>
              <BarChart data={data.genderDistribution} formatValue={formatNumber} />
            </div>
          </div>
        </div>
      ) : null}
    </ReportSection>
  );
}

export function DoctorReportPanel() {
  const [filters, onChange] = useReportFilters();
  const { data, isLoading } = useDoctorReport(filters);

  return (
    <ReportSection
      title="Doctor Report"
      isLoading={isLoading}
      filters={<DateRangeFilter preset={filters.dateRange} start={filters.start} end={filters.end} onChange={onChange} />}
      actions={<ExportButtons report="doctors" filters={filters} />}
    >
      {data ? (
        <div className="space-y-3">
          <div>
            <p className="mb-2 text-sm font-medium">Doctor Workload (Patients Seen)</p>
            <BarChart data={data.doctors.map((d) => ({ label: d.doctorName, value: d.patientsSeen }))} formatValue={formatNumber} />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3">Doctor</th>
                  <th className="py-2 pr-3">Patients Seen</th>
                  <th className="py-2 pr-3">Completed</th>
                  <th className="py-2 pr-3">Cancelled</th>
                  <th className="py-2 pr-3">Avg. Consultation</th>
                  <th className="py-2 pr-3">Revenue</th>
                  <th className="py-2 pr-3">Utilization</th>
                </tr>
              </thead>
              <tbody>
                {data.doctors.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-4 text-center text-muted-foreground">No data for this period</td>
                  </tr>
                ) : (
                  data.doctors.map((row) => (
                    <tr key={row.doctorId} className="border-b border-border/50 last:border-0">
                      <td className="py-2 pr-3">{row.doctorName}</td>
                      <td className="py-2 pr-3">{formatNumber(row.patientsSeen)}</td>
                      <td className="py-2 pr-3">{formatNumber(row.completedVisits)}</td>
                      <td className="py-2 pr-3">{formatNumber(row.cancelledVisits)}</td>
                      <td className="py-2 pr-3">{formatDuration(row.avgConsultationSeconds)}</td>
                      <td className="py-2 pr-3">{formatCurrency(row.revenueGenerated)}</td>
                      <td className="py-2 pr-3">{formatPercent(row.appointmentUtilization)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </ReportSection>
  );
}

export function RevenueReportPanel() {
  const [filters, onChange] = useReportFilters();
  const { data, isLoading } = useRevenueReport(filters);

  return (
    <ReportSection
      title="Revenue Report"
      isLoading={isLoading}
      filters={<DateRangeFilter preset={filters.dateRange} start={filters.start} end={filters.end} onChange={onChange} />}
      actions={<ExportButtons report="revenue" filters={filters} />}
    >
      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MiniStat label="Total Revenue" value={formatCurrency(data.totalRevenue)} />
            <MiniStat label="Outstanding Invoices" value={`${formatNumber(data.outstandingInvoicesCount)} (${formatCurrency(data.outstandingInvoicesAmount)})`} />
            <MiniStat label="Discounts Given" value={formatCurrency(data.discountSummary.reduce((sum, s) => sum + s.value, 0))} />
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Daily Revenue Trend</p>
            <LineChart data={data.dailyRevenue} formatValue={formatCurrency} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium">Revenue by Doctor</p>
              <BarChart data={data.revenueByDoctor} formatValue={formatCurrency} />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Revenue by Branch</p>
              <BarChart data={data.revenueByBranch} formatValue={formatCurrency} />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Revenue by Service</p>
              <BarChart data={data.revenueByService} formatValue={formatCurrency} />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Revenue by Payment Method</p>
              <BarChart data={data.revenueByPaymentMethod} formatValue={formatCurrency} />
            </div>
          </div>
        </div>
      ) : null}
    </ReportSection>
  );
}

export function QueueReportPanel() {
  const [filters, onChange] = useReportFilters();
  const { data, isLoading } = useQueueReport(filters);

  return (
    <ReportSection
      title="Queue Report"
      isLoading={isLoading}
      filters={<DateRangeFilter preset={filters.dateRange} start={filters.start} end={filters.end} onChange={onChange} />}
      actions={<ExportButtons report="queue" filters={filters} />}
    >
      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MiniStat label="Avg. Waiting Time" value={formatDuration(data.avgWaitingSeconds)} />
            <MiniStat label="Longest Wait" value={formatDuration(data.longestWaitSeconds)} />
            <MiniStat label="Completed" value={formatNumber(data.completedCount)} />
            <MiniStat label="Cancelled" value={formatNumber(data.cancelledCount)} />
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Queue Volume by Hour</p>
            <BarChart data={data.volumeByHour} formatValue={formatNumber} />
          </div>
        </div>
      ) : null}
    </ReportSection>
  );
}

export function LaboratoryReportPanel() {
  const [filters, onChange] = useReportFilters();
  const { data, isLoading } = useLaboratoryReport(filters);

  return (
    <ReportSection
      title="Laboratory Report"
      isLoading={isLoading}
      filters={<DateRangeFilter preset={filters.dateRange} start={filters.start} end={filters.end} onChange={onChange} />}
      actions={<ExportButtons report="laboratory" filters={filters} />}
    >
      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MiniStat label="Orders" value={formatNumber(data.ordersToday)} />
            <MiniStat label="Completed" value={formatNumber(data.completed)} />
            <MiniStat label="Pending" value={formatNumber(data.pending)} />
            <MiniStat label="Avg. Turnaround" value={formatDuration(data.avgTurnaroundSeconds)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium">Laboratory Trend</p>
              <LineChart data={data.dailyVolume} formatValue={formatNumber} />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Top Requested Tests</p>
              <BarChart data={data.topRequestedTests} formatValue={formatNumber} />
            </div>
          </div>
        </div>
      ) : null}
    </ReportSection>
  );
}

export function AppointmentReportPanel() {
  const [filters, onChange] = useReportFilters();
  const { data, isLoading } = useAppointmentReport(filters);

  return (
    <ReportSection
      title="Appointment Report"
      isLoading={isLoading}
      filters={<DateRangeFilter preset={filters.dateRange} start={filters.start} end={filters.end} onChange={onChange} />}
      actions={<ExportButtons report="appointments" filters={filters} />}
    >
      {data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <MiniStat label="Bookings" value={formatNumber(data.bookings)} />
            <MiniStat label="Completed" value={formatNumber(data.completed)} />
            <MiniStat label="Cancelled" value={formatNumber(data.cancelled)} />
            <MiniStat label="No Shows" value={formatNumber(data.noShows)} />
            <MiniStat label="Rescheduled" value={formatNumber(data.rescheduled)} />
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Appointment Trend</p>
            <LineChart data={data.dailyBookings} formatValue={formatNumber} />
          </div>
          {data.doctorUtilization.length > 0 ? (
            <Card>
              <CardContent className="overflow-x-auto p-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-2 pr-3">Doctor</th>
                      <th className="py-2 pr-3">Booked</th>
                      <th className="py-2 pr-3">Completed</th>
                      <th className="py-2 pr-3">Utilization</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.doctorUtilization.map((row) => (
                      <tr key={row.doctor_id} className="border-b border-border/50 last:border-0">
                        <td className="py-2 pr-3">{row.doctor_name}</td>
                        <td className="py-2 pr-3">{formatNumber(row.booked)}</td>
                        <td className="py-2 pr-3">{formatNumber(row.completed)}</td>
                        <td className="py-2 pr-3">{formatPercent(row.utilization)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </ReportSection>
  );
}
