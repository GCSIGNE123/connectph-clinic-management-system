"use client";

import { SignaturePanel } from "@/components/signature/SignaturePanel";
import { pathologistsApi } from "@/features/pathologists/api/pathologists-api";
import type { Pathologist } from "@/features/pathologists/types";

/** Round 6: Pathologist e-signature settings, using the shared
 * `SignaturePanel` (generalized from `DoctorSignatureSettings`). Manage
 * permission (Owner/Administrator only - `require_config_manage_role`) is
 * enforced by the backend; a 403 surfaces as the panel's own error text. */
export function PathologistSignatureSettings({
  pathologist,
  onPathologistUpdated,
}: {
  pathologist: Pathologist;
  onPathologistUpdated: (pathologist: Pathologist) => void;
}) {
  return (
    <SignaturePanel
      hasSignature={Boolean(pathologist.signature_url)}
      previewQueryKey={["pathologist-signature-preview", pathologist.id, pathologist.signature_url]}
      getBlob={() => pathologistsApi.getSignatureBlob(pathologist.id)}
      upload={async (file) => {
        const updated = await pathologistsApi.uploadSignature(pathologist.id, file);
        onPathologistUpdated(updated);
      }}
      remove={async () => {
        const updated = await pathologistsApi.removeSignature(pathologist.id);
        onPathologistUpdated(updated);
      }}
    />
  );
}
