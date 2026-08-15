"use client";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/layout/EmptyState";
import { AttachmentPreview } from "@/features/consultation/components/AttachmentPreview";
import type { ConsultationAttachment } from "@/features/consultation/types";

/**
 * Feature 2: the consultation Attachments tab's list - extracted out of
 * `visits/[id]/consultation/page.tsx` so it (and the "make an uploaded
 * photo immediately viewable" behavior in particular) is independently
 * testable, same JSX/styling as before, just relocated.
 */
export function AttachmentList({ attachments }: { attachments: ConsultationAttachment[] }) {
  if (attachments.length === 0) {
    return <EmptyState title="No attachments yet" description="Upload clinical images, PDFs, or referral letters below." />;
  }

  return (
    <ul className="space-y-2 text-sm">
      {attachments.map((a) => (
        <li key={a.id} className="flex items-center justify-between gap-3 rounded-md border border-border p-2">
          <span className="flex min-w-0 items-center gap-2">
            <Badge variant="secondary" className="shrink-0">{a.attachmentType}</Badge>
            <span className="truncate">{a.fileName}</span>
          </span>
          <span className="shrink-0">
            <AttachmentPreview attachment={a} />
          </span>
        </li>
      ))}
    </ul>
  );
}
