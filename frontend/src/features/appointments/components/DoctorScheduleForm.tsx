"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { appointmentsApi } from "@/features/appointments/api/appointments-api";
import { useDoctorSchedule } from "@/features/appointments/hooks/use-appointments";
import { useQueryClient } from "@tanstack/react-query";
import { appointmentKeys } from "@/features/appointments/hooks/use-appointments";
import { formatDate } from "@/lib/utils";

const DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface DayFormState {
  dayOfWeek: number;
  enabled: boolean;
  startTime: string;
  endTime: string;
  lunchBreakStart: string;
  lunchBreakEnd: string;
  slotDurationMinutes: number;
  maxPatientsPerDay: string;
}

function defaultDay(dayOfWeek: number): DayFormState {
  return {
    dayOfWeek,
    enabled: false,
    startTime: "08:00",
    endTime: "17:00",
    lunchBreakStart: "12:00",
    lunchBreakEnd: "13:00",
    slotDurationMinutes: 30,
    maxPatientsPerDay: "",
  };
}

/**
 * Doctor working-hours schedule editor (working days/hours/lunch/slot
 * duration/max-per-day) plus vacation/blocked-dates list+add. Wired to the
 * existing `GET/PUT /doctors/{id}/schedule` and
 * `POST /doctors/{id}/schedule/blocks` endpoints from Phase 11's backend
 * (built and API-verified before this UI was added). Editing and saving
 * invalidates `appointmentKeys.schedule`/`slots` so the New Appointment
 * dialog's Time Slot Engine picker reflects changes immediately.
 */
