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
import { Select } from "@/components/ui/select";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import type { Paginated, PriorityType, QueueSettingItem } from "@/features/clinic-config/types";
import { validateQueueSettingsForm } from "@/features/clinic-config/validation";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

interface SimpleDepartment {
  id: string;
  name: string;
  status?: string;
}

interface SimpleDoctor {
  id: string;
  first_name: string;
  last_name: string;
  department_id?: string | null;
  status?: string;
}

interface SimpleBranch {
  id: string;
  name: string;
}

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
  const { data: departmentsData } = useQuery({
    queryKey: ["departments", "queue-settings"],
    queryFn: () => apiClient.get<Paginated<SimpleDepartment>>("/departments?status=Active&limit=100"),
  });
  const { data: doctorsData } = useQuery({
    queryKey: ["doctors", "queue-settings"],
    queryFn: () => apiClient.get<Paginated<SimpleDoctor>>("/doctors?status=Active&limit=200"),
  });
  const { data: branchesData } = useQuery({
    queryKey: ["branches", "queue-settings"],
    queryFn: () => apiClient.get<Paginated<SimpleBranch>>("/branches?limit=100"),
  });

  const clinicWide = settingsData?.items.find((s) => !s.branch_id && !s.department_id && !s.doctor_id) ?? null;
  // Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): any row with
  // a department and/or doctor set is a narrower prefix override (always
  // branch-scoped too - see the override form's note on why branch_id can't
  // be null there) - listed separately below rather than mixed into the
  // single clinic-wide form.
  const overrides = (settingsData?.items ?? []).filter((s) => s.department_id || s.doctor_id);

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

  // Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): per-
  // department and per-doctor prefix override form. Reuses the same
  // `PUT /queue-settings` upsert endpoint as the clinic-wide form above -
  // the backend keys the upsert on (branch_id, department_id, doctor_id),
  // so submitting with a department/doctor selected creates or updates
  // that narrower row without touching the clinic-wide default.
  //
  // branch_id is REQUIRED here (unlike the clinic-wide form, which stores
  // branch_id=null): a Queue ticket's own branch_id is never null (see
  // `models/queue.py`), and `QueueSettingRepository.get_effective_for_doctor`
  // resolves by an EXACT branch_id match - a NULL-branch override would
  // never actually be selected for any real ticket. Defaults to the
  // clinic's only branch when there's just one (the common case for a
  // single-location clinic like Canora).
  const branches = branchesData?.items ?? [];
  const [overrideForm, setOverrideForm] = useState({
    branch_id: "",
    department_id: "",
    doctor_id: "",
    queue_prefix: "",
    max_daily_queue: 200,
  });
  useEffect(() => {
    if (branches.length === 1 && !overrideForm.branch_id) {
      setOverrideForm((f) => ({ ...f, branch_id: branches[0].id }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [branches.length]);
  const saveOverride = useMutation({
    mutationFn: () => {
      if (!overrideForm.branch_id) {
        throw new Error("Select a branch for this override.");
      }
      if (!overrideForm.department_id && !overrideForm.doctor_id) {
        throw new Error("Select a department and/or doctor for this override.");
      }
      const validationError = validateQueueSettingsForm({
        queue_prefix: overrideForm.queue_prefix,
        max_daily_queue: Number(overrideForm.max_daily_queue),
        reset_time: clinicWide?.reset_time?.slice(0, 5) ?? "00:00",
      });
      if (validationError) {
        throw new Error(validationError);
      }
      return apiClient.put<QueueSettingItem>("/queue-settings", {
        branch_id: overrideForm.branch_id,
        department_id: overrideForm.department_id || null,
        doctor_id: overrideForm.doctor_id || null,
        queue_prefix: overrideForm.queue_prefix,
        max_daily_queue: Number(overrideForm.max_daily_queue),
        reset_time: `${clinicWide?.reset_time?.slice(0, 5) ?? "00:00"}:00`,
        allow_walkins: clinicWide?.allow_walkins ?? true,
        allow_priority_lane: clinicWide?.allow_priority_lane ?? true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["queue-settings"] });
      setOverrideForm((f) => ({ ...f, department_id: "", doctor_id: "", queue_prefix: "", max_daily_queue: 200 }));
      toast({ title: "Prefix override saved", variant: "success" });
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
          <CardTitle>Department &amp; doctor prefix overrides</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Give a specific department (e.g. Laboratory -&gt; &quot;L&quot;, Radiology -&gt; &quot;R&quot;) or a specific
            doctor (e.g. Dr. A -&gt; &quot;A&quot;, Dr. B -&gt; &quot;B&quot;, even within the same department) its own queue-number
            prefix instead of the clinic-wide default above. Numbering for each prefix is independently sequenced -
            calling one prefix never affects another. Leave a row&apos;s doctor blank to set a department-wide override
            (applies to every doctor in that department who has no doctor-specific override of their own).
          </p>
          {overrides.length > 0 ? (
            <div className="space-y-2">
              {overrides.map((s) => (
                <div key={s.id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                  <div>
                    <span className="font-medium">{s.doctor_name ? `Dr. ${s.doctor_name}` : s.department_name}</span>
                    {s.doctor_name && s.department_name ? (
                      <span className="text-xs text-muted-foreground"> ({s.department_name})</span>
                    ) : null}
                  </div>
                  <div className="text-muted-foreground">
                    Prefix <span className="font-mono font-semibold text-foreground">{s.queue_prefix}</span> · max{" "}
                    {s.max_daily_queue}/day
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No overrides configured yet - every ticket uses the clinic-wide prefix above.</p>
          )}
          {canManage ? (
            <div className="grid gap-3 rounded-md border border-dashed border-border p-3 sm:grid-cols-5 sm:items-end">
              {branches.length > 1 ? (
                <div className="space-y-1.5">
                  <Label htmlFor="override_branch">Branch</Label>
                  <Select
                    id="override_branch"
                    value={overrideForm.branch_id}
                    onChange={(e) => setOverrideForm((f) => ({ ...f, branch_id: e.target.value }))}
                  >
                    <option value="">(select branch)</option>
                    {branches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </Select>
                </div>
              ) : null}
              <div className="space-y-1.5">
                <Label htmlFor="override_department">Department</Label>
                <Select
                  id="override_department"
                  value={overrideForm.department_id}
                  onChange={(e) => setOverrideForm((f) => ({ ...f, department_id: e.target.value }))}
                >
                  <option value="">(any)</option>
                  {(departmentsData?.items ?? []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="override_doctor">Doctor</Label>
                <Select
                  id="override_doctor"
                  value={overrideForm.doctor_id}
                  onChange={(e) => setOverrideForm((f) => ({ ...f, doctor_id: e.target.value }))}
                >
                  <option value="">(any / department-wide)</option>
                  {(doctorsData?.items ?? [])
                    .filter((d) => !overrideForm.department_id || d.department_id === overrideForm.department_id)
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.first_name} {d.last_name}
                      </option>
                    ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="override_prefix">Prefix</Label>
                <Input
                  id="override_prefix"
                  value={overrideForm.queue_prefix}
                  onChange={(e) => setOverrideForm((f) => ({ ...f, queue_prefix: e.target.value.toUpperCase() }))}
                  placeholder="e.g. B or L"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="override_max">Max/day</Label>
                <Input
                  id="override_max"
                  type="number"
                  value={overrideForm.max_daily_queue}
                  onChange={(e) => setOverrideForm((f) => ({ ...f, max_daily_queue: Number(e.target.value) }))}
                />
              </div>
              <div className="sm:col-span-5">
                <Button type="button" isLoading={saveOverride.isPending} onClick={() => saveOverride.mutate()}>
                  Save override
                </Button>
              </div>
            </div>
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
