"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { AppointmentStatusBadge } from "@/features/appointments/components/AppointmentStatusBadge";
import { APPOINTMENT_TYPE_LABELS, AppointmentStatus, type AppointmentListItem } from "@/features/appointments/types";

/** Client Acceptance Revisions - Round 3 (item 1): sortable columns, same
 * client-side-sort-over-fetched-page pattern as
 * `features/queue/components/QueueTable.tsx` (Round 2, item 3).
 * `AppointmentListItem` (the list-view shape) has no `createdAt` - that
 * only exists on `AppointmentDetail` - so "Created Date" from the task
 * isn't sortable here without a backend/list-schema change; sorting is
 * implemented for Patient Name, Appointment Time (date+start time),
 * Doctor, and Status, which covers what the list actually has. */
type SortKey = "patientName" | "appointmentTime" | "doctorName" | "status";
type SortDirection = "asc" | "desc";

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "patientName", label: "Patient" },
  { key: "doctorName", label: "Doctor" },
  { key: "appointmentTime", label: "Date / Time" },
  { key: "status", label: "Status" },
];

function compareValues(a: AppointmentListItem, b: AppointmentListItem, key: SortKey): number {
  if (key === "appointmentTime") {
    const av = `${a.appointmentDate}T${a.startTime}`;
    const bv = `${b.appointmentDate}T${b.startTime}`;
    return av.localeCompare(bv);
  }
  const av = (a[key] ?? "").toString().toLowerCase();
  const bv = (b[key] ?? "").toString().toLowerCase();
  return av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
}

export interface AppointmentTableProps {
  items: AppointmentListItem[];
  isLoading: boolean;
  onView: (item: AppointmentListItem) => void;
  onConfirm: (item: AppointmentListItem) => void;
  onCheckIn: (item: AppointmentListItem) => void;
  onCancel: (item: AppointmentListItem) => void;
  onComplete: (item: AppointmentListItem) => void;
  onNoShow: (item: AppointmentListItem) => void;
  canManage: boolean;
  canComplete: boolean;
}

const TERMINAL_STATUSES = [AppointmentStatus.Completed, AppointmentStatus.Cancelled, AppointmentStatus.NoShow, AppointmentStatus.Rescheduled];

export function AppointmentTable({
  items, isLoading, onView, onConfirm, onCheckIn, onCancel, onComplete, onNoShow, canManage, canComplete,
}: AppointmentTableProps) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const sortedItems = useMemo(() => {
    if (!sortKey) return items;
    const sorted = [...items].sort((a, b) => compareValues(a, b, sortKey));
    return sortDirection === "asc" ? sorted : sorted.reverse();
  }, [items, sortKey, sortDirection]);

  function toggleSort(key: SortKey) {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDirection("asc");
      return;
    }
    setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
  }

  if (isLoading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return <EmptyState title="No appointments" description="No appointments match the current filters." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Appointment #</TableHead>
          {SORTABLE_COLUMNS.map((col) => (
            <TableHead key={col.key}>
              <button
                type="button"
                onClick={() => toggleSort(col.key)}
                className="flex items-center gap-1 font-medium hover:text-foreground"
                aria-label={`Sort by ${col.label}`}
              >
                {col.label}
                {sortKey === col.key ? (
                  sortDirection === "asc" ? (
                    <ArrowUp className="h-3.5 w-3.5" />
                  ) : (
                    <ArrowDown className="h-3.5 w-3.5" />
                  )
                ) : (
                  <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground/50" />
                )}
              </button>
            </TableHead>
          ))}
          <TableHead>Department</TableHead>
          <TableHead>Type</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedItems.map((item) => {
          const isTerminal = TERMINAL_STATUSES.includes(item.status);
          return (
            <TableRow key={item.id}>
              <TableCell className="font-mono font-semibold">{item.appointmentNumber}</TableCell>
              <TableCell>
                <div>{item.patientName ?? "—"}</div>
                <div className="text-xs text-muted-foreground">{item.patientNumber}</div>
              </TableCell>
              <TableCell>{item.doctorName ?? "—"}</TableCell>
              <TableCell>
                {item.appointmentDate} {item.startTime.slice(0, 5)}
              </TableCell>
              <TableCell>
                <AppointmentStatusBadge status={item.status} />
              </TableCell>
              <TableCell>{item.departmentName ?? "—"}</TableCell>
              <TableCell>{APPOINTMENT_TYPE_LABELS[item.appointmentType]}</TableCell>
              <TableCell className="text-right">
                <div className="flex flex-wrap justify-end gap-1">
                  <Button size="sm" variant="outline" onClick={() => onView(item)}>
                    View
                  </Button>
                  {canManage && item.status === AppointmentStatus.Booked ? (
                    <Button size="sm" variant="outline" onClick={() => onConfirm(item)}>
                      Confirm
                    </Button>
                  ) : null}
                  {canManage && (item.status === AppointmentStatus.Booked || item.status === AppointmentStatus.Confirmed) ? (
                    <Button size="sm" onClick={() => onCheckIn(item)}>
                      Check In
                    </Button>
                  ) : null}
                  {canComplete && (item.status === AppointmentStatus.CheckedIn || item.status === AppointmentStatus.Waiting) ? (
                    <Button size="sm" variant="outline" onClick={() => onComplete(item)}>
                      Complete
                    </Button>
                  ) : null}
                  {canManage && !isTerminal ? (
                    <Button size="sm" variant="outline" onClick={() => onNoShow(item)}>
                      No-Show
                    </Button>
                  ) : null}
                  {canManage && !isTerminal ? (
                    <Button size="sm" variant="destructive" onClick={() => onCancel(item)}>
                      Cancel
                    </Button>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