export function DoctorScheduleForm({ doctorId }: { doctorId: string }) {
  const { data, isLoading } = useDoctorSchedule(doctorId);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [days, setDays] = useState<DayFormState[]>(() => Array.from({ length: 7 }, (_, i) => defaultDay(i)));
  const [saving, setSaving] = useState(false);

  const [blockDate, setBlockDate] = useState("");
  const [blockType, setBlockType] = useState<"Vacation" | "Blocked">("Blocked");
  const [blockReason, setBlockReason] = useState("");
  const [blockSaving, setBlockSaving] = useState(false);

  useEffect(() => {
    if (!data) return;
    const next = Array.from({ length: 7 }, (_, i) => defaultDay(i));
    for (const d of data.days) {
      next[d.dayOfWeek] = {
        dayOfWeek: d.dayOfWeek,
        enabled: d.isActive,
        startTime: d.startTime.slice(0, 5),
        endTime: d.endTime.slice(0, 5),
        lunchBreakStart: d.lunchBreakStart?.slice(0, 5) ?? "",
        lunchBreakEnd: d.lunchBreakEnd?.slice(0, 5) ?? "",
        slotDurationMinutes: d.slotDurationMinutes,
        maxPatientsPerDay: d.maxPatientsPerDay?.toString() ?? "",
      };
    }
    setDays(next);
  }, [data]);

  function updateDay(index: number, patch: Partial<DayFormState>) {
    setDays((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  }

  async function onSave() {
    setSaving(true);
    try {
      await appointmentsApi.setSchedule(
        doctorId,
        days
          .filter((d) => d.enabled)
          .map((d) => ({
            dayOfWeek: d.dayOfWeek,
            startTime: `${d.startTime}:00`,
            endTime: `${d.endTime}:00`,
            lunchBreakStart: d.lunchBreakStart ? `${d.lunchBreakStart}:00` : null,
            lunchBreakEnd: d.lunchBreakEnd ? `${d.lunchBreakEnd}:00` : null,
            slotDurationMinutes: d.slotDurationMinutes,
            maxPatientsPerDay: d.maxPatientsPerDay ? Number(d.maxPatientsPerDay) : null,
            isActive: true,
          }))
      );
      queryClient.invalidateQueries({ queryKey: appointmentKeys.schedule(doctorId) });
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      toast({ title: "Schedule saved", variant: "success" });
    } catch (error) {
      toast({
        title: "Could not save schedule",
        description: error instanceof ApiError ? error.message : "Please try again.",
        variant: "error",
      });
    } finally {
      setSaving(false);
    }
  }

  async function onAddBlock() {
    if (!blockDate) return;
    setBlockSaving(true);
    try {
      await appointmentsApi.addScheduleBlock(doctorId, blockDate, blockType, blockReason || undefined);
      queryClient.invalidateQueries({ queryKey: appointmentKeys.schedule(doctorId) });
      queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      setBlockDate("");
      setBlockReason("");
      toast({ title: "Block added", variant: "success" });
    } catch (error) {
      toast({
        title: "Could not add block",
        description: error instanceof ApiError ? error.message : "Please try again.",
        variant: "error",
      });
    } finally {
      setBlockSaving(false);
    }
  }

  async function onRemoveBlock(blockId: string) {
    await appointmentsApi.removeScheduleBlock(doctorId, blockId);
    queryClient.invalidateQueries({ queryKey: appointmentKeys.schedule(doctorId) });
    queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    toast({ title: "Block removed", variant: "success" });
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Working Hours</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {days.map((d, i) => (
            <div key={d.dayOfWeek} className="grid grid-cols-2 items-center gap-3 border-b border-border pb-3 last:border-0 sm:grid-cols-7">
              <label className="flex items-center gap-2 text-sm font-medium sm:col-span-1">
                <input type="checkbox" checked={d.enabled} onChange={(e) => updateDay(i, { enabled: e.target.checked })} />
                {DAY_LABELS[d.dayOfWeek]}
              </label>
              <div className="space-y-1 sm:col-span-1">
                <Label className="text-xs">Start</Label>
                <Input type="time" value={d.startTime} onChange={(e) => updateDay(i, { startTime: e.target.value })} disabled={!d.enabled} />
              </div>
              <div className="space-y-1 sm:col-span-1">
                <Label className="text-xs">End</Label>
                <Input type="time" value={d.endTime} onChange={(e) => updateDay(i, { endTime: e.target.value })} disabled={!d.enabled} />
              </div>
              <div className="space-y-1 sm:col-span-1">
                <Label className="text-xs">Lunch start</Label>
                <Input type="time" value={d.lunchBreakStart} onChange={(e) => updateDay(i, { lunchBreakStart: e.target.value })} disabled={!d.enabled} />
              </div>
              <div className="space-y-1 sm:col-span-1">
                <Label className="text-xs">Lunch end</Label>
                <Input type="time" value={d.lunchBreakEnd} onChange={(e) => updateDay(i, { lunchBreakEnd: e.target.value })} disabled={!d.enabled} />
              </div>
              <div className="space-y-1 sm:col-span-1">
                <Label className="text-xs">Slot (min)</Label>
                <Input
                  type="number"
                  min={5}
                  max={240}
                  value={d.slotDurationMinutes}
                  onChange={(e) => updateDay(i, { slotDurationMinutes: Number(e.target.value) })}
                  disabled={!d.enabled}
                />
              </div>
              <div className="space-y-1 sm:col-span-1">
                <Label className="text-xs">Max/day</Label>
                <Input
                  type="number"
                  min={1}
                  placeholder="No limit"
                  value={d.maxPatientsPerDay}
                  onChange={(e) => updateDay(i, { maxPatientsPerDay: e.target.value })}
                  disabled={!d.enabled}
                />
              </div>
            </div>
          ))}
          <div className="flex justify-end pt-2">
            <Button onClick={onSave} disabled={saving}>
              {saving ? "Saving..." : "Save Schedule"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Vacation / Blocked Dates</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Date</Label>
              <Input type="date" value={blockDate} onChange={(e) => setBlockDate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Type</Label>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={blockType}
                onChange={(e) => setBlockType(e.target.value as "Vacation" | "Blocked")}
              >
                <option value="Blocked">Blocked</option>
                <option value="Vacation">Vacation</option>
              </select>
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Reason (optional)</Label>
              <Input value={blockReason} onChange={(e) => setBlockReason(e.target.value)} placeholder="e.g. Conference" />
            </div>
            <Button onClick={onAddBlock} disabled={!blockDate || blockSaving}>
              {blockSaving ? "Adding..." : "Add"}
            </Button>
          </div>

          {(data?.blocks.length ?? 0) === 0 ? (
            <p className="text-sm text-muted-foreground">No vacation or blocked dates configured.</p>
          ) : (
            <ul className="divide-y divide-border rounded-md border border-border">
              {data?.blocks.map((b) => (
                <li key={b.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span>
                    {formatDate(b.blockDate)} — {b.blockType}
                    {b.reason ? ` (${b.reason})` : ""}
                  </span>
                  <button type="button" className="text-xs text-destructive underline" onClick={() => onRemoveBlock(b.id)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
