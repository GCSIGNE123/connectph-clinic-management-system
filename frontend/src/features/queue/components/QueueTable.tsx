"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { QueueStatusBadge } from "@/features/queue/components/QueueStatusBadge";
import { QUEUE_PRIORITY_LABELS, QueueStatus, VISIT_CLASSIFICATION_LABELS, VisitClassification, type QueueListItem } from "@/features/queue/types";

export interface QueueTableProps {
  items: QueueListItem[];
  isLoading: boolean;
  onView: (item: QueueListItem) => void;
  onCancel: (item: QueueListItem) => void;
  onReprint: (item: QueueListItem) => void;
  canManage: boolean;
  /** Phase 20 (items 3-5): show an "Enter Vitals" action (Receptionist/
   * Nurse only) that opens `ReceptionVitalsDialog` for the ticket's visit. */
  onEnterVitals?: (item: QueueListItem) => void;
  /** Phase 2.7 (YAKAP Patient Classification / Receptionist Queue Control):
   * row-level Call/Re-announce actions - only rendered when the current
   * user is in `QUEUE_TRANSITION_ROLES`. Reuses the exact same
   * status-transition/reannounce mutations already wired on the Queue
   * Details dialog - no parallel calling mechanism. */
  canTransition?: boolean;
  onCall?: (item: QueueListItem) => void;
  onReannounce?: (item: QueueListItem) => void;
}

const CLASSIFICATION_BADGE_CLASS: Record<VisitClassification, string> = {
  [VisitClassification.Yakap]: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  [VisitClassification.Regular]: "bg-muted text-muted-foreground",
};

function ClassificationBadge({ value }: { value: VisitClassification }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${CLASSIFICATION_BADGE_CLASS[value]}`}>
      {VISIT_CLASSIFICATION_LABELS[value]}
    </span>
  );
}

/** Client Acceptance Revisions - Round 2 (MEDIUM item 3): sortable columns.
 * Client-side sort over the already-fetched page of results - no new API
 * params, since the list is already small/paginated per day. */
type SortKey = "queueNumber" | "patientName" | "departmentName" | "createdAt";
type SortDirection = "asc" | "desc";

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "queueNumber", label: "Queue #" },
  { key: "patientName", label: "Patient" },
  { key: "departmentName", label: "Department" },
  { key: "createdAt", label: "Created" },
];

function compareValues(a: QueueListItem, b: QueueListItem, key: SortKey): number {
  if (key === "createdAt") {
    return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
  }
  const av = (a[key] ?? "").toString().toLowerCase();
  const bv = (b[key] ?? "").toString().toLowerCase();
  return av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
}

export function QueueTable({
  items,
  isLoading,
  onView,
  onCancel,
  onReprint,
  canManage,
  onEnterVitals,
  canTransition,
  onCall,
  onReannounce,
}: QueueTableProps) {
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
    return <EmptyState title="No queue tickets" description="No tickets match the current filters for today." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
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
          <TableHead>Doctor</TableHead>
          <TableHead>Service</TableHead>
          <TableHead>Priority</TableHead>
          <TableHead>Classification</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedItems.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="font-mono font-semibold">{item.queueNumber}</TableCell>
            <TableCell>
              <div>{item.patientName ?? "—"}</div>
              <div className="text-xs text-muted-foreground">{item.patientNumber}</div>
            </TableCell>
            <TableCell>{item.departmentName ?? "—"}</TableCell>
            <TableCell>{new Date(item.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</TableCell>
            <TableCell>{item.doctorName ?? "Unassigned"}</TableCell>
            <TableCell>{item.serviceName ?? "—"}</TableCell>
            <TableCell>{QUEUE_PRIORITY_LABELS[item.priority]}</TableCell>
            <TableCell>
              <ClassificationBadge value={item.visitClassification} />
            </TableCell>
            <TableCell>
              <QueueStatusBadge status={item.status} />
            </TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                <Button size="sm" variant="outline" onClick={() => onView(item)}>
                  View
                </Button>
                <Button size="sm" variant="outline" onClick={() => onReprint(item)}>
                  Print
                </Button>
                {/* Phase 2.7 (Receptionist Queue Control): the receptionist
                    explicitly picks which Waiting ticket to call next - no
                    automatic YAKAP-first ordering, this button is available
                    on every Waiting row equally, in the order the table
                    already renders them. */}
                {canTransition && onCall && item.status === QueueStatus.Waiting ? (
                  <Button size="sm" onClick={() => onCall(item)}>
                    Call
                  </Button>
                ) : null}
                {canTransition && onReannounce && item.status === QueueStatus.Called ? (
                  <Button size="sm" variant="outline" onClick={() => onReannounce(item)}>
                    Re-announce
                  </Button>
                ) : null}
                {onEnterVitals && item.visitId && !["Completed", "Cancelled"].includes(item.status) ? (
                  <Button size="sm" variant="outline" onClick={() => onEnterVitals(item)}>
                    Enter Vitals
                  </Button>
                ) : null}
                {canManage && !["Completed", "Cancelled"].includes(item.status) ? (
                  <Button size="sm" variant="destructive" onClick={() => onCancel(item)}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
