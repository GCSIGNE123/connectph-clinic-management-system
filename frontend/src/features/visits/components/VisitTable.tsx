"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/layout/EmptyState";
import { formatDateTime } from "@/lib/utils";
import { VisitStatusBadge } from "@/features/visits/components/VisitStatusBadge";
import { VISIT_TYPE_LABELS, type VisitListItem } from "@/features/visits/types";

export interface VisitTableProps {
  items: VisitListItem[];
  isLoading: boolean;
}

/** Client Acceptance Revisions - Round 3 (item 1): sortable columns, same
 * client-side-sort-over-fetched-page pattern as
 * `features/queue/components/QueueTable.tsx` (Round 2, item 3). Visits
 * list pagination is server-side (see `app/(dashboard)/visits/page.tsx`),
 * so - consistent with the Queue table's existing limitation - this sorts
 * only the current page, not the full result set. */
type SortKey = "patientName" | "createdAt" | "doctorName" | "status";
type SortDirection = "asc" | "desc";

const SORTABLE_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "patientName", label: "Patient" },
  { key: "createdAt", label: "Date" },
  { key: "doctorName", label: "Doctor" },
  { key: "status", label: "Status" },
];

function compareValues(a: VisitListItem, b: VisitListItem, key: SortKey): number {
  if (key === "createdAt") {
    return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
  }
  const av = (a[key] ?? "").toString().toLowerCase();
  const bv = (b[key] ?? "").toString().toLowerCase();
  return av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
}

export function VisitTable({ items, isLoading }: VisitTableProps) {
  const router = useRouter();
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
    return <EmptyState title="No visits found" description="No visits match the current search or filters." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Visit #</TableHead>
          {SORTABLE_COLUMNS.map((col) => (
            <TableHead key={col.key}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleSort(col.key);
                }}
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
          <TableHead>Queue #</TableHead>
          <TableHead>Department</TableHead>
          <TableHead>Type</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedItems.map((item) => (
          <TableRow
            key={item.id}
            className="cursor-pointer hover:bg-accent/50"
            onClick={() => router.push(`/visits/${item.id}`)}
          >
            <TableCell className="font-mono font-semibold">{item.visitNumber}</TableCell>
            <TableCell>
              <div>{item.patientName ?? "—"}</div>
              <div className="text-xs text-muted-foreground">{item.patientNumber}</div>
            </TableCell>
            <TableCell>{formatDateTime(item.createdAt)}</TableCell>
            <TableCell>{item.doctorName ?? "Unassigned"}</TableCell>
            <TableCell>
              <VisitStatusBadge status={item.status} />
            </TableCell>
            <TableCell className="font-mono">{item.queueNumber ?? "—"}</TableCell>
            <TableCell>{item.departmentName ?? "—"}</TableCell>
            <TableCell>{VISIT_TYPE_LABELS[item.visitType]}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
