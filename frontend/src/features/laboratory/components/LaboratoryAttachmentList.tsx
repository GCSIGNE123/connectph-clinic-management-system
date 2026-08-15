"use client";

import { EmptyState } from "@/components/layout/EmptyState";
import { LaboratoryAttachmentPreview } from "@/features/laboratory/components/LaboratoryAttachmentPreview";
import type { LaboratoryAttachment } from "@/features/laboratory/types";

/** Feature 4: the Result Entry dialog's attachment list - mirrors
 * `consultation/components/AttachmentList.tsx`'s shape. */
export function LaboratoryAttachmentList({ attachments }: { attachments: LaboratoryAttachment[] }) {
  if (attachments.length === 0) {
    return <EmptyState title="No images attached yet" description="Upload the clinic's actual laboratory result image below." />;
  }

  return (
    <ul className="flex flex-wrap gap-3">
      {attachments.map((a) => (
        <li key={a.id} className="flex flex-col items-center gap-1">
          <LaboratoryAttachmentPreview attachment={a} />
          <span className="max-w-[5.5rem] truncate text-[11px] text-muted-foreground" title={a.fileName}>
            {a.fileName}
          </span>
        </li>
      ))}
    </ul>
  );
}
