"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { createCrudApi } from "@/features/clinic-config/api/crud-factory";
import { useAppointmentCalendar } from "@/features/appointments/hooks/use-appointments";
import { AppointmentStatusBadge } from "@/features/appointments/components/AppointmentStatusBadge";
import { APPOINTMENT_TYPE_LABELS, AppointmentType, type AppointmentListItem } from "@/features/appointments/types";

interface SimpleOption {
  id: string;
  name: string;
  first_name?: string;
  last_name?: string;
}

const doctorsApi = createCrudApi<SimpleOption>("/doctors");
const departmentsApi = createCrudApi<SimpleOption>("/departments");
const branchesApi = createCrudApi<SimpleOption>("/branches");

type ViewMode = "day" | "week" | "month" | "agenda";

const DAY_LABELS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function toIso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(d: Date, n: number): Date {
  const next = new Date(d);
  next.setDate(next.getDate() + n);
  return next;
}

/** Monday-based start of week, matching the backend's day_of_week convention (0=Monday). */
function startOfWeek(d: Date): Date {
  const day = d.getDay(); // 0=Sunday..6=Saturday
  const diff = day === 0 ? -6 : 1 - day;
  return addDays(d, diff);
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

/**
 * Day/Week/Month/Agenda appointment calendar, built with plain React/CSS
 * grid layouts (no calendar library dependency, consistent with this
 * project's dependency-free UI-primitive convention). Wired to
 * `GET /appointments/calendar` via `useAppointmentCalendar`. Filters by
 * Doctor/Department/Branch/Appointment Type per the spec.
 */
export function AppointmentCalendar() {
  const [viewMode, setViewMode] = useState<ViewMode>("month");
  const [anchorDate, setAnchorDate] = useState(new Date());
  const [doctorId, setDoctorId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [appointmentType, setAppointmentType] = useState<AppointmentType | "">("");
  const [selectedItem, setSelectedItem] = useState<AppointmentListItem | null>(null);

  const doctors = useQuery({ queryKey: ["appointment-calendar", "doctors"], queryFn: () => doctorsApi.list({ status: "Active", limit: 100 }) });
  const departments = useQuery({ queryKey: ["appointment-calendar", "departments"], queryFn: () => departmentsApi.list({ status: "Active", limit: 100 }) });
  const branches = useQuery({ queryKey: ["appointment-calendar", "branches"], queryFn: () => branchesApi.list({ limit: 100 }) });

  const { rangeStart, rangeEnd } = useMemo(() => {
    if (viewMode === "day") return { rangeStart: anchorDate, rangeEnd: anchorDate };
    if (viewMode === "week") {
      const start = startOfWeek(anchorDate);
      return { rangeStart: start, rangeEnd: addDays(start, 6) };
    }
    if (viewMode === "agenda") return { rangeStart: anchorDate, rangeEnd: addDays(anchorDate, 13) };
    // month: pad to full weeks so the grid is rectangular
    const monthStart = startOfMonth(anchorDate);
    const monthEnd = endOfMonth(anchorDate);
    return { rangeStart: startOfWeek(monthStart), rangeEnd: addDays(startOfWeek(addDays(monthEnd, 6)), 6) };
  }, [viewMode, anchorDate]);

  const { data: items, isLoading } = useAppointmentCalendar({
    dateFrom: toIso(rangeStart),
    dateTo: toIso(rangeEnd),
    doctorId: doctorId || undefined,
    departmentId: departmentId || undefined,
    branchId: branchId || undefined,
    appointmentType: (appointmentType || undefined) as AppointmentType | undefined,
  });

  const byDate = useMemo(() => {
    const map = new Map<string, AppointmentListItem[]>();
    for (const item of items ?? []) {
      const list = map.get(item.appointmentDate) ?? [];
      list.push(item);
      map.set(item.appointmentDate, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.startTime.localeCompare(b.startTime));
    return map;
  }, [items]);

  function navigate(direction: 1 | -1) {
    if (viewMode === "day") setAnchorDate((d) => addDays(d, direction));
    else if (viewMode === "week") setAnchorDate((d) => addDays(d, 7 * direction));
    else if (viewMode === "agenda") setAnchorDate((d) => addDays(d, 14 * direction));
    else setAnchorDate((d) => new Date(d.getFullYear(), d.getMonth() + direction, 1));
  }

  const rangeLabel =
    viewMode === "day"
      ? anchorDate.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" })
      : viewMode === "month"
      ? anchorDate.toLocaleDateString(undefined, { month: "long", year: "numeric" })
      : `${rangeStart.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${rangeEnd.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;

  return (
    <div className="space-y-4">
      <Card className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setAnchorDate(new Date())}>
              Today
            </Button>
            <Button variant="outline" size="sm" onClick={() => navigate(1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <span className="ml-2 text-sm font-medium">{rangeLabel}</span>
          </div>
          <div className="flex gap-1 rounded-md border border-border p-1">
            {(["day", "week", "month", "agenda"] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`rounded px-3 py-1 text-xs capitalize ${
                  viewMode === mode ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <Select value={doctorId} onChange={(e) => setDoctorId(e.target.value)} className="w-48">
            <option value="">All doctors</option>
            {(doctors.data?.items ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                Dr. {d.first_name} {d.last_name}
              </option>
            ))}
          </Select>
          <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} className="w-48">
            <option value="">All departments</option>
            {(departments.data?.items ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </Select>
          <Select value={branchId} onChange={(e) => setBranchId(e.target.value)} className="w-48">
            <option value="">All branches</option>
            {(branches.data?.items ?? []).map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </Select>
          <Select value={appointmentType} onChange={(e) => setAppointmentType(e.target.value as AppointmentType | "")} className="w-48">
            <option value="">All types</option>
            {Object.values(AppointmentType).map((t) => (
              <option key={t} value={t}>{APPOINTMENT_TYPE_LABELS[t]}</option>
            ))}
          </Select>
        </div>
      </Card>

      {isLoading ? (
        <Card className="p-6 text-sm text-muted-foreground">Loading calendar...</Card>
      ) : viewMode === "month" ? (
        <MonthGrid rangeStart={rangeStart} anchorDate={anchorDate} byDate={byDate} onSelect={setSelectedItem} />
      ) : viewMode === "week" ? (
        <WeekGrid rangeStart={rangeStart} byDate={byDate} onSelect={setSelectedItem} />
      ) : viewMode === "day" ? (
        <DayList date={anchorDate} byDate={byDate} onSelect={setSelectedItem} />
      ) : (
        <AgendaList rangeStart={rangeStart} rangeEnd={rangeEnd} byDate={byDate} onSelect={setSelectedItem} />
      )}

      {selectedItem ? (
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-mono text-sm font-semibold">{selectedItem.appointmentNumber}</p>
              <p className="text-sm text-muted-foreground">
                {selectedItem.patientName} — Dr. {selectedItem.doctorName} — {selectedItem.appointmentDate} {selectedItem.startTime.slice(0, 5)}
              </p>
            </div>
            <AppointmentStatusBadge status={selectedItem.status} />
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function AppointmentChip({ item, onSelect }: { item: AppointmentListItem; onSelect: (item: AppointmentListItem) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      className="block w-full truncate rounded bg-primary/10 px-1.5 py-0.5 text-left text-[11px] text-primary hover:bg-primary/20"
      title={`${item.startTime.slice(0, 5)} ${item.patientName ?? ""}`}
    >
      {item.startTime.slice(0, 5)} {item.patientName ?? "Unknown"}
    </button>
  );
}

function MonthGrid({
  rangeStart, anchorDate, byDate, onSelect,
}: {
  rangeStart: Date; anchorDate: Date; byDate: Map<string, AppointmentListItem[]>; onSelect: (item: AppointmentListItem) => void;
}) {
  const weeks: Date[][] = [];
  let cursor = rangeStart;
  for (let w = 0; w < 6; w++) {
    const week: Date[] = [];
    for (let d = 0; d < 7; d++) {
      week.push(cursor);
      cursor = addDays(cursor, 1);
    }
    weeks.push(week);
    if (cursor.getMonth() !== anchorDate.getMonth() && w >= 3) break;
  }

  return (
    <Card className="overflow-hidden p-0">
      <div className="grid grid-cols-7 border-b border-border bg-muted/40 text-xs font-medium">
        {DAY_LABELS_SHORT.map((label) => (
          <div key={label} className="px-2 py-2 text-center">{label}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {weeks.flat().map((date) => {
          const iso = toIso(date);
          const dayItems = byDate.get(iso) ?? [];
          const inMonth = date.getMonth() === anchorDate.getMonth();
          return (
            <div key={iso} className={`min-h-24 border-b border-r border-border p-1 ${inMonth ? "" : "bg-muted/20 text-muted-foreground"}`}>
              <div className="text-xs font-medium">{date.getDate()}</div>
              <div className="mt-1 space-y-0.5">
                {dayItems.slice(0, 3).map((item) => (
                  <AppointmentChip key={item.id} item={item} onSelect={onSelect} />
                ))}
                {dayItems.length > 3 ? <div className="text-[11px] text-muted-foreground">+{dayItems.length - 3} more</div> : null}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function WeekGrid({
  rangeStart, byDate, onSelect,
}: {
  rangeStart: Date; byDate: Map<string, AppointmentListItem[]>; onSelect: (item: AppointmentListItem) => void;
}) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(rangeStart, i));
  return (
    <Card className="overflow-hidden p-0">
      <div className="grid grid-cols-7">
        {days.map((date) => {
          const iso = toIso(date);
          const dayItems = byDate.get(iso) ?? [];
          return (
            <div key={iso} className="min-h-40 border-r border-border p-2 last:border-r-0">
              <div className="mb-1 text-xs font-medium">
                {date.toLocaleDateString(undefined, { weekday: "short" })} {date.getDate()}
              </div>
              <div className="space-y-1">
                {dayItems.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground">—</p>
                ) : (
                  dayItems.map((item) => <AppointmentChip key={item.id} item={item} onSelect={onSelect} />)
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function DayList({
  date, byDate, onSelect,
}: {
  date: Date; byDate: Map<string, AppointmentListItem[]>; onSelect: (item: AppointmentListItem) => void;
}) {
  const dayItems = byDate.get(toIso(date)) ?? [];
  return (
    <Card className="p-4">
      {dayItems.length === 0 ? (
        <p className="text-sm text-muted-foreground">No appointments on this day.</p>
      ) : (
        <ul className="divide-y divide-border">
          {dayItems.map((item) => (
            <li key={item.id} className="flex items-center justify-between py-2">
              <button type="button" className="text-left text-sm hover:underline" onClick={() => onSelect(item)}>
                <span className="font-mono">{item.startTime.slice(0, 5)}</span> — {item.patientName} with Dr. {item.doctorName}
              </button>
              <AppointmentStatusBadge status={item.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AgendaList({
  rangeStart, rangeEnd, byDate, onSelect,
}: {
  rangeStart: Date; rangeEnd: Date; byDate: Map<string, AppointmentListItem[]>; onSelect: (item: AppointmentListItem) => void;
}) {
  const days: Date[] = [];
  let cursor = rangeStart;
  while (cursor <= rangeEnd) {
    days.push(cursor);
    cursor = addDays(cursor, 1);
  }
  const nonEmptyDays = days.filter((d) => (byDate.get(toIso(d))?.length ?? 0) > 0);

  return (
    <Card className="p-4">
      {nonEmptyDays.length === 0 ? (
        <p className="text-sm text-muted-foreground">No appointments in this range.</p>
      ) : (
        <div className="space-y-4">
          {nonEmptyDays.map((date) => {
            const iso = toIso(date);
            const dayItems = byDate.get(iso) ?? [];
            return (
              <div key={iso}>
                <h3 className="mb-1 text-sm font-semibold">{date.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}</h3>
                <ul className="divide-y divide-border">
                  {dayItems.map((item) => (
                    <li key={item.id} className="flex items-center justify-between py-1.5">
                      <button type="button" className="text-left text-sm hover:underline" onClick={() => onSelect(item)}>
                        <span className="font-mono">{item.startTime.slice(0, 5)}</span> — {item.patientName} with Dr. {item.doctorName}
                      </button>
                      <AppointmentStatusBadge status={item.status} />
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
