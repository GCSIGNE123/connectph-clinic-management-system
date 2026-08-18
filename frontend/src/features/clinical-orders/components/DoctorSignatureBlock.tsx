"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetchBlob } from "@/lib/api-client";

/**
 * Doctor E-Signature: the ONE shared print-signature block used by Medical
 * Certificate, Prescription, and Referral - previously each document
 * inlined its own near-duplicate signature block (see git history on
 * `MedicalCertificatePrintContent.tsx`/`PrescriptionTab.tsx`), and Referral
 * had none at all. `signatureFileApiPath` is the document's own
 * authenticated signature-file endpoint (e.g.
 * `/prescriptions/{id}/signature/file`) - each document type serves its
 * SNAPSHOTTED signature (captured at issue time), never the doctor's
 * current one, so this component never needs to know which document type
 * it's rendering for; it only ever fetches whatever path it's given.
 *
 * Renders nothing extra when no signature is configured/snapshotted -
 * never fabricates one (product decision) - just the existing blank
 * underline area a physical wet-ink signature would go on.
 */
export function DoctorSignatureBlock({
  doctorName,
  doctorPrcLicense,
  doctorPtrNumber,
  clinicLicenseNumber,
  signatureFileApiPath,
  blankLineWhenMissing = false,
  fallbackLabel = "Attending Physician",
  testId = "doctor-signature-block",
}: {
  doctorName?: string | null;
  doctorPrcLicense?: string | null;
  doctorPtrNumber?: string | null;
  clinicLicenseNumber?: string | null;
  /** Authenticated API path to fetch the signature PNG from, or `null`/
   * `undefined` when this document has no signature snapshot. */
  signatureFileApiPath?: string | null;
  /** Medical Certificate always shows a blank fill-in line for missing
   * PRC/PTR (it "reads as incomplete" otherwise); Prescription/Referral
   * omit the line entirely when absent. Defaults to the Prescription/
   * Referral (omit) behavior. */
  blankLineWhenMissing?: boolean;
  /** Shown in place of the doctor's name when absent - each document type
   * has its own existing wording (Prescription: "Prescribing Physician"). */
  fallbackLabel?: string;
  testId?: string;
}) {
  const blobQuery = useQuery({
    queryKey: ["doctor-signature-block", signatureFileApiPath],
    queryFn: () => apiFetchBlob(signatureFileApiPath as string),
    enabled: Boolean(signatureFileApiPath),
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

  const prcLine = doctorPrcLicense
    ? `PRC License No. ${doctorPrcLicense}`
    : blankLineWhenMissing
      ? "PRC License No. ____________________"
      : null;
  const ptrLine = doctorPtrNumber
    ? `PTR No. ${doctorPtrNumber}`
    : blankLineWhenMissing
      ? "PTR No. ____________________"
      : null;

  return (
    <div className="pt-10 flex flex-col items-end">
      <div data-testid={testId} className="w-56 text-center text-xs">
        {objectUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not a static/optimizable asset
          <img src={objectUrl} alt="Doctor signature" className="mx-auto mb-1 h-14 object-contain" />
        ) : null}
        <div className="border-t border-foreground pt-1">
          {doctorName ? `Dr. ${doctorName}` : fallbackLabel}
          {prcLine ? <><br />{prcLine}</> : null}
          {ptrLine ? <><br />{ptrLine}</> : null}
          {clinicLicenseNumber ? <><br />License No. {clinicLicenseNumber}</> : null}
        </div>
      </div>
    </div>
  );
}
