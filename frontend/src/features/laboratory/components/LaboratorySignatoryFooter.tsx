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
 * `DoctorSignatureBlock`'s "blank rather than guess" convention.
 *
 * Client feedback (round 2 - "the headings reappeared on the standard
 * report"): the "MED TECHNOLOGIST IN CHARGE" / "PATHOLOGIST" role headings
 * above each signature are redundant on EVERY report, not just a
 * qualitative/matrix one - the name, license number, and role line
 * beneath the signature already identify each signatory. This was
 * first removed ONLY for the matrix layout (a `showHeading` prop the
 * matrix's call site set `false`, defaulting `true`/shown for a standard
 * report) - that scoping is exactly why a standard CBC-style report kept
 * printing the heading. There is no documented reason any report type
 * needs it, so the heading is now removed unconditionally, for every
 * report - no `showHeading` prop, nothing for a call site to opt into. */
export function LaboratorySignatoryFooter({ order }: { order: LaboratoryOrder }) {
  if (!order.medTechNameSnapshot && !order.pathologistNameSnapshot) return null;

  return (
    <div className="mt-4 grid grid-cols-2 gap-6 text-[10px]">
      <SignatoryColumn
        name={order.medTechNameSnapshot}
        roleLabel="Medical Technologist"
        licenseLabel="RMT No."
        licenseNumber={order.medTechLicenseSnapshot}
        signatureApiPath={order.medTechSignatureSnapshotUrl ? `/laboratory/orders/${order.id}/med-tech-signature/file` : null}
        signatureAlt="Med Technologist in Charge signature"
        testId="med-tech-signatory"
      />
      <SignatoryColumn
        name={order.pathologistNameSnapshot}
        roleLabel="Pathologist"
        licenseLabel="Lic. No."
        licenseNumber={order.pathologistLicenseSnapshot}
        signatureApiPath={order.pathologistSignatureSnapshotUrl ? `/laboratory/orders/${order.id}/pathologist-signature/file` : null}
        signatureAlt="Pathologist signature"
        testId="pathologist-signatory"
      />
    </div>
  );
}

function SignatoryColumn({
  name,
  roleLabel,
  licenseLabel,
  licenseNumber,
  signatureApiPath,
  signatureAlt,
  testId,
}: {
  name?: string | null;
  roleLabel: string;
  /** "RMT No." for the Med Tech, "Lic. No." for the Pathologist - the two
   * signatories use different professional-license conventions (client
   * reference format), never a shared generic label. */
  licenseLabel: string;
  licenseNumber?: string | null;
  signatureApiPath: string | null;
  /** Alt text for the signature `<img>` - previously derived from the
   * (now-removed) heading `label` prop; kept as its own prop so removing
   * the heading doesn't change this accessible name, which existing tests
   * assert on verbatim (e.g. "Med Technologist in Charge signature"). */
  signatureAlt: string;
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
      {/* Client feedback (signature line alignment): the signature image and
          the line below it were two plain stacked siblings - the image's
          box always ended exactly AT the line, so any ordinary transparent
          margin baked into a signature PNG (the ink rarely fills its own
          canvas edge-to-edge) reads as a gap floating above the line rather
          than a signature crossing it, which is the conventional look for
          a printed signature line. `relative z-10` + `translate-y-2` is a
          pure paint-order/visual shift - it doesn't reserve any extra
          layout space (unlike a margin change), so it can't push the
          name/license/role block below out of place: the image is simply
          allowed to visually overlap the top ~8px of the line beneath it,
          the same amount for both columns since both render through this
          one shared component. A missing signature (`objectUrl` null)
          still renders nothing here - only the (unmoved) line prints. */}
      <div className="relative z-10 mx-auto flex h-10 items-end justify-center">
        {objectUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not a static/optimizable asset
          <img src={objectUrl} alt={signatureAlt} className="max-h-10 translate-y-2 object-contain" />
        ) : null}
      </div>
      <div className="border-t border-slate-400 pt-1">
        {name ? <p className="font-medium text-slate-900">{name}</p> : <p>&nbsp;</p>}
        {/* Client reference format: Name, then license number, then role -
            omitted entirely (not "RMT No." / "Lic. No." with a blank
            trailing value) when no license number was captured, so a
            signatory with none configured still prints cleanly. */}
        {licenseNumber ? (
          <p className="text-muted-foreground">
            {licenseLabel} {licenseNumber}
          </p>
        ) : null}
        <p className="text-muted-foreground">{roleLabel}</p>
      </div>
    </div>
  );
}
