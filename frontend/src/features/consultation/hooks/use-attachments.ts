"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import type { AttachmentType } from "@/features/consultation/types";

export function useAttachments(consultationId: string | null) {
  return useQuery({
    queryKey: ["consultation", "attachments", consultationId],
    queryFn: () => consultationApi.listAttachments(consultationId as string),
    enabled: Boolean(consultationId),
  });
}

/** Real upload (Feature 2): sends the actual file bytes, so the attachment
 * is immediately viewable afterward via its returned `fileUrl`. */
export function useUploadAttachment(consultationId: string | null) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { attachmentType: AttachmentType; file: File }) => {
      if (!consultationId) throw new Error("No consultation open");
      return consultationApi.uploadAttachment(consultationId, payload);
    },
    onSuccess: () => {
      toast({ title: "Attachment uploaded", variant: "success" });
      queryClient.invalidateQueries({ queryKey: ["consultation", "attachments", consultationId] });
    },
    onError: (error) => {
      toast({
        title: "Upload failed",
        description: error instanceof ApiError ? error.message : "Something went wrong.",
        variant: "error",
      });
    },
  });
}
