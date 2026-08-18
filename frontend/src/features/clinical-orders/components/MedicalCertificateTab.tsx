"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/layout/EmptyState";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { apiClient } from "@/lib/api-client";
import { formatDate } from "@/lib/utils";
import {
  useCancelMedicalCertificate,
  useCreateMedicalCertificateDraft,
  useIssueMedicalCertificate,
  useMedicalCertificatesForConsultation,
  useRecordMedicalCertificatePrint,
  useReissueMedicalCertificate,
  useUpdateMedicalCertificateDraft,
} from "@/features/clinical-orders/hooks/use-medical-certificates";
import {
  MEDICAL_CERTIFICATE_TEMPLATE_TEXT,
  MEDICAL_CERTIFICATE_TYPE_LABELS,
  type MedicalCertificate,
  type MedicalCertificateDraftInput,
  type MedicalCertificateType,
} from "@/features/clinical-orders/types";
import { PrintableDocumentDialog } from "@/features/clinical-orders/components/PrintableDocumentDialog";
import { MedicalCertificatePrintContent } from "@/features/clinical-orders/components/MedicalCertificatePrintContent";
import type { Diagnosis } from "@/features/consultation/types";
import type { ClinicSettings } from "@/features/clinic-config/types";

const STATUS_BADGE_VARIANT: Record<MedicalCertificate["status"], "default" | "secondary" | "success" | "destructive"> = {
  Draft: "secondary",
  Issued: "success",
  Cancelled: "destructive",
};

function emptyDraft(): MedicalCertificateDraftInput {
  return { certificateType: "MedicalCertificate", findings: "", recommendation: "", restDays: null, dateFrom: null, dateTo: null, notes: "" };
}

/** Joins the consultation's Primary/Final diagnoses into a starting-point
 * findings summary - a ONE-TIME snapshot copied into the draft's text field
 * (product decision 8), never a live reference. The doctor edits freely
 * from here before issuing. */
function prefillFindingsFromDiagnoses(diagnoses: Diagnosis[]): string {
  const relevant = diagnoses.filter((d) => d.diagnosisType === "Primary" || d.status === "Final");
  const source = relevant.length > 0 ? relevant : diagnoses;
  return source
    .map((d) => [d.icd10Code, d.notes].filter(Boolean).join(" - "))
    .filter(Boolean)
    .join("; ");
}

