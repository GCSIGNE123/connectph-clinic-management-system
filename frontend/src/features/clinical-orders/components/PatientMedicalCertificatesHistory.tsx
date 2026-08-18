"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { apiClient } from "@/lib/api-client";
import { formatDate } from "@/lib/utils";
import {
  useMedicalCertificatesForPatient,
  useRecordMedicalCertificatePrint,
} from "@/features/clinical-orders/hooks/use-medical-certificates";
import { MEDICAL_CERTIFICATE_TYPE_LABELS, type MedicalCertificate } from "@/features/clinical-orders/types";
import { PrintableDocumentDialog } from "@/features/clinical-orders/components/PrintableDocumentDialog";
import { MedicalCertificatePrintContent } from "@/features/clinical-orders/components/MedicalCertificatePrintContent";
import type { ClinicSettings } from "@/features/clinic-config/types";

const STATUS_BADGE_VARIANT: Record<string, "secondary" | "success" | "destructive"> = {
  Draft: "secondary",
  Issued: "success",
  Cancelled: "destructive",
};

/** Patient Profile "Medical Certificates" tab - read-only history across
 * all of the patient's visits, mirroring `PatientPrescriptionsHistory`'s
 * layout, plus a Print action so any already-issued (or cancelled, for the
 * record) certificate can be reprinted directly from here - e.g. a patient
 * returning later asking for another copy, without reopening the original
 * consultation. Reprinting here follows the exact same view-only role gate
 * as everywhere else (`require_medical_certificate_view_role` on the
 * backend) - this component never exposes create/edit/issue/cancel. */
export function PatientMedicalCertificatesHistory({ patientId }: { patientId: string }) {
  const { data: certificates, isLoading } = useMedicalCertificatesForPatient(patientId);
  const recordPrint = useRecordMedicalCertificatePrint();
  const [printCertificate, setPrintCertificate] = useState<MedicalCertificate | null>(null);

  const clinicQuery = useQuery({
    queryKey: ["clinic-settings"],
    queryFn: () => apiClient.get<ClinicSettings>("/clinic-settings"),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <SkeletonList rows={3} />;
  if (!certificates || certificates.length === 0) {
    return <EmptyState title="No medical certificates yet" description="Certificates issued for this patient will appear here." />;
  }

  function handlePrint(certificate: MedicalCertificate) {
    setPrintCertificate(certificate);
    recordPrint.mutate(certificate.id);
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Certificate #</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Doctor</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {certificates.map((cert) => (
            <tr key={cert.id} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-2 whitespace-nowrap">{formatDate(cert.issuedAt ?? cert.createdAt)}</td>
              <td className="px-3 py-2 font-mono text-xs">{cert.certificateNumber ?? "—"}</td>
              <td className="px-3 py-2 text-muted-foreground">{MEDICAL_CERTIFICATE_TYPE_LABELS[cert.certificateType]}</td>
              <td className="px-3 py-2 text-muted-foreground">
                {cert.doctorName ? `Dr. ${cert.doctorName}` : "—"}
                {/* Doctor's PRC license/PTR number, visible here too (not
                    just on the printed document) so staff can verify them
                    before reprinting for a patient. */}
                {cert.doctorPrcLicense || cert.doctorPtrNumber ? (
                  <div className="text-xs">
                    {cert.doctorPrcLicense ? `PRC ${cert.doctorPrcLicense}` : ""}
                    {cert.doctorPrcLicense && cert.doctorPtrNumber ? " · " : ""}
                    {cert.doctorPtrNumber ? `PTR ${cert.doctorPtrNumber}` : ""}
                  </div>
                ) : null}
              </td>
              <td className="px-3 py-2">
                <Badge variant={STATUS_BADGE_VARIANT[cert.status] ?? "secondary"}>{cert.status}</Badge>
              </td>
              <td className="px-3 py-2 text-right">
                {cert.status !== "Draft" ? (
                  <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => handlePrint(cert)}>
                    Print
                  </Button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <PrintableDocumentDialog
        open={printCertificate !== null}
        onOpenChange={(open) => !open && setPrintCertificate(null)}
        title="Medical Certificate"
        printableId="medical-certificate-printable"
      >
        {printCertificate ? (
          <MedicalCertificatePrintContent certificate={printCertificate} clinic={clinicQuery.data} />
        ) : null}
      </PrintableDocumentDialog>
    </div>
  );
}
