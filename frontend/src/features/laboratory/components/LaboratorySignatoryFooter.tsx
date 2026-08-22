"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetchBlob } from "@/lib/api-client";
import type { LaboratoryOrder } from "@/features/laboratory/types";

/** Round 6 (Laboratory Report Signatories): the printed report's Med Tech
 * In Charge (left) + Pathologist (right) signatory block, at the bottom of
 * the report after the result table/notes. Both columns read ONLY the
 * snapshot fields captured once at release (`medTechNameSnapshot`/
 * `pathologistNameSnapshot`/etc.) - never re-resolved from the current
 * Med Tech's or Pathologist's live profile, so a historical report never
 * changes after release (see the implementation report's snapshot
 * section). Renders nothing extra when a name wasn't captured (order not
 * yet released, or released with no Pathologist selected) - never
 * fabricates a signatory, matching the existing Doctor E-Signature
 * `DoctorSignatureBlock`'s "blank rather than guess" convention. */
export function LaboratorySignatoryFooter({ order }: { order: LaboratoryOrder }) {
  if (!order.medTechNameSnapshot && !order.pathologistNameSnapshot) return null;

  return (
    <div className="mt-4 grid grid-cols-2 gap-6 text-[10px]">
      <SignatoryColumn
        label="Med Technician in Charge"
        name={order.medTechNameSnapshot}
        roleLabel="Medical Technologist"
        licenseNumber={order.medTechLicenseSnapshot}
        signatureApiPath={order.medTechSignatureSnapshotUrl ? `/laboratory/orders/${order.id}/med-tech-signature/file` : null}
        testId="med-tech-signatory"
      />
      <SignatoryColumn
        label="Pathologist"
        name={order.pathologistNameSnapshot}
        roleLabel="Pathologist"
        licenseNumber={order.pathologistLicenseSnapshot}
        signatureApiPath={order.pathologistSignatureSnapshotUrl ? `/laboratory/orders/${order.id}/pathologist-signature/file` : null}
        testId="pathologist-signatory"
      />
    </div>
  );
}

function SignatoryColumn({
  label,
  name,
  roleLabel,
  licenseNumber,
  signatureApiPath,
  testId,
}: {
  label: string;
  name?: string | null;
  roleLabel: string;
  licenseNumber?: string | null;
  signatureApiPath: string | null;
  testId: string;
}) {
  const blobQuery = useQuery({
    queryKey: ["laboratory-signatory-block", signatureApiPath],
    queryFn: () => apiFetchBlob(signatureApiPath as string),
    enabled: Boolean(signatureApiPath),
    staleTime: Infinity,
    retry: false,
  });

  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blobQuery.data) {
      setObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(blobQuery.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blobQuery.data]);

  return (
    <div data-testid={testId} className="text-center">
      <p className="mb-1 font-semibold uppercase tracking-wide text-slate-700">{label}</p>
      <div className="mx-auto flex h-10 items-end justify-center">
        {objectUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not a static/optimizable asset
          <img src={objectUrl} alt={`${label} signature`} className="max-h-10 object-contain" />
        ) : null}
      </div>
      <div className="border-t border-slate-400 pt-1">
        {name ? <p className="font-medium text-slate-900">{name}</p> : <p>&nbsp;</p>}
        <p className="text-muted-foreground">{roleLabel}</p>
        {licenseNumber ? <p className="text-muted-foreground">Lic. No. {licenseNumber}</p> : null}
      </div>
    </div>
  );
}
