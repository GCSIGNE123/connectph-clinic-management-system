"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, ImageOff, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { consultationApi } from "@/features/consultation/api/consultation-api";
import type { ConsultationAttachment } from "@/features/consultation/types";

/**
 * Feature 2: makes an uploaded attachment actually viewable. The file is
 * served by an authenticated endpoint (not a public URL - see
 * `consultations.py::get_attachment_file`'s docstring for why), so a plain
 * `<img src>`/`<a href>` can't reach it; this fetches the real bytes via
 * the normal authenticated API client and turns them into a blob: URL.
 *
 * - `ClinicalImage` attachments render a real thumbnail, click-to-enlarge
 *   into a full-size dialog.
 * - Every other type (PDF, ReferralLetter) gets a plain "View" button that
 *   opens the same blob in a new tab - no thumbnail to render, but still
 *   immediately viewable, not just a filename.
 * - A failed fetch/decode (deleted file, network hiccup, non-image bytes
 *   under an image type) shows a clear broken-image state, never a
 *   silently broken `<img>` icon or an unhandled promise rejection.
 */
export function AttachmentPreview({ attachment }: { attachment: ConsultationAttachment }) {
  const isImage = attachment.attachmentType === "ClinicalImage";

  const blobQuery = useQuery({
    queryKey: ["consultation", "attachment-file", attachment.id],
    queryFn: () => consultationApi.getAttachmentFileBlob(attachment.fileUrl),
    staleTime: Infinity,
  });

  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [imageFailedToRender, setImageFailedToRender] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    if (!blobQuery.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(blobQuery.data);
    setObjectUrl(url);
    // Revoke on cleanup (attachment removed from the list, or component
    // unmounted) so repeated view sessions don't leak blob: URLs.
    return () => URL.revokeObjectURL(url);
  }, [blobQuery.data]);

  if (blobQuery.isLoading) {
    return (
      <span className="inline-flex h-10 w-10 items-center justify-center rounded border border-border bg-muted">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
      </span>
    );
  }

  if (blobQuery.isError || !objectUrl) {
    return (
      <span
        className="inline-flex h-10 w-10 items-center justify-center rounded border border-dashed border-destructive/40 text-destructive"
        title="Could not load this file"
      >
        <ImageOff className="h-4 w-4" aria-hidden="true" />
      </span>
    );
  }

  if (!isImage) {
    return (
      <Button type="button" variant="outline" size="sm" onClick={() => window.open(objectUrl, "_blank", "noopener,noreferrer")}>
        <FileText className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
        View
      </Button>
    );
  }

  return (
    <>
      {imageFailedToRender ? (
        <span
          className="inline-flex h-10 w-10 items-center justify-center rounded border border-dashed border-destructive/40 text-destructive"
          title="Image failed to load"
        >
          <ImageOff className="h-4 w-4" aria-hidden="true" />
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setLightboxOpen(true)}
          className="block h-10 w-10 overflow-hidden rounded border border-border transition hover:ring-2 hover:ring-ring"
          aria-label={`View ${attachment.fileName} full size`}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL, not a static/optimizable asset */}
          <img
            src={objectUrl}
            alt={attachment.fileName}
            className="h-full w-full object-cover"
            onError={() => setImageFailedToRender(true)}
          />
        </button>
      )}

      <Dialog open={lightboxOpen} onOpenChange={setLightboxOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{attachment.fileName}</DialogTitle>
          </DialogHeader>
          {imageFailedToRender ? (
            <p className="py-8 text-center text-sm text-muted-foreground">This image could not be loaded.</p>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not a static/optimizable asset
            <img src={objectUrl} alt={attachment.fileName} className="max-h-[75vh] w-full rounded object-contain" onError={() => setImageFailedToRender(true)} />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
