"use client";

import { useState } from "react";
import { Monitor, Pencil, Trash2, Copy, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertDialog } from "@/components/ui/alert-dialog";
import { useToast } from "@/components/ui/toast";
import type { TvDisplayConfig } from "@/features/tv-display/types";

interface TvDisplayListProps {
  displays: TvDisplayConfig[];
  isLoading: boolean;
  onEdit: (display: TvDisplayConfig) => void;
  onDelete: (id: string) => void;
  onManageAnnouncements: (display: TvDisplayConfig) => void;
}

export function TvDisplayList({ displays, isLoading, onEdit, onDelete, onManageAnnouncements }: TvDisplayListProps) {
  const [pendingDelete, setPendingDelete] = useState<TvDisplayConfig | null>(null);
  const { toast } = useToast();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (displays.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12 text-center">
        <Monitor className="mb-3 h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm font-medium">No TV displays configured yet</p>
        <p className="text-sm text-muted-foreground">Create one to show the live queue in your waiting area.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {displays.map((display) => {
        const publicUrl =
          display.isPublic && display.publicSlug && typeof window !== "undefined"
            ? `${window.location.origin}/tv/${display.publicSlug}`
            : null;
        const shortUrl =
          display.isPublic && display.shortCode && typeof window !== "undefined"
            ? `${window.location.origin}/tv/${display.shortCode}`
            : null;
        return (
          <div key={display.id} className="flex flex-col gap-2 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1">
              <div className="flex items-center gap-2">
                <p className="font-medium">{display.displayName}</p>
                <Badge variant={display.isActive ? "default" : "secondary"}>{display.isActive ? "Active" : "Inactive"}</Badge>
                {display.isPublic ? <Badge variant="outline">Public</Badge> : <Badge variant="outline">Private</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">
                {display.theme} · {display.fontSize} font · next {display.queueSize} · refresh {display.refreshIntervalSeconds}s
              </p>
              {publicUrl ? (
                <div className="flex items-center gap-2 text-xs">
                  <code className="truncate rounded bg-muted px-1.5 py-0.5">{publicUrl}</code>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={() => {
                      void navigator.clipboard?.writeText(publicUrl);
                      toast({ title: "Public URL copied", variant: "success" });
                    }}
                    aria-label="Copy public URL"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                  <a href={publicUrl} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="Open public display">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </div>
              ) : null}
              {shortUrl ? (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">Short:</span>
                  <code className="truncate rounded bg-muted px-1.5 py-0.5">{shortUrl}</code>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={() => {
                      void navigator.clipboard?.writeText(shortUrl);
                      toast({ title: "Short URL copied", variant: "success" });
                    }}
                    aria-label="Copy short URL"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                  <a href={shortUrl} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground" aria-label="Open display via short URL">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </div>
              ) : null}
            </div>
            <div className="flex shrink-0 gap-2">
              <Button variant="outline" size="sm" onClick={() => onManageAnnouncements(display)}>
                Announcements
              </Button>
              <Button variant="outline" size="sm" onClick={() => onEdit(display)} aria-label="Edit display">
                <Pencil className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={() => setPendingDelete(display)} aria-label="Delete display">
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );
      })}

      <AlertDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title={`Delete "${pendingDelete?.displayName}"?`}
        description="This removes the display config. Its public URL (if any) will stop working immediately."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDelete) onDelete(pendingDelete.id);
          setPendingDelete(null);
        }}
      />
    </div>
  );
}
