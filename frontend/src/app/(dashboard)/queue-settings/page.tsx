"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import type { Paginated, PriorityType, QueueSettingItem } from "@/features/clinic-config/types";
import { validateQueueSettingsForm } from "@/features/clinic-config/validation";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

/**
 * Queue configuration (pure configuration - no ticket/queue logic). Manages
 * the clinic-wide `QueueSetting` row (branch_id=null) and the per-clinic
 * `PriorityType` reference list. Per-branch queue settings can be added
 * later by extending this form with a branch selector.
 */
export default function QueueSettingsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: settingsData } = useQuery({
    queryKey: ["queue-settings"],
    queryFn: () => apiClient.get<Paginated<QueueSettingItem>>("/queue-settings"),
  });
  const { data: priorityData } = useQuery({
    queryKey: ["priority-types"],
    queryFn: () => apiClient.get<Paginated<PriorityType>>("/queue-settings/priority-types"),
  });

  const clinicWide = settingsData?.items.find((s) => !s.branch_id) ?? null;

  const [form, setForm] = useState({
    queue_prefix: "A",
    max_daily_queue: 200,
    reset_time: "00:00",
    allow_walkins: true,
    allow_priority_lane: true,
  });

  useEffect(() => {
    if (clinicWide) {
      setForm({
        queue_prefix: clinicWide.queue_prefix,
        max_daily_queue: clinicWide.max_daily_queue,
        reset_time: clinicWide.reset_time?.slice(0, 5) ?? "00:00",
        allow_walkins: clinicWide.allow_walkins,
        allow_priority_lane: clinicWide.allow_priority_lane,
      });
    }
  }, [clinicWide]);

  const saveSettings = useMutation({
    mutationFn: () => {
      const validationError = validateQueueSettingsForm({
        queue_prefix: form.queue_prefix,
        max_daily_queue: Number(form.max_daily_queue),
        reset_time: form.reset_time,
      });
      if (validationError) {
        throw new Error(validationError);
      }
      return apiClient.put<QueueSettingItem>("/queue-settings", {
        branch_id: null,
        queue_prefix: form.queue_prefix,
        max_daily_queue: Number(form.max_daily_queue),
        reset_time: `${form.reset_time}:00`,
        allow_walkins: form.allow_walkins,
        allow_priority_lane: form.allow_priority_lane,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue-settings"] });
      toast({ title: "Queue settings saved", variant: "success" });
    },
    onError: (err) => toast({ title: "Save failed", description: (err as Error).message, variant: "error" }),
  });

  const [newPriority, setNewPriority] = useState({ code: "", label: "" });
  const addPriority = useMutation({
    mutationFn: () => apiClient.post<PriorityType>("/queue-settings/priority-types", newPriority),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["priority-types"] });
      setNewPriority({ code: "", label: "" });
      toast({ title: "Priority type added", variant: "success" });
    },
    onError: (err) => toast({ title: "Add failed", description: (err as Error).message, variant: "error" }),
  });
  const togglePriority = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiClient.put<PriorityType>(`/queue-settings/priority-types/${id}`, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["priority-types"] }),
  });
  const deletePriority = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/queue-settings/priority-types/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["priority-types"] }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Queue Settings</h1>
        <p className="text-sm text-muted-foreground">
          Pure configuration for the future Queue module - prefix, daily cap, reset time, walk-ins, and priority lanes.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Clinic-wide queue configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="queue_prefix">Queue prefix</Label>
              <Input
                id="queue_prefix"
                value={form.queue_prefix}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, queue_prefix: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="max_daily_queue">Max daily queue</Label>
              <Input
                id="max_daily_queue"
                type="number"
                value={form.max_daily_queue}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, max_daily_queue: Number(e.target.value) }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="reset_time">Daily reset time</Label>
              <Input
                id="reset_time"
                type="time"
                value={form.reset_time}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, reset_time: e.target.value }))}
              />
            </div>
            <div className="flex items-center gap-2 pt-6">
              <Checkbox
                id="allow_walkins"
                checked={form.allow_walkins}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, allow_walkins: e.target.checked }))}
              />
              <Label htmlFor="allow_walkins">Allow walk-ins</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="allow_priority_lane"
                checked={form.allow_priority_lane}
                disabled={!canManage}
                onChange={(e) => setForm((f) => ({ ...f, allow_priority_lane: e.target.checked }))}
              />
              <Label htmlFor="allow_priority_lane">Allow priority lane</Label>
            </div>
          </div>
          {canManage ? (
            <Button type="button" isLoading={saveSettings.isPending} onClick={() => saveSettings.mutate()}>
              Save queue settings
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Priority types</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(priorityData?.items ?? []).map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-md border border-border p-2">
              <div>
                <span className="font-medium">{p.label}</span>{" "}
                <span className="text-xs text-muted-foreground">({p.code})</span>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={p.enabled}
                  disabled={!canManage}
                  onChange={(e) => togglePriority.mutate({ id: p.id, enabled: e.target.checked })}
                />
                {canManage ? (
                  <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => deletePriority.mutate(p.id)}>
                    Remove
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
          {canManage ? (
            <div className="flex gap-2 pt-2">
              <Input
                placeholder="Code (e.g. SENIOR)"
                value={newPriority.code}
                onChange={(e) => setNewPriority((v) => ({ ...v, code: e.target.value }))}
              />
              <Input
                placeholder="Label (e.g. Senior Citizen)"
                value={newPriority.label}
                onChange={(e) => setNewPriority((v) => ({ ...v, label: e.target.value }))}
              />
              <Button type="button" onClick={() => addPriority.mutate()} isLoading={addPriority.isPending}>
                Add
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
