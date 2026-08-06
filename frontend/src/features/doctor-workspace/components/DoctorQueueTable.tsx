"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Bell, Check, PhoneCall, Play, Lock, X, Ban } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/layout/EmptyState";
import type { DoctorQueueItem } from "@/features/doctor-workspace/types";
import {
  useCallPatient,
  useCancelVisit,
  useCompleteConsultation,
  useMarkNoShow,
  useRecallPatient,
  useStartConsultation,
} from "@/features/doctor-workspace/hooks/use-doctor-actions";

function formatWaiting(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return "<1 min";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "success" | "outline"> = {
  Registered: "outline",
  Waiting: "secondary",
  Called: "default",
  InConsultation: "default",
  Completed: "success",
  Cancelled: "destructive",
  NoShow: "destructive",
};

/** Client Acceptance Revisions - Round 3 (item 1): sortable columns, same
 * client-side-sort-over-fetched-page pattern as
 * `features/queue/components/QueueTable.tsx` (Round 2, item 3). */
type SortKey = "queueNumber" | "patientName" | "status";
type SortDirection = "asc" | "desc";

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "queueNumber", label: "Queue #" },
  { key: "patientName", label: "Patient" },
  { key: "status", label: "Status" },
];

function compareValues(a: DoctorQueueItem, b: DoctorQueueItem, key: SortKey): number {
  const av = (a[key] ?? "").toString().toLowerCase();
  const bv = (b[key] ?? "").toString().toLowerCase();
  return av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
}

export function DoctorQueueTable({ items, readOnly = false }: { items: DoctorQueueItem[]; readOnly?: boolean }) {
  const call = useCallPatient();
  const recall = useRecallPatient();
  const start = useStartConsultation();
  const complete = useCompleteConsultation();
  const noShow = useMarkNoShow();
  const cancel = useCancelVisit();
  const [cancellingId, setCancellingId] = useState<string | null>(null);
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

  if (items.length === 0) {
    return <EmptyState title="No visits today" description="Visits assigned to you will appear here once patients check in." />;
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
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
            <TableHead>Visit #</TableHead>
            <TableHead>Age</TableHead>
            <TableHead>Gender</TableHead>
            <TableHead>Priority</TableHead>
            <TableHead>Arrival</TableHead>
            <TableHead>Waiting</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedItems.map((item) => (
            <TableRow key={item.visitId}>
              <TableCell className="font-mono">{item.queueNumber ?? "—"}</TableCell>
              <TableCell>
                <div className="font-medium text-foreground">{item.patientName}</div>
                <div className="text-xs text-muted-foreground">{item.patientNumber}</div>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <Badge variant={STATUS_VARIANT[item.status] ?? "outline"}>{item.status}</Badge>
                  {item.isLocked ? (
                    <span title={item.lockedByName ? `Locked by ${item.lockedByName}` : "Locked"}>
                      <Lock className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                    </span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs">{item.visitNumber}</TableCell>
              <TableCell>{item.age ?? "—"}</TableCell>
              <TableCell>{item.gender ?? "—"}</TableCell>
              <TableCell>{item.priority}</TableCell>
              <TableCell>{item.arrivalTime ? new Date(item.arrivalTime).toLocaleTimeString() : "—"}</TableCell>
              <TableCell>{item.status === "Waiting" ? formatWaiting(item.waitingSeconds) : "—"}</TableCell>
              <TableCell className="text-right">
                {readOnly ? (
                  <span className="text-xs text-muted-foreground">View only</span>
                ) : (
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {item.status === "Waiting" ? (
                      <Button size="sm" variant="outline" disabled={call.isPending} onClick={() => call.mutate(item.visitId)}>
                        <PhoneCall className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> Call
                      </Button>
                    ) : null}
                    {item.status === "Called" ? (
                      <>
                        <Button size="sm" variant="outline" disabled={recall.isPending} onClick={() => recall.mutate(item.visitId)}>
                          <Bell className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> Recall
                        </Button>
                        <Button size="sm" disabled={start.isPending} onClick={() => start.mutate(item.visitId)}>
                          <Play className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> Start
                        </Button>
                      </>
                    ) : null}
                    {item.status === "InConsultation" ? (
                      <Button size="sm" disabled={complete.isPending} onClick={() => complete.mutate(item.visitId)}>
                        <Check className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> Complete
                      </Button>
                    ) : null}
                    {["Waiting", "Called"].includes(item.status) ? (
                      <Button size="sm" variant="ghost" disabled={noShow.isPending} onClick={() => noShow.mutate(item.visitId)}>
                        <X className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> No-show
                      </Button>
                    ) : null}
                    {["Registered", "Waiting", "Called"].includes(item.status) ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={cancel.isPending && cancellingId === item.visitId}
                        onClick={() => {
                          setCancellingId(item.visitId);
                          cancel.mutate({ visitId: item.visitId, reason: "Cancelled by doctor" });
                        }}
                      >
                        <Ban className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> Cancel
                      </Button>
                    ) : null}
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
