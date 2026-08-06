"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { DAY_NAMES, type Branch, type OperatingHoursEntry, type Paginated } from "@/features/clinic-config/types";
import { Role } from "@/types";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

/** Weekly operating-hours grid (Mon-Sun) per branch. Upserts one row per day. */
export default function OperatingHoursPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: branchesData } = useQuery({
    queryKey: ["branches", "for-hours"],
    queryFn: () => apiClient.get<Paginated<Branch>>("/branches?limit=100"),
  });
  const branches = branchesData?.items ?? [];
  const [branchId, setBranchId] = useState<string>("");

  const { data: hoursData } = useQuery({
    queryKey: ["operating-hours", branchId],
    queryFn: () => apiClient.get<Paginated<OperatingHoursEntry>>(`/operating-hours/branch/${branchId}`),
    enabled: Boolean(branchId),
  });

  const rows = DAY_NAMES.map((_, idx) => hoursData?.items.find((h) => h.day_of_week === idx) ?? null);

  const [drafts, setDrafts] = useState<Record<number, Partial<OperatingHoursEntry>>>({});

  const upsert = useMutation({
    mutationFn: (payload: Partial<OperatingHoursEntry> & { branch_id: string; day_of_week: number }) =>
      apiClient.put<OperatingHoursEntry>("/operating-hours", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["operating-hours", branchId] });
      toast({ title: "Saved", variant: "success" });
    },
    onError: (err) => toast({ title: "Save failed", description: (err as Error).message, variant: "error" }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Operating Hours</h1>
        <p className="text-sm text-muted-foreground">Weekly schedule per branch, including lunch break windows.</p>
      </div>

      <div className="max-w-xs space-y-1.5">
        <Select value={branchId} onChange={(e) => setBranchId(e.target.value)}>
          <option value="">Select a branch...</option>
          {branches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </Select>
      </div>

      {branchId ? (
        <Card>
          <CardHeader>
            <CardTitle>Weekly schedule</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {DAY_NAMES.map((day, idx) => {
              const existing = rows[idx];
              const draft = drafts[idx] ?? {
                opening_time: existing?.opening_time?.slice(0, 5) ?? "08:00",
                closing_time: existing?.closing_time?.slice(0, 5) ?? "17:00",
                is_closed: existing?.is_closed ?? false,
              };
              return (
                <div key={day} className="flex flex-wrap items-center gap-3 rounded-md border border-border p-2">
                  <span className="w-24 text-sm font-medium">{day}</span>
                  <Input
                    type="time"
                    className="w-32"
                    disabled={!canManage}
                    value={draft.opening_time as string}
                    onChange={(e) => setDrafts((d) => ({ ...d, [idx]: { ...draft, opening_time: e.target.value } }))}
                  />
                  <span className="text-muted-foreground">to</span>
                  <Input
                    type="time"
                    className="w-32"
                    disabled={!canManage}
                    value={draft.closing_time as string}
                    onChange={(e) => setDrafts((d) => ({ ...d, [idx]: { ...draft, closing_time: e.target.value } }))}
                  />
                  <label className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={Boolean(draft.is_closed)}
                      disabled={!canManage}
                      onChange={(e) => setDrafts((d) => ({ ...d, [idx]: { ...draft, is_closed: e.target.checked } }))}
                    />
                    Closed
                  </label>
                  {canManage ? (
                    <Button
                      type="button"
                      size="sm"
                      onClick={() =>
                        upsert.mutate({
                          branch_id: branchId,
                          day_of_week: idx,
                          opening_time: `${draft.opening_time}:00`,
                          closing_time: `${draft.closing_time}:00`,
                          is_closed: Boolean(draft.is_closed),
                        })
                      }
                    >
                      Save
                    </Button>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