export function MedicalCertificateTab({
  consultationId,
  visitId,
  patientId,
  canEdit,
  diagnoses,
  visitNumber,
}: {
  consultationId: string;
  visitId: string;
  patientId?: string | null;
  canEdit: boolean;
  diagnoses: Diagnosis[];
  visitNumber?: string | null;
}) {
  const certificatesQuery = useMedicalCertificatesForConsultation(consultationId);
  const createDraft = useCreateMedicalCertificateDraft(consultationId, visitId, patientId);
  const updateDraft = useUpdateMedicalCertificateDraft(consultationId, visitId, patientId);
  const issueCertificate = useIssueMedicalCertificate(consultationId, visitId, patientId);
  const cancelCertificate = useCancelMedicalCertificate(consultationId, visitId, patientId);
  const reissueCertificate = useReissueMedicalCertificate(consultationId, visitId, patientId);
  const recordPrint = useRecordMedicalCertificatePrint();

  const clinicQuery = useQuery({
    queryKey: ["clinic-settings"],
    queryFn: () => apiClient.get<ClinicSettings>("/clinic-settings"),
    staleTime: 5 * 60 * 1000,
  });
  const clinic = clinicQuery.data;

  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [form, setForm] = useState<MedicalCertificateDraftInput>(() => ({
    ...emptyDraft(),
    findings: prefillFindingsFromDiagnoses(diagnoses),
  }));
  const [cancelTarget, setCancelTarget] = useState<MedicalCertificate | null>(null);
  const [reissueTarget, setReissueTarget] = useState<MedicalCertificate | null>(null);
  const [reasonInput, setReasonInput] = useState("");
  const [printCertificate, setPrintCertificate] = useState<MedicalCertificate | null>(null);

  if (certificatesQuery.isLoading) return <SkeletonList rows={4} />;

  const certificates = certificatesQuery.data ?? [];
  const drafts = certificates.filter((c) => c.status === "Draft");
  const issuedOrCancelled = certificates.filter((c) => c.status !== "Draft");

  function startNewDraft() {
    setEditingDraftId(null);
    setForm({ ...emptyDraft(), findings: prefillFindingsFromDiagnoses(diagnoses) });
  }

  function editExistingDraft(draft: MedicalCertificate) {
    setEditingDraftId(draft.id);
    setForm({
      certificateType: draft.certificateType, findings: draft.findings ?? "", recommendation: draft.recommendation ?? "",
      restDays: draft.restDays, dateFrom: draft.dateFrom, dateTo: draft.dateTo, notes: draft.notes ?? "",
    });
  }

  function applyTypeTemplate(type: MedicalCertificateType) {
    const template = MEDICAL_CERTIFICATE_TEMPLATE_TEXT[type];
    setForm((f) => ({
      ...f, certificateType: type,
      recommendation: f.recommendation?.trim() ? f.recommendation : template.recommendation,
    }));
  }

  function saveDraft() {
    if (editingDraftId) {
      updateDraft.mutate({ certificateId: editingDraftId, input: form }, { onSuccess: () => setEditingDraftId(null) });
    } else {
      createDraft.mutate(form, { onSuccess: () => setForm(emptyDraft()) });
    }
  }

  function handlePrint(certificate: MedicalCertificate) {
    setPrintCertificate(certificate);
    recordPrint.mutate(certificate.id);
  }

  const isSickLeave = form.certificateType === "SickLeave";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Medical Certificates</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {certificates.length === 0 ? (
            <EmptyState title="No medical certificates yet" description="Fill out the form below to draft one." />
          ) : (
            <ul className="space-y-3">
              {drafts.map((cert) => (
                <li key={cert.id} className="rounded-md border border-border p-3 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant={STATUS_BADGE_VARIANT[cert.status]}>{cert.status}</Badge>
                    <span className="font-medium">{MEDICAL_CERTIFICATE_TYPE_LABELS[cert.certificateType]}</span>
                    {canEdit ? (
                      <div className="ml-auto flex gap-2">
                        <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => editExistingDraft(cert)}>
                          Edit
                        </Button>
                        <Button
                          type="button" size="sm" className="h-7 text-xs"
                          onClick={() => issueCertificate.mutate(cert.id)}
                          disabled={issueCertificate.isPending}
                        >
                          Issue Certificate
                        </Button>
                      </div>
                    ) : null}
                  </div>
                  {cert.findings ? <p className="mt-1 text-muted-foreground">{cert.findings}</p> : null}
                </li>
              ))}

              {issuedOrCancelled.map((cert) => (
                <li key={cert.id} className="rounded-md border border-border p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-muted-foreground">{cert.certificateNumber}</span>
                    <Badge variant={STATUS_BADGE_VARIANT[cert.status]}>{cert.status}</Badge>
                    <span className="font-medium">{MEDICAL_CERTIFICATE_TYPE_LABELS[cert.certificateType]}</span>
                    <span className="text-muted-foreground">{cert.issuedAt ? formatDate(cert.issuedAt) : ""}</span>
                    <div className="ml-auto flex gap-2">
                      <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => handlePrint(cert)}>
                        Print
                      </Button>
                      {canEdit && cert.status === "Issued" ? (
                        <>
                          <Button
                            type="button" variant="outline" size="sm" className="h-7 text-xs"
                            onClick={() => { setReissueTarget(cert); setReasonInput(""); }}
                          >
                            Correct (Reissue)
                          </Button>
                          <Button
                            type="button" variant="destructive" size="sm" className="h-7 text-xs"
                            onClick={() => { setCancelTarget(cert); setReasonInput(""); }}
                          >
                            Cancel
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </div>
                  {cert.status === "Cancelled" ? (
                    <p className="mt-1 text-xs text-destructive">
                      Cancelled{cert.cancelledReason ? ` - ${cert.cancelledReason}` : ""}
                      {cert.supersededById ? " (superseded by a new certificate)" : ""}
                    </p>
                  ) : null}
                  {/* Doctor's PRC license and PTR number - visible on screen,
                      not just on the printed document, so staff can confirm
                      them before reprinting. */}
                  <p className="mt-1 text-xs text-muted-foreground">
                    {cert.doctorName ? `Dr. ${cert.doctorName}` : "Attending Physician"}
                    {cert.doctorPrcLicense ? ` · PRC ${cert.doctorPrcLicense}` : ""}
                    {cert.doctorPtrNumber ? ` · PTR ${cert.doctorPtrNumber}` : ""}
                  </p>
                  {cert.findings ? <p className="mt-1 text-muted-foreground">{cert.findings}</p> : null}
                </li>
              ))}
            </ul>
          )}

          {canEdit ? (
            <div className="space-y-4 border-t border-border pt-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">{editingDraftId ? "Edit draft" : "New draft"}</h3>
                {editingDraftId ? (
                  <button type="button" className="text-xs text-primary underline" onClick={startNewDraft}>
                    Start a new draft instead
                  </button>
                ) : null}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Certificate type</Label>
                  <Select value={form.certificateType} onChange={(e) => applyTypeTemplate(e.target.value as MedicalCertificateType)}>
                    {Object.entries(MEDICAL_CERTIFICATE_TYPE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </Select>
                </div>
                {isSickLeave ? (
                  <div>
                    <Label>Rest days (optional)</Label>
                    <Input
                      type="number" min={0} value={form.restDays ?? ""}
                      onChange={(e) => setForm((f) => ({ ...f, restDays: e.target.value ? Number(e.target.value) : null }))}
                    />
                  </div>
                ) : null}
              </div>
              {isSickLeave ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <Label>From (optional)</Label>
                    <Input type="date" value={form.dateFrom ?? ""} onChange={(e) => setForm((f) => ({ ...f, dateFrom: e.target.value || null }))} />
                  </div>
                  <div>
                    <Label>To (optional)</Label>
                    <Input type="date" value={form.dateTo ?? ""} onChange={(e) => setForm((f) => ({ ...f, dateTo: e.target.value || null }))} />
                  </div>
                </div>
              ) : null}
              <div>
                <Label>Findings</Label>
                <Textarea rows={3} value={form.findings ?? ""} onChange={(e) => setForm((f) => ({ ...f, findings: e.target.value }))} />
              </div>
              <div>
                <Label>Recommendation</Label>
                <Textarea rows={2} value={form.recommendation ?? ""} onChange={(e) => setForm((f) => ({ ...f, recommendation: e.target.value }))} />
              </div>
              <div>
                <Label>Notes (internal, optional)</Label>
                <Textarea rows={2} value={form.notes ?? ""} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
              <div className="flex justify-end">
                <Button type="button" onClick={saveDraft} disabled={createDraft.isPending || updateDraft.isPending}>
                  {editingDraftId ? "Save Draft" : "Save Draft"}
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Cancel dialog - reason required, matches the backend's own
          validation rather than trusting a disabled Confirm button. */}
      <Dialog open={cancelTarget !== null} onOpenChange={(open) => !open && setCancelTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Cancel certificate {cancelTarget?.certificateNumber}</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label>Reason (required)</Label>
            <Textarea rows={3} value={reasonInput} onChange={(e) => setReasonInput(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCancelTarget(null)}>Back</Button>
            <Button
              type="button" variant="destructive" disabled={!reasonInput.trim() || cancelCertificate.isPending}
              onClick={() => cancelTarget && cancelCertificate.mutate(
                { certificateId: cancelTarget.id, reason: reasonInput },
                { onSuccess: () => setCancelTarget(null) }
              )}
            >
              Confirm Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reissue (Cancel + Issue New) dialog. */}
      <Dialog open={reissueTarget !== null} onOpenChange={(open) => !open && setReissueTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Correct certificate {reissueTarget?.certificateNumber}</DialogTitle></DialogHeader>
          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">
              This cancels the original certificate and issues a brand-new one with the same content, ready to edit
              before reprinting. The original stays visible in history as Cancelled.
            </p>
            <Label>Reason for correction (required)</Label>
            <Textarea rows={3} value={reasonInput} onChange={(e) => setReasonInput(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setReissueTarget(null)}>Back</Button>
            <Button
              type="button" disabled={!reasonInput.trim() || reissueCertificate.isPending}
              onClick={() => reissueTarget && reissueCertificate.mutate(
                { certificateId: reissueTarget.id, reason: reasonInput },
                { onSuccess: () => setReissueTarget(null) }
              )}
            >
              Confirm Correction
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PrintableDocumentDialog
        open={printCertificate !== null}
        onOpenChange={(open) => !open && setPrintCertificate(null)}
        title="Medical Certificate"
        printableId="medical-certificate-printable"
      >
        {printCertificate ? (
          <MedicalCertificatePrintContent certificate={printCertificate} clinic={clinic} visitNumber={visitNumber} />
        ) : null}
      </PrintableDocumentDialog>
    </div>
  );
}
