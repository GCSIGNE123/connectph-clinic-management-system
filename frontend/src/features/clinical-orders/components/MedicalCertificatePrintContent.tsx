"use client";

import { formatDate } from "@/lib/utils";
import { MEDICAL_CERTIFICATE_TYPE_LABELS, type MedicalCertificate } from "@/features/clinical-orders/types";
import { DoctorSignatureBlock } from "@/features/clinical-orders/components/DoctorSignatureBlock";
import type { ClinicSettings } from "@/features/clinic-config/types";

/** The certificate's printable body - shared between `MedicalCertificateTab`
 * (print/reprint from the Consultation Workspace) and
 * `PatientMedicalCertificatesHistory` (reprint from the Patient record), so
 * both surfaces render byte-for-byte the same document instead of two
 * near-duplicate templates drifting apart. Rendered inside
 * `PrintableDocumentDialog` by both callers. */
export function MedicalCertificatePrintContent({
  certificate,
  clinic,
  visitNumber,
}: {
  certificate: MedicalCertificate;
  clinic?: ClinicSettings;
  visitNumber?: string | null;
}) {
  return (
    <>
      <div className="flex items-center gap-3 border-b-2 border-foreground pb-2">
        {clinic?.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={clinic.logo_url} alt="" className="h-12 w-12 object-contain" />
        ) : null}
        <div className="flex-1 text-center">
          <p className="text-base font-bold uppercase tracking-wide">{clinic?.name ?? certificate.clinicName ?? "Clinic"}</p>
          <p className="text-xs text-muted-foreground">
            {[clinic?.address ?? certificate.clinicAddress, clinic?.city, clinic?.province].filter(Boolean).join(", ")}
          </p>
          <p className="text-xs text-muted-foreground">
            {[clinic?.telephone ?? clinic?.mobile, clinic?.email].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>

      <div className="text-center">
        <p className="font-semibold uppercase tracking-wide">{MEDICAL_CERTIFICATE_TYPE_LABELS[certificate.certificateType]}</p>
        <p className="text-xs text-muted-foreground">{certificate.certificateNumber ?? "DRAFT - NOT YET ISSUED"}</p>
      </div>

      <div className="border-t border-dashed pt-2 space-y-1">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Patient</span>
          <span>
            {certificate.patientName ?? "-"}
            {typeof certificate.patientAge === "number" ? `, ${certificate.patientAge} y/o` : ""}
            {certificate.patientSex ? `, ${certificate.patientSex}` : ""}
          </span>
        </div>
        <div className="flex justify-between"><span className="text-muted-foreground">Visit #</span><span>{visitNumber ?? certificate.visitNumber ?? "-"}</span></div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Date issued</span>
          <span>{certificate.issuedAt ? formatDate(certificate.issuedAt) : formatDate(certificate.createdAt)}</span>
        </div>
      </div>

      <div className="border-t-2 border-foreground pt-2 space-y-3">
        {certificate.findings ? (
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Findings</p>
            <p>{certificate.findings}</p>
          </div>
        ) : null}
        {certificate.recommendation ? (
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Recommendation</p>
            <p>{certificate.recommendation}</p>
          </div>
        ) : null}
        {certificate.restDays || certificate.dateFrom || certificate.dateTo ? (
          <div>
            <p className="text-xs font-semibold uppercase text-muted-foreground">Rest period</p>
            <p>
              {certificate.restDays ? `${certificate.restDays} day(s)` : ""}
              {certificate.dateFrom || certificate.dateTo
                ? ` (${formatDate(certificate.dateFrom ?? "")} to ${formatDate(certificate.dateTo ?? "")})`
                : ""}
            </p>
          </div>
        ) : null}
      </div>

      {/* PRC/PTR always print, even blank - a certificate reads as
          incomplete/unofficial without these lines present at all, so a
          doctor with none on file still gets a fillable line rather than
          the lines silently disappearing (unlike Prescription's print,
          which omits them entirely when absent) - see
          `blankLineWhenMissing` on `DoctorSignatureBlock`. */}
      <DoctorSignatureBlock
        doctorName={certificate.doctorName}
        doctorPrcLicense={certificate.doctorPrcLicense}
        doctorPtrNumber={certificate.doctorPtrNumber}
        clinicLicenseNumber={clinic?.license_number ?? certificate.clinicLicenseNumber}
        signatureFileApiPath={certificate.doctorSignatureSnapshotUrl ? `/medical-certificates/${certificate.id}/signature/file` : null}
        blankLineWhenMissing
        testId="medical-certificate-signature-block"
      />
    </>
  );
}
