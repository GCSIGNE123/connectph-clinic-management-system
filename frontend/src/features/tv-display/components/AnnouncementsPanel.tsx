"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Trash2 } from "lucide-react";
import type { TvAnnouncementType, TvDisplayConfig } from "@/features/tv-display/types";
import {
  useAnnouncements,
  useCreateAnnouncement,
  useDeleteAnnouncement,
  useToggleAnnouncement,
} from "@/features/tv-display/hooks/use-tv-displays";

interface AnnouncementsPanelProps {
  display: TvDisplayConfig | null;
  onOpenChange: (open: boolean) => void;
}

export function AnnouncementsPanel({ display, onOpenChange }: AnnouncementsPanelProps) {
  const configId = display?.id ?? null;
  const { data: announcements = [], isLoading } = useAnnouncements(configId);
  const createMutation = useCreateAnnouncement(configId ?? "");
  const toggleMutation = useToggleAnnouncement(configId ?? "");
  const deleteMutation = useDeleteAnnouncement(configId ?? "");

  const [message, setMessage] = useState("");
  const [type, setType] = useState<TvAnnouncementType>("Welcome");

  return (
    <Dialog open={Boolean(display)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Announcements - {display?.displayName}</DialogTitle>
        </DialogHeader>

        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!message.trim()) return;
            createMutation.mutate(
              { message, announcementType: type, displayOrder: announcements.length },
              { onSuccess: () => setMessage("") }
            );
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="ann_message">New announcement</Label>
            <Input id="ann_message" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Wash your hands regularly." />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ann_type">Type</Label>
            <Select id="ann_type" value={type} onChange={(e) => setType(e.target.value as TvAnnouncementType)}>
              <option value="Welcome">Welcome</option>
              <option value="HealthTip">Health Tip</option>
              <option value="Promotion">Promotion</option>
              <option value="Emergency">Emergency</option>
            </Select>
          </div>
          <Button type="submit" disabled={createMutation.isPending}>
            Add
          </Button>
        </form>

        <div className="max-h-80 space-y-2 overflow-y-auto">
          {isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : announcements.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">No announcements yet.</p>
          ) : (
            announcements.map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate">{a.message}</p>
                  <div className="mt-0.5 flex items-center gap-1.5">
                    <Badge variant="outline">{a.announcementType}</Badge>
                    <Badge variant={a.isActive ? "default" : "secondary"}>{a.isActive ? "Active" : "Inactive"}</Badge>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => toggleMutation.mutate({ id: a.id, isActive: !a.isActive })}
                  >
                    {a.isActive ? "Disable" : "Enable"}
                  </Button>
                  <button
                    type="button"
                    aria-label="Delete announcement"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => deleteMutation.mutate(a.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
