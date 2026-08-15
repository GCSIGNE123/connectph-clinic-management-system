"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { cn } from "@/lib/utils";
import { useVisit } from "@/features/visits/hooks/use-visit";
import { usePatient } from "@/features/patients/hooks/use-patient";
import { computeAge } from "@/features/patients/components/PatientsTable";
import { VisitTimeline } from "@/features/visits/components/VisitTimeline";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { LockBanner } from "@/features/doctor-workspace/components/LockBanner";
import { useOpenConsultation, useCompleteConsultation } from "@/features/consultation/hooks/use-consultation";
import { useSoapAutosave } from "@/features/consultation/hooks/use-soap-autosave";
import { useAddDiagnosis } from "@/features/consultation/hooks/use-diagnoses";
import { useAttachments, useUploadAttachment } from "@/features/consultation/hooks/use-attachments";
import { AttachmentList } from "@/features/consultation/components/AttachmentList";
import type { AttachmentType, DiagnosisStatus, DiagnosisType, SoapNoteInput } from "@/features/consultation/types";
import { computeBmi } from "@/features/consultation/bmi";
import { ClinicalOrdersTab } from "@/features/clinical-orders/components/ClinicalOrdersTab";
import { PrescriptionTab } from "@/features/clinical-orders/components/PrescriptionTab";
import { ApiError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/utils";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "soap", label: "SOAP" },
  { key: "diagnosis", label: "Diagnosis" },
  { key: "orders", label: "Orders" },
  { key: "prescription", label: "Prescription" },
  { key: "attachments", label: "Attachments" },
  { key: "timeline", label: "Timeline" },
  { key: "audit", label: "Audit Log" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const PLACEHOLDER_TABS = new Set<TabKey>(["audit"]);

export default function ConsultationPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const visitId = params.id;

  const { data: visit, isLoading: visitLoading } = useVisit(visitId);
  const { data: currentUser } = useCurrentUser();
  const {
    data: consultation,
    isLoading: consultationLoading,
    isError: consultationIsError,
    error: consultationError,
  } = useOpenConsultation(visitId);
  const { data: patient } = usePatient(visit?.patientId);

  const [activeTab, setActiveTab] = useState<TabKey>("overview");

  const canEdit = Boolean(consultation?.lock.isSelf) && consultation?.status !== "Signed";
  const autosave = useSoapAutosave(consultation?.id ?? null, canEdit);
  const addDiagnosis = useAddDiagnosis(consultation?.id ?? "");
  const completeConsultation = useCompleteConsultation(consultation?.id ?? "");
  const attachmentsQuery = useAttachments(consultation?.id ?? null);
  const uploadAttachment = useUploadAttachment(consultation?.id ?? null);

  useEffect(() => {
    if (consultation?.soapNote) {
      const n = consultation.soapNote;
      autosave.initialize({
        chiefComplaint: n.chiefComplaint,
        historyOfPresentIllness: n.historyOfPresentIllness,
        pastMedicalHistory: n.pastMedicalHistory,
        familyHistory: n.familyHistory,
        socialHistory: n.socialHistory,
        reviewOfSystems: n.reviewOfSystems,
        subjectiveNotes: n.subjectiveNotes,
        bloodPressure: n.bloodPressure,
        pulseRate: n.pulseRate,
        respiratoryRate: n.respiratoryRate,
        temperature: n.temperature,
        heightCm: n.heightCm,
        weightKg: n.weightKg,
        oxygenSaturation: n.oxygenSaturation,
        physicalExamination: n.physicalExamination,
        clinicalFindings: n.clinicalFindings,
        clinicalImpression: n.clinicalImpression,
        differentialDiagnosis: n.differentialDiagnosis,
        assessmentNotes: n.assessmentNotes,
        treatmentPlan: n.treatmentPlan,
        patientInstructions: n.patientInstructions,
        followupRecommendation: n.followupRecommendation,
        referralNotes: n.referralNotes,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consultation?.id]);

  const [diagnosisForm, setDiagnosisForm] = useState<{
    diagnosisType: DiagnosisType;
    status: DiagnosisStatus;
    notes: string;
    icd10Code: string;
  }>({ diagnosisType: "Primary", status: "Working", notes: "", icd10Code: "" });

  const liveBmi = useMemo(() => computeBmi(autosave.values.heightCm, autosave.values.weightKg), [autosave.values.heightCm, autosave.values.weightKg]);

  // Phase 20 (item 9): optional Doctor-set fee override, entered at the
  // point of completing the consultation, that overrides Doctor.consultation_fee/
  // ClinicService.default_price on the auto-created invoice. Left blank
  // means the pre-Phase-20 pricing behavior is unchanged.
  const [consultationFeeInput, setConsultationFeeInput] = useState("");

  if (visitLoading || consultationLoading) {
    return <SkeletonList rows={8} />;
  }

  if (!visit) {
    return <EmptyState title="Visit not found" description="This visit record may have been removed." />;
  }

  // Real bug found live: a failed useOpenConsultation() (e.g. 403 "This
  // account is not linked to a Doctor record.") was previously invisible -
  // `consultation` just stayed undefined, `canEdit` silently evaluated to
  // false, and the SOAP/diagnosis/orders form rendered as a normal-looking
  // but permanently read-only, unexplained shell. Surface the real reason
  // instead of a mysteriously uneditable page.
  if (consultationIsError) {
    return (
      <EmptyState
        title="Could not open this consultation"
        description={
          consultationError instanceof ApiError
            ? consultationError.message
            : "Please try again, or contact an administrator if this keeps happening."
        }
      />
    );
  }

  const canActAsDoctor = currentUser ? ["Owner", "Administrator", "Doctor"].includes(currentUser.role) : false;
  if (!canActAsDoctor) {
    return <EmptyState title="Not authorized" description="Only clinical staff may view a consultation." />;
  }

  const set = (field: keyof SoapNoteInput, value: unknown) => {
    autosave.setValues({ ...autosave.values, [field]: value });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button type="button" variant="ghost" size="icon" onClick={() => router.push(`/visits/${visitId}`)} aria-label="Back to visit">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <div>
          <h1 className="text-xl font-semibold text-foreground">Consultation</h1>
          <p className="text-sm text-muted-foreground">{visit.visitNumber}</p>
        </div>
        {consultation ? <Badge variant={consultation.status === "Signed" ? "success" : "secondary"}>{consultation.status}</Badge> : null}
        {canEdit ? (
          <span className="ml-auto text-xs text-muted-foreground" aria-live="polite">
            {autosave.status === "saving" ? "Saving…" : autosave.status === "unsaved" ? "Unsaved changes" : autosave.status === "saved" ? "Saved" : ""}
          </span>
        ) : null}
      </div>

      {consultation ? <LockBanner lock={consultation.lock} /> : null}

      {/* Patient Summary header - always visible */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-6 pt-6">
          <Avatar name={patient ? `${patient.firstName} ${patient.lastName}` : "?"} src={patient?.photoUrl} size="lg" />
          <div className="grid flex-1 grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-4">
            <SummaryField label="Patient" value={patient ? `${patient.firstName} ${patient.lastName}` : "—"} />
            <SummaryField label="Patient #" value={patient?.patientNumber ?? "—"} />
            <SummaryField label="Visit #" value={visit.visitNumber} />
            <SummaryField label="Queue #" value={visit.queueNumber ?? "—"} />
            <SummaryField label="Age / Gender" value={patient ? `${computeAge(patient.birthDate)} / ${patient.gender}` : "—"} />
            <SummaryField label="Blood type" value={patient?.bloodType ?? "Unknown"} />
            <SummaryField label="Allergies" value={patient?.allergies || "None recorded"} />
            <SummaryField label="Current medications" value="Not tracked yet (Prescription module)" />
            <SummaryField
              label="Emergency contact"
              value={patient?.emergencyContactName ? `${patient.emergencyContactName} (${patient.emergencyContactPhone ?? "—"})` : "Not recorded"}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-1 border-b border-border" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "rounded-t-md px-3 py-2 text-sm font-medium transition-colors",
              activeTab === tab.key ? "border-b-2 border-primary text-primary" : "text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" ? (
        <Card>
          <CardHeader>
            <CardTitle>Encounter overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <SummaryField label="Doctor" value={consultation?.doctorName ?? "—"} />
            <SummaryField label="Status" value={consultation?.status ?? "—"} />
            <SummaryField label="Started" value={consultation ? formatDateTime(consultation.startedAt) : "—"} />
            <SummaryField label="Completed" value={consultation?.completedAt ? formatDateTime(consultation.completedAt) : "—"} />
            <SummaryField label="Signed" value={consultation?.signedAt ? formatDateTime(consultation.signedAt) : "—"} />
            <div className="flex flex-wrap items-end gap-2 pt-3">
              {canEdit && consultation && consultation.status !== "Completed" && consultation.status !== "Signed" ? (
                <>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Consultation fee (optional override)</label>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      className="w-40"
                      placeholder="Default pricing"
                      value={consultationFeeInput}
                      onChange={(e) => setConsultationFeeInput(e.target.value)}
                    />
                  </div>
                  <Button
                    type="button"
                    onClick={() => {
                      autosave.saveNow();
                      completeConsultation.mutate(consultationFeeInput ? Number(consultationFeeInput) : undefined);
                    }}
                    disabled={completeConsultation.isPending}
                  >
                    Mark Consultation Complete
                  </Button>
                </>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "soap" ? (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Subjective</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <Field label="Chief complaint" value={autosave.values.chiefComplaint} onChange={(v) => set("chiefComplaint", v)} disabled={!canEdit} />
              <Field label="History of present illness" value={autosave.values.historyOfPresentIllness} onChange={(v) => set("historyOfPresentIllness", v)} disabled={!canEdit} />
              <Field label="Past medical history" value={autosave.values.pastMedicalHistory} onChange={(v) => set("pastMedicalHistory", v)} disabled={!canEdit} />
              <Field label="Family history" value={autosave.values.familyHistory} onChange={(v) => set("familyHistory", v)} disabled={!canEdit} />
              <Field label="Social history" value={autosave.values.socialHistory} onChange={(v) => set("socialHistory", v)} disabled={!canEdit} />
              <Field label="Review of systems" value={autosave.values.reviewOfSystems} onChange={(v) => set("reviewOfSystems", v)} disabled={!canEdit} />
              <Field label="Additional subjective notes" value={autosave.values.subjectiveNotes} onChange={(v) => set("subjectiveNotes", v)} disabled={!canEdit} className="md:col-span-2" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Objective / Vitals</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <NumberField label="Blood pressure" value={autosave.values.bloodPressure ?? ""} onChange={(v) => set("bloodPressure", v)} disabled={!canEdit} isText />
                <NumberField label="Pulse (bpm)" value={autosave.values.pulseRate} onChange={(v) => set("pulseRate", v)} disabled={!canEdit} />
                <NumberField label="Resp. rate" value={autosave.values.respiratoryRate} onChange={(v) => set("respiratoryRate", v)} disabled={!canEdit} />
                <NumberField label="Temp (°C)" value={autosave.values.temperature} onChange={(v) => set("temperature", v)} disabled={!canEdit} />
                <NumberField label="Height (cm)" value={autosave.values.heightCm} onChange={(v) => set("heightCm", v)} disabled={!canEdit} />
                <NumberField label="Weight (kg)" value={autosave.values.weightKg} onChange={(v) => set("weightKg", v)} disabled={!canEdit} />
                <div>
                  <label className="text-xs font-medium text-muted-foreground">BMI</label>
                  <p className="mt-1 rounded-md border border-border bg-muted/30 px-2 py-1.5 text-sm font-medium">{liveBmi ?? "—"}</p>
                </div>
                <NumberField label="O2 sat (%)" value={autosave.values.oxygenSaturation} onChange={(v) => set("oxygenSaturation", v)} disabled={!canEdit} />
              </div>
              <Field label="Physical examination" value={autosave.values.physicalExamination} onChange={(v) => set("physicalExamination", v)} disabled={!canEdit} />
              <Field label="Clinical findings" value={autosave.values.clinicalFindings} onChange={(v) => set("clinicalFindings", v)} disabled={!canEdit} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Assessment</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <Field label="Clinical impression" value={autosave.values.clinicalImpression} onChange={(v) => set("clinicalImpression", v)} disabled={!canEdit} />
              <Field label="Differential diagnosis" value={autosave.values.differentialDiagnosis} onChange={(v) => set("differentialDiagnosis", v)} disabled={!canEdit} />
              <Field label="Assessment notes" value={autosave.values.assessmentNotes} onChange={(v) => set("assessmentNotes", v)} disabled={!canEdit} className="md:col-span-2" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Plan</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <Field label="Treatment plan" value={autosave.values.treatmentPlan} onChange={(v) => set("treatmentPlan", v)} disabled={!canEdit} />
              <Field label="Patient instructions" value={autosave.values.patientInstructions} onChange={(v) => set("patientInstructions", v)} disabled={!canEdit} />
              <Field label="Follow-up recommendation" value={autosave.values.followupRecommendation} onChange={(v) => set("followupRecommendation", v)} disabled={!canEdit} />
              <Field label="Referral notes" value={autosave.values.referralNotes} onChange={(v) => set("referralNotes", v)} disabled={!canEdit} />
            </CardContent>
          </Card>

          {canEdit ? (
            <div className="flex justify-end">
              <Button type="button" onClick={() => autosave.saveNow()} disabled={!autosave.isDirty}>
                Save Progress
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {activeTab === "diagnosis" ? (
        <Card>
          <CardHeader>
            <CardTitle>Diagnoses</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {consultation && consultation.diagnoses.length > 0 ? (
              <ul className="space-y-2">
                {consultation.diagnoses.map((d) => (
                  <li key={d.id} className="rounded-md border border-border p-3 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge variant={d.diagnosisType === "Primary" ? "default" : "secondary"}>{d.diagnosisType}</Badge>
                      <Badge variant={d.status === "Final" ? "success" : "secondary"}>{d.status}</Badge>
                      {d.icd10Code ? <span className="font-mono text-xs text-muted-foreground">{d.icd10Code}</span> : null}
                    </div>
                    {d.notes ? <p className="mt-1 text-muted-foreground">{d.notes}</p> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No diagnoses recorded yet" description="Add a diagnosis below." />
            )}

            {canEdit ? (
              <div className="space-y-3 border-t border-border pt-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Type</label>
                    <Select
                      value={diagnosisForm.diagnosisType}
                      onChange={(e) => setDiagnosisForm((f) => ({ ...f, diagnosisType: e.target.value as DiagnosisType }))}
                    >
                      <option value="Primary">Primary</option>
                      <option value="Secondary">Secondary</option>
                    </Select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Status</label>
                    <Select
                      value={diagnosisForm.status}
                      onChange={(e) => setDiagnosisForm((f) => ({ ...f, status: e.target.value as DiagnosisStatus }))}
                    >
                      <option value="Working">Working</option>
                      <option value="Final">Final</option>
                    </Select>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">ICD-10 code (optional)</label>
                    <Input value={diagnosisForm.icd10Code} onChange={(e) => setDiagnosisForm((f) => ({ ...f, icd10Code: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Notes</label>
                  <Textarea value={diagnosisForm.notes} onChange={(e) => setDiagnosisForm((f) => ({ ...f, notes: e.target.value }))} rows={3} />
                </div>
                <Button
                  type="button"
                  onClick={() =>
                    addDiagnosis.mutate(
                      { ...diagnosisForm, icd10Code: diagnosisForm.icd10Code || null },
                      { onSuccess: () => setDiagnosisForm({ diagnosisType: "Primary", status: "Working", notes: "", icd10Code: "" }) }
                    )
                  }
                  disabled={addDiagnosis.isPending}
                >
                  Add Diagnosis
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "orders" && consultation ? (
        <ClinicalOrdersTab
          consultationId={consultation.id}
          visitId={visitId}
          canEdit={canEdit}
          patientName={consultation.patientName ?? (patient ? `${patient.firstName} ${patient.lastName}` : undefined)}
          doctorName={consultation.doctorName}
          visitNumber={visit.visitNumber}
        />
      ) : null}

      {activeTab === "prescription" && consultation ? (
        <PrescriptionTab
          consultationId={consultation.id}
          visitId={visitId}
          patientId={patient?.id}
          canEdit={canEdit}
          patientName={consultation.patientName ?? (patient ? `${patient.firstName} ${patient.lastName}` : undefined)}
          patientAge={patient ? computeAge(patient.birthDate) : undefined}
          doctorName={consultation.doctorName}
          doctorPrcLicense={consultation.doctorPrcLicense}
          doctorPtrNumber={consultation.doctorPtrNumber}
          visitNumber={visit.visitNumber}
        />
      ) : null}

      {activeTab === "attachments" ? (
        <Card>
          <CardHeader>
            <CardTitle>Attachments</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <AttachmentList attachments={attachmentsQuery.data ?? []} />
            {canEdit ? (
              <AttachmentUploadForm
                onUpload={(type, file) => uploadAttachment.mutate({ attachmentType: type, file })}
                pending={uploadAttachment.isPending}
              />
            ) : null}
            <EmptyState title="Lab Requests" description="Placeholder — Laboratory module not built yet." />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "timeline" ? (
        <Card>
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <VisitTimeline events={visit.timeline} />
          </CardContent>
        </Card>
      ) : null}

      {PLACEHOLDER_TABS.has(activeTab) ? (
        <Card>
          <CardHeader>
            <CardTitle>{TABS.find((t) => t.key === activeTab)?.label}</CardTitle>
          </CardHeader>
          <CardContent>
            <EmptyState
              title="Coming in a future phase"
              description={`${TABS.find((t) => t.key === activeTab)?.label} will be available once that module is built.`}
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function SummaryField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-medium text-foreground">{value}</p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  disabled,
  className,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (v: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <Textarea value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled} rows={3} className="mt-1" />
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  disabled,
  isText,
}: {
  label: string;
  value: number | string | null | undefined;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  isText?: boolean;
}) {
  return (
    <div>
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <Input
        type={isText ? "text" : "number"}
        value={value ?? ""}
        onChange={(e) => onChange(isText ? e.target.value || null : e.target.value === "" ? null : Number(e.target.value))}
        disabled={disabled}
        className="mt-1"
      />
    </div>
  );
}

function AttachmentUploadForm({
  onUpload,
  pending,
}: {
  onUpload: (type: AttachmentType, file: File) => void;
  pending: boolean;
}) {
  const [type, setType] = useState<AttachmentType>("ClinicalImage");
  return (
    <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
      <div>
        <label className="text-xs font-medium text-muted-foreground">Type</label>
        <Select value={type} onChange={(e) => setType(e.target.value as AttachmentType)}>
          <option value="ClinicalImage">Clinical Image</option>
          <option value="PDF">PDF File</option>
          <option value="ReferralLetter">Referral Letter</option>
        </Select>
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground">File</label>
        <input
          type="file"
          className="mt-1 block text-sm"
          disabled={pending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(type, file);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
