"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { useDebouncedValue } from "@/features/patients/hooks/use-patients";
import { useVisits } from "@/features/visits/hooks/use-visits";
import { VisitTable } from "@/features/visits/components/VisitTable";
import { VISIT_STATUS_LABELS, VISIT_TYPE_LABELS, VisitStatus, VisitType } from "@/features/visits/types";

const PAGE_SIZE = 20;

/**
 * Visit List: searchable/filterable/paginated table of all visits
 * (Phase 6). Rows link to the Visit Details page. Visits are created
 * automatically from Queue ticket creation - there is no "New Visit"
 * action here by design (see `services/queue_service.py`).
 */
export default function VisitsPage() {
  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [status, setStatus] = useState<VisitStatus | "">("");
  const [visitType, setVisitType] = useState<VisitType | "">("");
  const [dateRange, setDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({
    dateFrom: new Date().toISOString().slice(0, 10),
    dateTo: new Date().toISOString().slice(0, 10),
  });
  const [page, setPage] = useState(1);

  const params = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      status: status || undefined,
      visitType: visitType || undefined,
      dateFrom: dateRange.dateFrom,
      dateTo: dateRange.dateTo,
      page,
      pageSize: PAGE_SIZE,
    }),
    [debouncedSearch, status, visitType, dateRange, page]
  );

  const { data, isLoading, isFetching } = useVisits(params);
  const items = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Visits</h1>
        <p className="text-sm text-muted-foreground">
          Every patient encounter, created automatically from reception queue tickets.
        </p>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Search visit number, queue number, or patient name/number"
            value={searchInput}
            onChange={(e) => {
              setSearchInput(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <RecordDateRangeFilter
          defaultPreset="today"
          onApply={(range) => {
            setDateRange(range);
            setPage(1);
          }}
        />
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as VisitStatus | "");
            setPage(1);
          }}
          className="sm:w-44"
        >
          <option value="">All statuses</option>
          {Object.values(VisitStatus).map((s) => (
            <option key={s} value={s}>
              {VISIT_STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
        <Select
          value={visitType}
          onChange={(e) => {
            setVisitType(e.target.value as VisitType | "");
            setPage(1);
          }}
          className="sm:w-44"
        >
          <option value="">All visit types</option>
          {Object.values(VisitType).map((t) => (
            <option key={t} value={t}>
              {VISIT_TYPE_LABELS[t]}
            </option>
          ))}
        </Select>
      </div>

      <Card>
        <VisitTable items={items} isLoading={isLoading} />
      </Card>

      {meta && meta.totalPages > 1 ? (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Page {meta.page} of {meta.totalPages} ({meta.total} total)
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page <= 1 || isFetching}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page >= meta.totalPages || isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
