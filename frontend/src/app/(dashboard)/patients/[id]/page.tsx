"use client";

import { useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Camera, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { RecordDateRangeFilter } from "@/components/filters/RecordDateRangeFilter";
import { cn } from "@/lib/utils";
import { usePatient, usePatientQr } from "@/features/patients/hooks/use-patient";
import { useUploadPatientPhoto } from "@/features/patients/hooks/use-patient-mutations";
import { computeAge } from "@/features/patients/components/PatientsTable";
import { PatientStatus } from "@/features/patients/types";
import { useVisitsForPatient } from "@/features/visits/hooks/use-visits";
import { VisitTable } from "@/features/visits/components/VisitTable";
import { PatientBillingHistory } from "@/features/billing/components/PatientBillingHistory";
import { PatientPrescriptionsHistory } from "@/features/clinical-orders/components/PatientPrescriptionsHistory";
import { PatientMedicalCertificatesHistory } from "@/features/clinical-orders/components/PatientMedicalCertificatesHistory";
import { PatientLaboratoryHistory } from "@/features/laboratory/components/PatientLaboratoryHistory";
import { PatientAppointmentsHistory } from "@/features/appointments/components/PatientAppointmentsHistory";
import { PatientFormDialog } from "@/features/patients/components/PatientFormDialog";
import { formatDate } from "@/lib/utils";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "personal", label: "Personal Information" },
  { key: "medical", label: "Medical Notes" },
  { key: "visits", label: "Visit History" },
  { key: "appointments", label: "Appointments" },
  { key: "billing", label: "Billing" },
  { key: "laboratory", label: "Laboratory" },
  { key: "prescriptions", label: "Prescriptions" },
  { key: "certificates", label: "Medical Certificates" },
  { key: "documents", label: "Documents" },
  { key: "audit", label: "Audit Logs" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const COMING_SOON_TABS = new Set<TabKey>([
  "documents",
  "audit",
]);

export default function PatientProfilePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const patientId = params.id;

  const { data: patient, isLoading } = usePatient(patientId);
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [editOpen, setEditOpen] = useState(false);
  const { data: qr } = usePatientQr(patientId, { enabled: activeTab === "overview" });
  const uploadPhoto = useUploadPatientPhoto(patientId);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [visitsPage, setVisitsPage] = useState(1);
  const [visitsDateRange, setVisitsDateRange] = useState<{ dateFrom?: string; dateTo?: string }>({});
  const { data: visitsData, isLoading: visitsLoading } = useVisitsForPatient(
    activeTab === "visits" ? patientId : null,
    visitsPage,
    10,
    visitsDateRange
  );

  if (isLoading) {
    return <SkeletonList rows={8} />;
  }

  if (!patient) {
    return <EmptyState title="Patient not found" description="This record may have been archived or removed." />;
  }

  const fullName = [patient.firstName, patient.middleName, patient.lastName, patient.suffix]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button type="button" variant="ghost" size="icon" onClick={() => router.push("/patients")} aria-label="Back to patients">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <div>
          <h1 className="text-xl font-semibold text-foreground">{fullName}</h1>
          <p className="font-mono text-sm text-muted-foreground">{patient.patientNumber}</p>
        </div>
        <Badge
          variant={patient.status === PatientStatus.Active ? "success" : "secondary"}
          className="ml-auto"
        >
          {patient.status}
        </Badge>
        <Button type="button" variant="outline" size="sm" onClick={() => setEditOpen(true)}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
          Edit
        </Button>
      </div>

      <PatientFormDialog open={editOpen} onOpenChange={setEditOpen} patient={patient} />

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
              activeTab === tab.key
                ? "border-b-2 border-primary text-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "overview" ? (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>Photo</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-3">
              <Avatar name={fullName} src={patient.photoUrl} size="lg" className="h-24 w-24 text-2xl" />
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadPhoto.mutate(file);
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                isLoading={uploadPhoto.isPending}
              >
                <Camera className="h-4 w-4" aria-hidden="true" />
                Upload photo
              </Button>
            </CardContent>
          </Card>

          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>Key info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <InfoRow label="Age" value={`${computeAge(patient.birthDate)} yrs`} />
              <InfoRow label="Gender" value={patient.gender} />
              <InfoRow label="Civil status" value={patient.civilStatus} />
              <InfoRow label="Mobile" value={patient.mobileNumber} />
              <InfoRow label="Email" value={patient.email ?? "—"} />
              <InfoRow label="Date registered" value={formatDate(patient.dateRegistered)} />
              <InfoRow
                label="Last visit"
                value={patient.lastVisit ? formatDate(patient.lastVisit) : "No visits yet"}
              />
            </CardContent>
          </Card>

          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>QR check-in code</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-2">
              {qr ? (
                <>
                  <div className="rounded-md border border-dashed border-border p-4 text-center">
                    <p className="break-all font-mono text-xs text-muted-foreground">{qr.payload}</p>
                  </div>
                  <p className="text-center text-xs text-muted-foreground">
                    Scannable check-in token for future queue/appointment modules. Image rendering is not
                    implemented yet - see docs/DATABASE.md.
                  </p>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">Loading QR code…</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "personal" ? (
        <Card>
          <CardHeader>
            <CardTitle>Personal information</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
            <InfoRow label="First name" value={patient.firstName} />
            <InfoRow label="Middle name" value={patient.middleName ?? "—"} />
            <InfoRow label="Last name" value={patient.lastName} />
            <InfoRow label="Suffix" value={patient.suffix ?? "—"} />
            <InfoRow label="Birth date" value={formatDate(patient.birthDate)} />
            <InfoRow label="Nationality" value={patient.nationality} />
            <InfoRow label="Address" value={patient.addressLine ?? "—"} />
            <InfoRow label="Barangay" value={patient.barangay ?? "—"} />
            <InfoRow label="City" value={patient.city ?? "—"} />
            <InfoRow label="Province" value={patient.province ?? "—"} />
            <InfoRow label="ZIP code" value={patient.zipCode ?? "—"} />
            <InfoRow label="Telephone" value={patient.telephoneNumber ?? "—"} />
            <InfoRow label="Occupation" value={patient.occupation ?? "—"} />
            <InfoRow label="Employer" value={patient.employer ?? "—"} />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "medical" ? (
        <Card>
          <CardHeader>
            <CardTitle>Medical notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <InfoRow label="Blood type" value={patient.bloodType ?? "Unspecified"} />
            <InfoRow label="Allergies" value={patient.allergies ?? "None recorded"} />
            <InfoRow label="Medical notes" value={patient.medicalNotes ?? "None recorded"} />
            <InfoRow label="Remarks" value={patient.remarks ?? "None recorded"} />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "visits" ? (
        <Card>
          <CardHeader>
            <CardTitle>Visit history</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <RecordDateRangeFilter
              onApply={(range) => {
                setVisitsDateRange(range);
                setVisitsPage(1);
              }}
            />
            <VisitTable items={visitsData?.data ?? []} isLoading={visitsLoading} />
            {visitsData && visitsData.meta.totalPages > 1 ? (
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  Page {visitsData.meta.page} of {visitsData.meta.totalPages} ({visitsData.meta.total} total)
                </span>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={visitsPage <= 1}
                    onClick={() => setVisitsPage((p) => Math.max(1, p - 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={visitsPage >= visitsData.meta.totalPages}
                    onClick={() => setVisitsPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "billing" ? (
        <Card>
          <CardHeader>
            <CardTitle>Billing history</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <PatientBillingHistory patientId={patientId} />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "laboratory" ? (
        <Card>
          <CardHeader>
            <CardTitle>Laboratory history</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <PatientLaboratoryHistory patientId={patientId} />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "appointments" ? (
        <Card>
          <CardHeader>
            <CardTitle>Appointments</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <PatientAppointmentsHistory patientId={patientId} />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "prescriptions" ? (
        <Card>
          <CardHeader>
            <CardTitle>Prescriptions</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <PatientPrescriptionsHistory patientId={patientId} />
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "certificates" ? (
        <Card>
          <CardHeader>
            <CardTitle>Medical Certificates</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <PatientMedicalCertificatesHistory patientId={patientId} />
          </CardContent>
        </Card>
      ) : null}

      {COMING_SOON_TABS.has(activeTab) ? (
        <EmptyState
          title="Coming in a future phase"
          description={`${TABS.find((t) => t.key === activeTab)?.label} will be available once that module is built.`}
        />
      ) : null}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/50 py-1.5 last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  );
}
