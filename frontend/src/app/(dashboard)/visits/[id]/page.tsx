"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonList } from "@/components/layout/LoadingSkeletons";
import { EmptyState } from "@/components/layout/EmptyState";
import { useVisit } from "@/features/visits/hooks/use-visit";
import { VisitStatusBadge } from "@/features/visits/components/VisitStatusBadge";
import { VisitTimeline } from "@/features/visits/components/VisitTimeline";
import { VISIT_PRIORITY_LABELS, VISIT_TYPE_LABELS } from "@/features/visits/types";
import { useCurrentUser } from "@/features/auth/hooks/use-current-user";
import { LockBanner } from "@/features/doctor-workspace/components/LockBanner";
import { useOpenVisit, useReleaseLock } from "@/features/doctor-workspace/hooks/use-doctor-actions";
import { DoctorQueueTable } from "@/features/doctor-workspace/components/DoctorQueueTable";
import { VisitBillingCard } from "@/features/billing/components/VisitBillingCard";
import { VisitOrdersCard } from "@/features/clinical-orders/components/VisitOrdersCard";
import { VisitPrescriptionsCard } from "@/features/clinical-orders/components/VisitPrescriptionsCard";
import { VisitLaboratoryCard } from "@/features/laboratory/components/VisitLaboratoryCard";
import type { DoctorQueueItem, LockInfo } from "@/features/doctor-workspace/types";
import { formatDateTime } from "@/lib/utils";

/** Heartbeat interval for the visit lock while this page stays mounted -
 * well inside `LOCK_TTL_MINUTES` (15) on the backend so an active viewer's
 * lock never expires out from under them. */
const LOCK_HEARTBEAT_MS = 5 * 60 * 1000;

const COMING_SOON_SECTIONS: { key: string; label: string }[] = [];

export default function VisitDetailsPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { data: visit, isLoading } = useVisit(params.id);
  const { data: currentUser } = useCurrentUser();
  const openVisit = useOpenVisit();
  const releaseLock = useReleaseLock();
  const [lock, setLock] = useState<LockInfo | null>(null);

  const canActAsDoctor = currentUser ? ["Owner", "Administrator", "Doctor"].includes(currentUser.role) : false;

  useEffect(() => {
    if (!params.id || !canActAsDoctor) return;
    let cancelled = false;
    const acquire = () => {
      openVisit.mutate(params.id, {
        onSuccess: (result) => {
          if (!cancelled) setLock(result);
        },
      });
    };
    acquire();
    const heartbeat = setInterval(acquire, LOCK_HEARTBEAT_MS);
    return () => {
      cancelled = true;
      clearInterval(heartbeat);
      if (lock?.isSelf) releaseLock.mutate(params.id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id, canActAsDoctor]);

  if (isLoading) {
    return <SkeletonList rows={8} />;
  }

  if (!visit) {
    return <EmptyState title="Visit not found" description="This visit record may have been removed." />;
  }

  const queueRow: DoctorQueueItem = {
    visitId: visit.id,
    visitNumber: visit.visitNumber,
    queueId: visit.queueId ?? null,
    queueNumber: visit.queueNumber ?? null,
    patientId: visit.patientId,
    patientName: visit.patientName ?? "",
    patientNumber: visit.patientNumber ?? "",
    age: null,
    gender: null,
    priority: visit.priority,
    status: visit.status,
    visitType: visit.visitType,
    arrivalTime: visit.arrivalTime ?? null,
    calledTime: null,
    consultationStart: null,
    waitingSeconds: null,
    isLocked: Boolean(lock?.locked),
    lockedByName: lock?.lockedByName ?? null,
    lockedBySelf: Boolean(lock?.isSelf),
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button type="button" variant="ghost" size="icon" onClick={() => router.push("/visits")} aria-label="Back to visits">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <div>
          <h1 className="font-mono text-xl font-semibold text-foreground">{visit.visitNumber}</h1>
          <p className="text-sm text-muted-foreground">{visit.patientName}</p>
        </div>
        <VisitStatusBadge status={visit.status} />
        {canActAsDoctor ? (
          <Button
            type="button"
            className="ml-auto"
            onClick={() => router.push(`/visits/${visit.id}/consultation`)}
          >
            Open Consultation
          </Button>
        ) : null}
      </div>

      {canActAsDoctor && lock ? <LockBanner lock={lock} /> : null}

      {canActAsDoctor ? (
        <Card>
          <CardHeader>
            <CardTitle>Doctor actions</CardTitle>
          </CardHeader>
          <CardContent>
            <DoctorQueueTable items={[queueRow]} readOnly={Boolean(lock && !lock.isSelf)} />
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Visit summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <InfoRow label="Patient" value={`${visit.patientName ?? "—"} (${visit.patientNumber ?? "—"})`} />
            <InfoRow label="Queue #" value={visit.queueNumber ?? "—"} />
            <InfoRow label="Doctor" value={visit.doctorName ?? "Unassigned"} />
            <InfoRow label="Department" value={visit.departmentName ?? "—"} />
            <InfoRow label="Service" value={visit.serviceName ?? "—"} />
            <InfoRow label="Visit type" value={VISIT_TYPE_LABELS[visit.visitType]} />
            <InfoRow label="Priority" value={VISIT_PRIORITY_LABELS[visit.priority]} />
            <InfoRow
              label="Arrival time"
              value={visit.arrivalTime ? formatDateTime(visit.arrivalTime) : "—"}
            />
            <InfoRow label="Branch" value={visit.branchName ?? "—"} />
            {visit.remarks ? <InfoRow label="Remarks" value={visit.remarks} /> : null}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <VisitTimeline events={visit.timeline} />
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        <VisitBillingCard visitId={visit.id} />
        <VisitOrdersCard visitId={visit.id} />
        <VisitPrescriptionsCard visitId={visit.id} />
        <VisitLaboratoryCard visitId={visit.id} />
        {COMING_SOON_SECTIONS.map((section) => (
          <Card key={section.key}>
            <CardHeader>
              <CardTitle>{section.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="Coming in a future phase"
                description={`${section.label} will be available once that module is built.`}
              />
            </CardContent>
          </Card>
        ))}
      </div>
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

