"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import type { ClinicSettings } from "@/features/clinic-config/types";
import { Role } from "@/types";
import { ThemeSettings } from "@/components/layout/ThemeSettings";

const MANAGE_ROLES = new Set<Role>([Role.Owner, Role.Administrator]);

/**
 * Clinic Settings + Branding - a singleton-per-clinic settings page backed
 * by GET/PUT /clinic-settings and PATCH /clinic-settings/branding (the
 * clinic row itself, extended in Phase 4 - see docs/DATABASE.md). Combined
 * into one tabbed page per the task's "settings area with tabs" guidance.
 */
export default function ClinicSettingsPage() {
  const { data: currentUser } = useCurrentUser();
  const canManage = Boolean(currentUser && MANAGE_ROLES.has(currentUser.role));
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"general" | "branding" | "appearance" | "inventory">("general");

  const { data: settings } = useQuery({
    queryKey: ["clinic-settings"],
    queryFn: () => apiClient.get<ClinicSettings>("/clinic-settings"),
  });

  const [general, setGeneral] = useState<Partial<ClinicSettings>>({});
  const [branding, setBranding] = useState<Partial<ClinicSettings>>({});
  const [inventory, setInventory] = useState<Partial<ClinicSettings>>({});

  useEffect(() => {
    if (settings) {
      setGeneral(settings);
      setBranding(settings);
      setInventory(settings);
    }
  }, [settings]);

  const saveGeneral = useMutation({
    mutationFn: () =>
      apiClient.put<ClinicSettings>("/clinic-settings", {
        name: general.name,
        short_name: general.short_name || null,
        address: general.address || null,
        province: general.province || null,
        city: general.city || null,
        barangay: general.barangay || null,
        zip_code: general.zip_code || null,
        telephone: general.telephone || null,
        mobile: general.mobile || null,
        email: general.email || null,
        website: general.website || null,
        tin: general.tin || null,
        license_number: general.license_number || null,
        timezone: general.timezone,
        language: general.language,
        currency: general.currency,
        date_format: general.date_format,
        time_format: general.time_format,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-settings"] });
      toast({ title: "Clinic settings saved", variant: "success" });
    },
    onError: (err) => toast({ title: "Save failed", description: (err as Error).message, variant: "error" }),
  });

  const saveBranding = useMutation({
    mutationFn: () =>
      apiClient.patch<ClinicSettings>("/clinic-settings/branding", {
        primary_color: branding.primary_color || null,
        secondary_color: branding.secondary_color || null,
        theme: branding.theme,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-settings"] });
      toast({ title: "Branding saved", variant: "success" });
    },
    onError: (err) => toast({ title: "Save failed", description: (err as Error).message, variant: "error" }),
  });

  const saveInventory = useMutation({
    mutationFn: () =>
      apiClient.put<ClinicSettings>("/clinic-settings", {
        medicine_expiry_warning_days_tier1: inventory.medicine_expiry_warning_days_tier1,
        medicine_expiry_warning_days_tier2: inventory.medicine_expiry_warning_days_tier2,
        medicine_expiry_warning_days_tier3: inventory.medicine_expiry_warning_days_tier3,
        medicine_expiry_warning_days_tier4: inventory.medicine_expiry_warning_days_tier4,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-settings"] });
      toast({ title: "Expiry warning thresholds saved", variant: "success" });
    },
    onError: (err) => toast({ title: "Save failed", description: (err as Error).message, variant: "error" }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Clinic Settings</h1>
        <p className="text-sm text-muted-foreground">General clinic information, locale preferences, and branding.</p>
      </div>

      <div className="flex gap-2 border-b border-border">
        {(["general", "branding", "appearance", "inventory"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium capitalize ${
              tab === t ? "border-b-2 border-primary text-primary" : "text-muted-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "general" ? (
        <Card>
          <CardHeader>
            <CardTitle>General information</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Clinic name" value={general.name} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, name: v }))} />
            <Field label="Short name" value={general.short_name} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, short_name: v }))} />
            <Field label="Address" value={general.address} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, address: v }))} />
            <Field label="Province" value={general.province} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, province: v }))} />
            <Field label="City" value={general.city} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, city: v }))} />
            <Field label="Barangay" value={general.barangay} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, barangay: v }))} />
            <Field label="ZIP code" value={general.zip_code} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, zip_code: v }))} />
            <Field label="Telephone" value={general.telephone} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, telephone: v }))} />
            <Field label="Mobile" value={general.mobile} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, mobile: v }))} />
            <Field label="Email" value={general.email} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, email: v }))} />
            <Field label="Website" value={general.website} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, website: v }))} />
            <Field label="TIN" value={general.tin} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, tin: v }))} />
            <Field label="License number" value={general.license_number} disabled={!canManage} onChange={(v) => setGeneral((g) => ({ ...g, license_number: v }))} />

            <div className="space-y-1.5">
              <Label>Timezone</Label>
              <Input
                value={general.timezone ?? ""}
                disabled={!canManage}
                onChange={(e) => setGeneral((g) => ({ ...g, timezone: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Currency</Label>
              <Input
                value={general.currency ?? ""}
                disabled={!canManage}
                onChange={(e) => setGeneral((g) => ({ ...g, currency: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Date format</Label>
              <Input
                value={general.date_format ?? ""}
                disabled={!canManage}
                onChange={(e) => setGeneral((g) => ({ ...g, date_format: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Time format</Label>
              <Select
                value={general.time_format ?? "12h"}
                disabled={!canManage}
                onChange={(e) => setGeneral((g) => ({ ...g, time_format: e.target.value }))}
              >
                <option value="12h">12-hour</option>
                <option value="24h">24-hour</option>
              </Select>
            </div>
            {canManage ? (
              <div className="sm:col-span-2">
                <Button type="button" isLoading={saveGeneral.isPending} onClick={() => saveGeneral.mutate()}>
                  Save changes
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {tab === "branding" ? (
        <Card>
          <CardHeader>
            <CardTitle>Branding</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Primary color</Label>
              <Input
                type="color"
                value={branding.primary_color ?? "#2563eb"}
                disabled={!canManage}
                onChange={(e) => setBranding((b) => ({ ...b, primary_color: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Secondary color</Label>
              <Input
                type="color"
                value={branding.secondary_color ?? "#0891b2"}
                disabled={!canManage}
                onChange={(e) => setBranding((b) => ({ ...b, secondary_color: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Theme</Label>
              <Select
                value={branding.theme ?? "system"}
                disabled={!canManage}
                onChange={(e) => setBranding((b) => ({ ...b, theme: e.target.value }))}
              >
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="system">System</option>
              </Select>
            </div>
            <p className="text-sm text-muted-foreground sm:col-span-2">
              Logo/favicon/login-background uploads use a presigned-URL stub (`POST
              /clinic-settings/branding/{"{asset}"}/upload`) - see backend TODO for real Supabase Storage wiring.
            </p>
            {canManage ? (
              <div className="sm:col-span-2">
                <Button type="button" isLoading={saveBranding.isPending} onClick={() => saveBranding.mutate()}>
                  Save branding
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {tab === "appearance" ? (
        <Card>
          <CardHeader>
            <CardTitle>Appearance</CardTitle>
          </CardHeader>
          <CardContent>
            <ThemeSettings />
          </CardContent>
        </Card>
      ) : null}

      {tab === "inventory" ? (
        <Card>
          <CardHeader>
            <CardTitle>Medicine Expiry Warning Thresholds</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <p className="text-sm text-muted-foreground sm:col-span-2">
              Days-before-expiry thresholds used by the daily expiry check to warn Receptionists and Doctors.
              Must be strictly descending: Tier 1 &gt; Tier 2 &gt; Tier 3 &gt; Tier 4.
            </p>
            <NumberField
              label="Tier 1 (days)"
              value={inventory.medicine_expiry_warning_days_tier1}
              disabled={!canManage}
              onChange={(v) => setInventory((s) => ({ ...s, medicine_expiry_warning_days_tier1: v }))}
            />
            <NumberField
              label="Tier 2 (days)"
              value={inventory.medicine_expiry_warning_days_tier2}
              disabled={!canManage}
              onChange={(v) => setInventory((s) => ({ ...s, medicine_expiry_warning_days_tier2: v }))}
            />
            <NumberField
              label="Tier 3 (days)"
              value={inventory.medicine_expiry_warning_days_tier3}
              disabled={!canManage}
              onChange={(v) => setInventory((s) => ({ ...s, medicine_expiry_warning_days_tier3: v }))}
            />
            <NumberField
              label="Tier 4 (days)"
              value={inventory.medicine_expiry_warning_days_tier4}
              disabled={!canManage}
              onChange={(v) => setInventory((s) => ({ ...s, medicine_expiry_warning_days_tier4: v }))}
            />
            {canManage ? (
              <div className="sm:col-span-2">
                <Button type="button" isLoading={saveInventory.isPending} onClick={() => saveInventory.mutate()}>
                  Save thresholds
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value?: string | null;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value?: number | null;
  onChange: (value: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input
        type="number"
        min={1}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
