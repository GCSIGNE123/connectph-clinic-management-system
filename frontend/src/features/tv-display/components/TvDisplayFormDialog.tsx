"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import type { CreateTvDisplayInput, TvDisplayConfig } from "@/features/tv-display/types";

interface TvDisplayFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial?: TvDisplayConfig | null;
  onSubmit: (input: CreateTvDisplayInput) => void;
  isSubmitting?: boolean;
}

const EMPTY: CreateTvDisplayInput = {
  displayName: "",
  isPublic: false,
  theme: "ClinicBranded",
  fontSize: "Large",
  animationSpeed: "Normal",
  queueSize: 10,
  refreshIntervalSeconds: 30,
  ttsEnabled: false,
  ttsTemplate: "Queue {queue_number}, please proceed to {room}.",
};

/** Create/edit dialog for a TV display config - Owner/Administrator only
 * (the page itself is role-gated; this dialog assumes the caller already
 * checked that). */
export function TvDisplayFormDialog({ open, onOpenChange, initial, onSubmit, isSubmitting }: TvDisplayFormDialogProps) {
  const [form, setForm] = useState<CreateTvDisplayInput>(EMPTY);

  useEffect(() => {
    if (initial) {
      setForm({
        branchId: initial.branchId ?? undefined,
        departmentId: initial.departmentId ?? undefined,
        doctorId: initial.doctorId ?? undefined,
        displayName: initial.displayName,
        isPublic: initial.isPublic,
        theme: initial.theme,
        fontSize: initial.fontSize,
        animationSpeed: initial.animationSpeed,
        queueSize: initial.queueSize,
        refreshIntervalSeconds: initial.refreshIntervalSeconds,
        logoUrl: initial.logoUrl ?? undefined,
        primaryColor: initial.primaryColor ?? undefined,
        secondaryColor: initial.secondaryColor ?? undefined,
        ttsEnabled: initial.ttsEnabled,
        ttsTemplate: initial.ttsTemplate ?? undefined,
      });
    } else {
      setForm(EMPTY);
    }
  }, [initial, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial ? "Edit TV Display" : "New TV Display"}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(form);
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="display_name">Display name</Label>
            <Input
              id="display_name"
              value={form.displayName}
              onChange={(e) => setForm((f) => ({ ...f, displayName: e.target.value }))}
              placeholder="Lobby Waiting Area TV"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="theme">Theme</Label>
              <Select
                id="theme"
                value={form.theme}
                onChange={(e) => setForm((f) => ({ ...f, theme: e.target.value as CreateTvDisplayInput["theme"] }))}
              >
                <option value="ClinicBranded">Clinic Branded</option>
                <option value="Light">Light</option>
                <option value="Dark">Dark</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="font_size">Font size</Label>
              <Select
                id="font_size"
                value={form.fontSize}
                onChange={(e) => setForm((f) => ({ ...f, fontSize: e.target.value as CreateTvDisplayInput["fontSize"] }))}
              >
                <option value="Small">Small</option>
                <option value="Medium">Medium</option>
                <option value="Large">Large</option>
                <option value="ExtraLarge">Extra Large</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="animation">Animation speed</Label>
              <Select
                id="animation"
                value={form.animationSpeed}
                onChange={(e) =>
                  setForm((f) => ({ ...f, animationSpeed: e.target.value as CreateTvDisplayInput["animationSpeed"] }))
                }
              >
                <option value="None">None</option>
                <option value="Slow">Slow</option>
                <option value="Normal">Normal</option>
                <option value="Fast">Fast</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="queue_size">Next Queue size</Label>
              <Input
                id="queue_size"
                type="number"
                min={1}
                max={50}
                value={form.queueSize}
                onChange={(e) => setForm((f) => ({ ...f, queueSize: Number(e.target.value) }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="refresh">Refresh interval (seconds)</Label>
              <Input
                id="refresh"
                type="number"
                min={5}
                max={600}
                value={form.refreshIntervalSeconds}
                onChange={(e) => setForm((f) => ({ ...f, refreshIntervalSeconds: Number(e.target.value) }))}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="logo_url">Logo URL (optional)</Label>
            <Input
              id="logo_url"
              value={form.logoUrl ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, logoUrl: e.target.value }))}
              placeholder="https://..."
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="primary_color">Primary color</Label>
              <Input
                id="primary_color"
                value={form.primaryColor ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, primaryColor: e.target.value }))}
                placeholder="#0f172a"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="secondary_color">Secondary color</Label>
              <Input
                id="secondary_color"
                value={form.secondaryColor ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, secondaryColor: e.target.value }))}
                placeholder="#38bdf8"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="is_public"
              checked={form.isPublic}
              onChange={(e) => setForm((f) => ({ ...f, isPublic: e.target.checked }))}
            />
            <Label htmlFor="is_public" className="cursor-pointer font-normal">
              Public mode (no login required to view this display)
            </Label>
          </div>
          {initial?.isPublic && initial.publicSlug ? (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              Public URL:{" "}
              <code className="font-mono">
                {typeof window !== "undefined" ? window.location.origin : ""}/tv/{initial.publicSlug}
              </code>
            </p>
          ) : null}

          <div className="flex items-center gap-2">
            <Checkbox
              id="tts_enabled"
              checked={form.ttsEnabled}
              onChange={(e) => setForm((f) => ({ ...f, ttsEnabled: e.target.checked }))}
            />
            <Label htmlFor="tts_enabled" className="cursor-pointer font-normal">
              Text-to-speech announcement text (architecture only - no audio playback)
            </Label>
          </div>
          {form.ttsEnabled ? (
            <div className="space-y-1.5">
              <Label htmlFor="tts_template">Announcement template</Label>
              <Input
                id="tts_template"
                value={form.ttsTemplate ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, ttsTemplate: e.target.value }))}
              />
              <p className="text-xs text-muted-foreground">
                Placeholders: {"{queue_number}"}, {"{room}"}, {"{doctor}"}, {"{patient_initials}"}
              </p>
            </div>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {initial ? "Save changes" : "Create display"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
