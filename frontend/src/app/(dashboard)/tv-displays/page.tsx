"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import {
  useCreateTvDisplay,
  useDeleteTvDisplay,
  useTvDisplays,
  useUpdateTvDisplay,
} from "@/features/tv-display/hooks/use-tv-displays";
import { TvDisplayList } from "@/features/tv-display/components/TvDisplayList";
import { TvDisplayFormDialog } from "@/features/tv-display/components/TvDisplayFormDialog";
import { AnnouncementsPanel } from "@/features/tv-display/components/AnnouncementsPanel";
import type { CreateTvDisplayInput, TvDisplayConfig } from "@/features/tv-display/types";

const CONFIG_MANAGE_ROLES = new Set(["Owner", "Administrator"]);

export default function TvDisplaysPage() {
  const { data: currentUser, isLoading: userLoading } = useCurrentUser();
  const { data: displays = [], isLoading } = useTvDisplays();
  const createMutation = useCreateTvDisplay();
  const [editing, setEditing] = useState<TvDisplayConfig | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [announcing, setAnnouncing] = useState<TvDisplayConfig | null>(null);

  const updateMutation = useUpdateTvDisplay(editing?.id ?? "");
  const deleteMutation = useDeleteTvDisplay();

  if (!userLoading && currentUser && !CONFIG_MANAGE_ROLES.has(currentUser.role ?? "")) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">Only Owner/Administrator accounts can manage TV displays.</p>
      </div>
    );
  }

  const handleSubmit = (input: CreateTvDisplayInput) => {
    if (editing) {
      updateMutation.mutate(input, { onSuccess: () => setFormOpen(false) });
    } else {
      createMutation.mutate(input, { onSuccess: () => setFormOpen(false) });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">TV Displays</h1>
          <p className="text-sm text-muted-foreground">
            Configure Live TV Queue Displays for waiting areas, branches, departments, or doctors.
          </p>
        </div>
        <Button
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus className="mr-1.5 h-4 w-4" />
          New Display
        </Button>
      </div>

      <TvDisplayList
        displays={displays}
        isLoading={isLoading}
        onEdit={(d) => {
          setEditing(d);
          setFormOpen(true);
        }}
        onDelete={(id) => deleteMutation.mutate(id)}
        onManageAnnouncements={(d) => setAnnouncing(d)}
      />

      <TvDisplayFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        onSubmit={handleSubmit}
        isSubmitting={createMutation.isPending || updateMutation.isPending}
      />

      <AnnouncementsPanel display={announcing} onOpenChange={(open) => !open && setAnnouncing(null)} />
    </div>
  );
}
