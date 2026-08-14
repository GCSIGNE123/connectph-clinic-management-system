"use client";

import { useRef, useState } from "react";
import { ImageIcon, Plus, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { resolveTvMediaUrl } from "@/features/tv-display/api/tv-display-api";
import {
  useCreateInfoContent,
  useDeleteInfoContent,
  useDeleteInfoContentImage,
  useInfoContent,
  useUpdateInfoContent,
  useUploadInfoContentImage,
} from "@/features/tv-display/hooks/use-tv-displays";
import type { CreateTvInfoContentInput, TvInfoContentType } from "@/features/tv-display/types";
import { useToast } from "@/components/ui/toast";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

const TV_DISPLAY_MANAGE_ROLES = new Set(["Owner", "Administrator", "Receptionist"]);

const CONTENT_TYPE_OPTIONS: { value: TvInfoContentType; label: string }[] = [
  { value: "ServicePricing", label: "Services & Pricing" },
  { value: "DoctorInfo", label: "Doctor Information" },
  { value: "HealthTip", label: "Health Tip" },
  { value: "PreventiveReminder", label: "Preventive Health Reminder" },
  { value: "Announcement", label: "Clinic Announcement" },
  { value: "Promotion", label: "Promotion / Package" },
  { value: "Motivational", label: "Motivational Message" },
];

const EMPTY_FORM: CreateTvInfoContentInput = {
  title: "",
  body: "",
  contentType: "Announcement",
  durationSeconds: 10,
  displayOrder: 0,
};

/** Post-RC1: admin CRUD for the 50/50 TV Display's right-half Information/
 * Advertisement Panel. Clinic-wide (no per-display scoping - see
 * `models/tv_info_content.py` docstring), so unlike Announcements this is
 * its own top-level page rather than a per-display dialog. */
export default function TvInfoContentPage() {
  const { data: currentUser, isLoading: userLoading } = useCurrentUser();
  const { data: items = [], isLoading } = useInfoContent();
  const createMutation = useCreateInfoContent();
  const updateMutation = useUpdateInfoContent();
  const deleteMutation = useDeleteInfoContent();
  const uploadImageMutation = useUploadInfoContentImage();
  const deleteImageMutation = useDeleteInfoContentImage();
  const { toast } = useToast();

  const [form, setForm] = useState<CreateTvInfoContentInput>(EMPTY_FORM);

  if (!userLoading && currentUser && !TV_DISPLAY_MANAGE_ROLES.has(currentUser.role ?? "")) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">Only Owner/Administrator/Receptionist accounts can manage the TV information panel.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">TV Information Panel</h1>
        <p className="text-sm text-muted-foreground">
          Manage the rotating content shown on the right half of the TV Display - service pricing, doctor
          information, health tips, announcements, promotions, and more.
        </p>
      </div>

      <form
        className="space-y-4 rounded-lg border bg-card p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!form.title.trim() || !form.body.trim()) return;
          createMutation.mutate(
            { ...form, displayOrder: items.length },
            { onSuccess: () => setForm(EMPTY_FORM) }
          );
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="ic_title">Title</Label>
            <Input
              id="ic_title"
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Flu Shots Now Available"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ic_type">Content type</Label>
            <Select
              id="ic_type"
              value={form.contentType}
              onChange={(e) => setForm((f) => ({ ...f, contentType: e.target.value as TvInfoContentType }))}
            >
              {CONTENT_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="ic_body">Content</Label>
          <Textarea
            id="ic_body"
            value={form.body}
            onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
            placeholder="Ask our staff about seasonal flu vaccination during your visit."
            rows={3}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="ic_duration">Display duration (seconds)</Label>
            <Input
              id="ic_duration"
              type="number"
              min={3}
              max={120}
              value={form.durationSeconds}
              onChange={(e) => setForm((f) => ({ ...f, durationSeconds: Number(e.target.value) }))}
            />
          </div>
        </div>

        <Button type="submit" disabled={createMutation.isPending}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add content
        </Button>
      </form>

      <div className="space-y-2">
        {isLoading ? (
          <Skeleton className="h-14 w-full" />
        ) : items.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No information panel content yet.</p>
        ) : (
          items.map((item) => {
            const thumbnail = resolveTvMediaUrl(item.imageUrl);
            return (
              <div key={item.id} className="flex items-center justify-between gap-4 rounded-md border px-4 py-3 text-sm">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
                    {thumbnail ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={thumbnail} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <ImageIcon className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium">{item.title}</p>
                    <p className="truncate text-muted-foreground">{item.body}</p>
                    <div className="mt-1 flex items-center gap-1.5">
                      <Badge variant="outline">{item.contentType}</Badge>
                      <Badge variant="outline">{item.durationSeconds}s</Badge>
                      <Badge variant={item.isActive ? "default" : "secondary"}>{item.isActive ? "Active" : "Inactive"}</Badge>
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <PhotoUploadButton
                    contentId={item.id}
                    hasImage={Boolean(item.imageUrl)}
                    isUploading={uploadImageMutation.isPending}
                    onUpload={(file) => {
                      if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
                        toast({ title: "Unsupported file type", description: "Use a JPG, PNG, or WEBP image.", variant: "error" });
                        return;
                      }
                      if (file.size > MAX_IMAGE_BYTES) {
                        toast({ title: "File too large", description: "Maximum size is 5 MB.", variant: "error" });
                        return;
                      }
                      uploadImageMutation.mutate({ id: item.id, file });
                    }}
                    onRemove={() => deleteImageMutation.mutate(item.id)}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => updateMutation.mutate({ id: item.id, input: { isActive: !item.isActive } })}
                  >
                    {item.isActive ? "Disable" : "Enable"}
                  </Button>
                  <button
                    type="button"
                    aria-label="Delete content"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => deleteMutation.mutate(item.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function PhotoUploadButton({
  contentId,
  hasImage,
  isUploading,
  onUpload,
  onRemove,
}: {
  contentId: string;
  hasImage: boolean;
  isUploading: boolean;
  onUpload: (file: File) => void;
  onRemove: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="flex items-center gap-1.5">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="hidden"
        id={`photo_${contentId}`}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
          e.target.value = "";
        }}
      />
      <Button type="button" variant="outline" size="sm" disabled={isUploading} onClick={() => inputRef.current?.click()}>
        <Upload className="mr-1.5 h-3.5 w-3.5" />
        {hasImage ? "Replace photo" : "Add photo"}
      </Button>
      {hasImage ? (
        <button
          type="button"
          aria-label="Remove photo"
          className="text-muted-foreground hover:text-destructive"
          onClick={onRemove}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  );
}
