"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { useDebouncedValue, usePatients } from "@/features/patients/hooks/use-patients";
import { patientsApi } from "@/features/patients/api/patients-api";
import { PatientsTable } from "@/features/patients/components/PatientsTable";
import { PatientFormDialog } from "@/features/patients/components/PatientFormDialog";
import { ArchiveRestoreDialog } from "@/features/patients/components/ArchiveRestoreDialog";
import {
  PatientGender,
  PatientStatus,
  type Patient,
  type PatientListItem,
  type PatientSortOption,
} from "@/features/patients/types";
import { Role } from "@/types";

const PAGE_SIZE = 10;

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist, Role.Doctor, Role.Nurse]);
const ARCHIVE_ROLES = new Set<Role>([Role.Owner, Role.Administrator, Role.Receptionist]);

/**
 * Patient directory: server-side search/filter/sort/pagination over
 * `/api/v1/patients`, with add/edit and archive/restore actions.
 */
export default function PatientsPage() {
  const router = useRouter();
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const canArchive = Boolean(currentUser && ARCHIVE_ROLES.has(currentUser.role));

  const [searchInput, setSearchInput] = useState("");
  const debouncedSearch = useDebouncedValue(searchInput, 350);
  const [gender, setGender] = useState<PatientGender | "">("");
  const [status, setStatus] = useState<PatientStatus | "">(PatientStatus.Active);
  const [sort, setSort] = useState<PatientSortOption>("newest");
  const [dateRange, setDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({});
  const [page, setPage] = useState(1);

  const [formOpen, setFormOpen] = useState(false);
  const [editingPatient, setEditingPatient] = useState<Patient | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<{ patient: PatientListItem; action: "archive" | "restore" } | null>(
    null
  );

  const params = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      gender: gender || undefined,
      status: status || undefined,
      sort,
      registeredFrom: dateRange.dateFrom,
      registeredTo: dateRange.dateTo,
      page,
      pageSize: PAGE_SIZE,
    }),
    [debouncedSearch, gender, status, sort, dateRange, page]
  );

  const { data, isLoading, isFetching } = usePatients(params);
  const patients = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Patients</h1>
          <p className="text-sm text-muted-foreground">
            The master patient database for this clinic - search, add, and manage records here.
          </p>
        </div>
        {canManage ? (
          <Button
            type="button"
            onClick={() => {
              setEditingPatient(null);
              setFormOpen(true);
            }}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add patient
          </Button>
        ) : null}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            placeholder="Search by number, name, mobile, or email"
            className="pl-8"
            value={searchInput}
            onChange={(e) => {
              setSearchInput(e.target.value);
              setPage(1);
            }}
            aria-label="Search patients"
          />
        </div>

        <Select
          aria-label="Filter by gender"
          className="w-full sm:w-40"
          value={gender}
          onChange={(e) => {
            setGender(e.target.value as PatientGender | "");
            setPage(1);
          }}
        >
          <option value="">All genders</option>
          {Object.values(PatientGender).map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </Select>

        <Select
          aria-label="Filter by status"
          className="w-full sm:w-40"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as PatientStatus | "");
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          {Object.values(PatientStatus).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>

        <Select
          aria-label="Sort patients"
          className="w-full sm:w-48"
          value={sort}
          onChange={(e) => setSort(e.target.value as PatientSortOption)}
        >
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
          <option value="alphabetical">Alphabetical</option>
          <option value="recently_visited">Recently visited</option>
        </Select>

        <RecordDateRangeFilter
          onApply={(range) => {
            setDateRange(range);
            setPage(1);
          }}
        />
      </div>

      <PatientsTable
        patients={patients}
        isLoading={isLoading}
        canManage={canManage}
        canArchive={canArchive}
        emptyMessage={
          debouncedSearch
            ? `No patients match "${debouncedSearch}".`
            : "No patients have been added to this clinic yet."
        }
        onView={(patient) => router.push(`/patients/${patient.id}`)}
        onEdit={(patient) => {
          patientsApi.get(patient.id).then((full) => {
            setEditingPatient(full);
            setFormOpen(true);
          });
        }}
        onArchive={(patient) => setArchiveTarget({ patient, action: "archive" })}
        onRestore={(patient) => setArchiveTarget({ patient, action: "restore" })}
      />

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

      <PatientFormDialog open={formOpen} onOpenChange={setFormOpen} patient={editingPatient} />

      <ArchiveRestoreDialog
        open={Boolean(archiveTarget)}
        onOpenChange={(open) => {
          if (!open) setArchiveTarget(null);
        }}
        patient={archiveTarget?.patient ?? null}
        action={archiveTarget?.action ?? null}
      />
    </div>
  );
}
